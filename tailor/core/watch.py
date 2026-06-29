#!/usr/bin/env python3
"""Local live-rebuild watcher for hand-edited tailored resumes.

Dev convenience: edit either ``output/<stem>/resume.slots.json`` OR
``output/<stem>/resume.tex`` by hand and the PDF re-renders live (Overleaf-style),
and the edit is snapshotted as that company's rolling human-final benchmark. The
PDF is always whatever you saved last:

* save ``resume.slots.json`` -> assemble it into ``resume.tex`` (overwriting any
  hand edits there), compile, snapshot ``dataset/<stem>/resume.final.slots.json``.
* save ``resume.tex`` -> compile that tex **as-is** (slots left untouched/stale),
  snapshot ``dataset/<stem>/resume.final.tex``.

Capturing one format drops the other's stale dataset final (see capture.py), so a
company keeps a single, unambiguous human-final.

The slots rebuild itself *writes* ``resume.tex``; that machine write would loop
back through the tex watcher forever. We dodge it by remembering the SHA of each
assembled tex and ignoring any tex event whose content matches -- only real human
edits get through.

Run it by hand from the repo root::

    .venv/bin/python -m tailor.core.watch

It is a singleton (``.watch.pid`` at the repo root) and self-detaches: the
launching command returns at once, either double-forking a detached daemon
(logging to ``.watch.log``) or printing that one already runs. Requires
``watchdog`` (in requirements.txt).
"""

from __future__ import annotations

import atexit
import hashlib
import os
import sys
import threading
import time
from pathlib import Path

from . import pdf_compile
from .assemble_resume import AssembleError, SlotsError, assemble_dir
from .capture import capture_human_final
from .paths import (
    OUTPUT,
    REPO_ROOT,
    RESUME_JOBNAME,
    RESUME_TEX,
    SLOTS_NAME,
    classify_output,
)

DEBOUNCE_SECONDS = 0.75
PIDFILE = REPO_ROOT / ".watch.pid"
LOGFILE = REPO_ROOT / ".watch.log"

# Timers are keyed by (stem, kind) so a slots save and a tex save debounce
# independently instead of one clobbering the other's pending rebuild.
_timers: dict[tuple[str, str], threading.Timer] = {}
_build_locks: dict[str, threading.Lock] = {}
# stem -> SHA of the resume.tex we last wrote during a slots rebuild. A tex event
# whose content matches is our own write, not a human edit -- skip it (else slots
# edits loop through the tex watcher and falsely capture tex as the final).
_machine_tex_hash: dict[str, str] = {}
_state_lock = threading.Lock()


def _sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _rebuild(stem: str, kind: str) -> None:
    """Rebuild the PDF from whichever source the user just saved, then snapshot it.

    ``kind == "slots"``: assemble slots -> tex (overwriting hand tex edits),
    compile, capture the slots final. ``kind == "resume"``: compile the
    hand-edited tex as-is (slots left stale), capture the tex final -- but only
    when the tex differs from our own last assemble write, so the machine write
    that a slots rebuild produces does not loop back here.
    """
    out_dir = OUTPUT / stem
    tex = out_dir / RESUME_TEX
    with _state_lock:
        lock = _build_locks.setdefault(stem, threading.Lock())
    with lock:
        if kind == "slots":
            print(f"[watch] {stem}: {SLOTS_NAME} saved -> assemble + compile...", flush=True)
            try:
                assemble_dir(out_dir)
            except (AssembleError, SlotsError) as e:
                print(f"[watch] {stem}: assemble failed: {e}", flush=True)
                return
            with _state_lock:
                _machine_tex_hash[stem] = _sha(tex)
            pdf_compile.compile_tex(tex, RESUME_JOBNAME, 2)
            capture_human_final(stem, out_dir / SLOTS_NAME, "slots")
            print(f"[watch] {stem}: rebuilt PDF from slots + captured slots final", flush=True)
        else:  # kind == "resume": hand-edited tex is the source of truth
            with _state_lock:
                machine = _machine_tex_hash.get(stem)
            if machine is not None and _sha(tex) == machine:
                return  # our own assemble write, not a human edit -- ignore
            print(f"[watch] {stem}: {RESUME_TEX} saved -> compile tex as-is...", flush=True)
            pdf_compile.compile_tex(tex, RESUME_JOBNAME, 2)
            capture_human_final(stem, tex, "resume")
            print(f"[watch] {stem}: rebuilt PDF from tex + captured tex final", flush=True)


def _schedule(stem: str, kind: str) -> None:
    key = (stem, kind)
    with _state_lock:
        old = _timers.get(key)
        if old is not None:
            old.cancel()
        t = threading.Timer(DEBOUNCE_SECONDS, _rebuild, args=(stem, kind))
        _timers[key] = t
        t.daemon = True
        t.start()


def _live_watcher_pid() -> int | None:
    try:
        pid = int(PIDFILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if pid == os.getpid():
        return pid
    try:
        os.kill(pid, 0)
        return pid
    except OSError:
        PIDFILE.unlink(missing_ok=True)
        return None


def _claim_singleton() -> bool:
    if _live_watcher_pid() is not None:
        return False
    PIDFILE.write_text(str(os.getpid()), encoding="utf-8")
    atexit.register(lambda: PIDFILE.unlink(missing_ok=True))
    return True


def _daemonize() -> bool:
    """POSIX double-fork; launcher gets False, the detached grandchild gets True."""
    if not hasattr(os, "fork"):
        return True
    if os.fork() > 0:
        return False
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
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
        print("watchdog not installed - run: .venv/bin/pip install -r requirements.txt")
        return 2

    live = _live_watcher_pid()
    if live is not None:
        print(f"[watch] already running (pid {live}) -- nothing to do.", flush=True)
        return 0

    if not _daemonize():
        print(f"[watch] started in background (logs -> {LOGFILE.name}).", flush=True)
        return 0

    if not _claim_singleton():
        return 0

    OUTPUT.mkdir(exist_ok=True)

    class Handler(FileSystemEventHandler):
        def _on(self, event: "FileSystemEvent") -> None:
            if event.is_directory:
                return
            # classify_output returns (stem, kind) for either watched name sitting
            # directly under output/<stem>/; the scratch dir (.tailor_cache) lives
            # outside OUTPUT so mid-loop churn never matches.
            target = classify_output(Path(str(event.src_path)))
            if target is not None:
                _schedule(target[0], target[1])

        def on_modified(self, event: "FileSystemEvent") -> None:
            self._on(event)

        def on_created(self, event: "FileSystemEvent") -> None:
            self._on(event)

    observer = Observer()
    observer.schedule(Handler(), str(OUTPUT), recursive=True)
    observer.start()
    print(f"[watch] watching {OUTPUT}/*/{{{SLOTS_NAME},{RESUME_TEX}}} for hand edits. "
          "Ctrl-C to stop.", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
