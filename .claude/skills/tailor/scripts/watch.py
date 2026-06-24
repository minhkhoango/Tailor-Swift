#!/usr/bin/env python3
"""Local live-rebuild watcher for tailored resumes / cover letters.

The final step of a /tailor run auto-starts this in the background; it can also
be run by hand:

    .venv/bin/python .claude/skills/tailor/scripts/watch.py

It is a singleton (a ``.watch.pid`` lock at the repo root) AND it self-detaches:
the launching command ALWAYS returns at once with a clear one-line verdict --

  * no watcher yet -> it double-forks a detached daemon (logs to ``.watch.log``)
    and the launcher returns immediately, or
  * one already running -> it prints a notice and returns immediately.

So re-running /tailor never spawns a duplicate and never leaves the caller holding
a long-lived process that merely *looks* like it died the instant it's relaunched.

It watches ``output/*/resume.tex`` and ``output/*/cover_letter.tex``. On save:

  * If the company still has a fresh ``.ai_phase.lock`` the AI is mid-tailor --
    the PostToolUse hook owns the build, so we SKIP (this prevents a double
    ``pdflatex`` and stops AI drafts from leaking into the *.final.tex snapshot).
  * Otherwise it's a human edit: debounce briefly, rebuild the PDF in-process via
    the skill's compile core (live Overleaf-style refresh), and overwrite
    ``dataset/<co>/{resume,cover_letter}.final.tex`` (last write wins) -- the
    rolling "human final" half of each training pair.

Requires `watchdog` (in requirements.txt). Everything else is sibling modules in
this scripts/ dir, so the watcher lives inside the self-contained skill.
"""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import threading
import time
from pathlib import Path

import pdf_compile
import tailor_lock
from paths import DATASET, OUTPUT, REPO_ROOT, classify_output

DEBOUNCE_SECONDS = 0.75
PIDFILE = REPO_ROOT / ".watch.pid"
LOGFILE = REPO_ROOT / ".watch.log"

# filename -> (pdflatex jobname, pass count, dataset snapshot name)
WATCHED: dict[str, tuple[str, int, str]] = {
    "resume.tex": ("Khoa_Ngo_resume", 2, "resume.final.tex"),
    "cover_letter.tex": ("Khoa_Ngo_cover_letter", 1, "cover_letter.final.tex"),
}

_timers: dict[tuple[str, str], threading.Timer] = {}
_build_locks: dict[str, threading.Lock] = {}
_state_lock = threading.Lock()


def _rebuild(company: str, filename: str) -> None:
    out_dir = OUTPUT / company
    if tailor_lock.is_fresh(out_dir):
        print(f"[watch] {company}/{filename}: skipped: tailor_lock", flush=True)
        return
    jobname, passes, snapshot = WATCHED[filename]
    with _state_lock:
        lock = _build_locks.setdefault(company, threading.Lock())
    with lock:
        print(f"[watch] {company}/{filename}: rebuilding PDF...", flush=True)
        pdf_compile.compile_tex(out_dir / filename, jobname, passes)
        co_dir = DATASET / company
        co_dir.mkdir(parents=True, exist_ok=True)
        src = out_dir / filename
        if src.exists():
            shutil.copy2(src, co_dir / snapshot)
            print(f"[watch] {company}: wrote dataset/{company}/{snapshot}", flush=True)


def _schedule(company: str, filename: str) -> None:
    key = (company, filename)
    with _state_lock:
        old = _timers.get(key)
        if old is not None:
            old.cancel()
        t = threading.Timer(DEBOUNCE_SECONDS, _rebuild, args=(company, filename))
        _timers[key] = t
        t.daemon = True
        t.start()


def _classify(path: Path) -> tuple[str, str] | None:
    """(company, filename) for a watched save under output/<company>/, else None.

    Defers the output-dir membership check to the shared classifier, then keeps
    only the two filenames the watcher rebuilds (slot files are ignored here).
    """
    if path.name not in WATCHED:
        return None
    target = classify_output(path)
    return (target[0], path.name) if target is not None else None


def _live_watcher_pid() -> int | None:
    """PID of a watcher already holding ``.watch.pid``, else None.

    Reads the lock, probes the pid with signal 0 (a no-op liveness check), and
    clears the lock if it was left behind by a dead process so the next claim can
    reclaim it. Our own pid counts as live (we already hold the lock).
    """
    try:
        pid = int(PIDFILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if pid == os.getpid():
        return pid
    try:
        os.kill(pid, 0)                   # signal 0 == liveness probe, no-op if alive
        return pid                        # someone alive holds it
    except OSError:
        PIDFILE.unlink(missing_ok=True)   # stale lock from a dead process; clear it
        return None


def _claim_singleton() -> bool:
    """Become the sole watcher, or report another is already live.

    Returns True if we claimed the lock (and registered its cleanup), False if a
    running watcher already holds ``.watch.pid``. A lock left by a dead process is
    reclaimed. This is the real gate: two daemons racing to start both reach here,
    but only the first writes its pid -- the loser sees a live lock and bows out.
    """
    if _live_watcher_pid() is not None:
        return False
    PIDFILE.write_text(str(os.getpid()), encoding="utf-8")
    atexit.register(lambda: PIDFILE.unlink(missing_ok=True))
    return True


def _daemonize() -> bool:
    """Detach into a background daemon so the launcher returns immediately.

    POSIX double-fork: the original (launcher) process gets False and should
    return at once; the surviving grandchild gets True, is reparented to init,
    and runs the watch loop with its std streams redirected to ``.watch.log`` (so
    later prints never hit a closed pipe once the launcher is gone). On a platform
    without ``os.fork`` it can't detach, so it returns True and runs inline.
    """
    if not hasattr(os, "fork"):
        return True
    if os.fork() > 0:
        return False                      # launcher: return now, daemon lives on
    os.setsid()
    if os.fork() > 0:
        os._exit(0)                       # intermediate child exits
    sys.stdout.flush()
    sys.stderr.flush()
    log = open(LOGFILE, "a", buffering=1, encoding="utf-8")
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, sys.stdin.fileno())
    os.dup2(log.fileno(), sys.stdout.fileno())
    os.dup2(log.fileno(), sys.stderr.fileno())
    return True


def main() -> int:
    try:
        from watchdog.events import FileSystemEvent, FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        print("watchdog not installed - run: "
              "python3 -m venv .venv && .venv/bin/pip install -r requirements.txt "
              "(then run this with .venv/bin/python watch.py)")
        return 2

    # Fast path: a live watcher already owns the lock -> say so and return at once.
    live = _live_watcher_pid()
    if live is not None:
        print(f"[watch] already running (pid {live}) — nothing to do.", flush=True)
        return 0

    # Otherwise detach a daemon and let the launcher return immediately. Both
    # branches make the launching command exit fast and clean, so a relaunch never
    # looks like a process that died on startup.
    if not _daemonize():
        print(f"[watch] started in background (logs -> "
              f"{LOGFILE.relative_to(REPO_ROOT)}).", flush=True)
        return 0

    # --- daemon child from here on ---
    if not _claim_singleton():         # lost a startup race; the winner is watching
        return 0

    OUTPUT.mkdir(exist_ok=True)

    class Handler(FileSystemEventHandler):
        def _on(self, event: "FileSystemEvent") -> None:
            if event.is_directory:
                return
            target = _classify(Path(str(event.src_path)))
            if target is not None:
                _schedule(*target)

        def on_modified(self, event: "FileSystemEvent") -> None:
            self._on(event)

        def on_created(self, event: "FileSystemEvent") -> None:
            self._on(event)

    observer = Observer()
    observer.schedule(Handler(), str(OUTPUT), recursive=True)
    observer.start()
    print(f"[watch] watching {OUTPUT}/*/ for resume.tex + cover_letter.tex saves. "
          f"Ctrl-C to stop.", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
