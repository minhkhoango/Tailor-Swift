#!/usr/bin/env python3
"""Local live-rebuild watcher for hand-edited tailored slots.

Dev convenience: edit ``output/<stem>/resume.slots.json`` by hand and the PDF
re-renders live (Overleaf-style), and the edit is snapshotted as that company's
rolling human-final benchmark slot. In the self-contained world there is no agent
to race -- the orchestrator builds in a scratch dir -- so this watcher needs **no
lock**. It only ever sees human edits.

Run it by hand from the repo root::

    .venv/bin/python -m tailor.core.watch

It is a singleton (``.watch.pid`` at the repo root) and self-detaches: the
launching command returns at once, either double-forking a detached daemon
(logging to ``.watch.log``) or printing that one already runs. Requires
``watchdog`` (in requirements.txt).
"""

from __future__ import annotations

import atexit
import os
import sys
import threading
import time
from pathlib import Path

from . import pdf_compile
from .assemble_resume import AssembleError, SlotsError, assemble_dir
from .capture import capture_human_final
from .paths import OUTPUT, REPO_ROOT, RESUME_JOBNAME, SLOTS_NAME, classify_output

DEBOUNCE_SECONDS = 0.75
PIDFILE = REPO_ROOT / ".watch.pid"
LOGFILE = REPO_ROOT / ".watch.log"

_timers: dict[str, threading.Timer] = {}
_build_locks: dict[str, threading.Lock] = {}
_state_lock = threading.Lock()


def _rebuild(stem: str) -> None:
    """Assemble + compile the hand-edited slot, then snapshot the human-final."""
    out_dir = OUTPUT / stem
    with _state_lock:
        lock = _build_locks.setdefault(stem, threading.Lock())
    with lock:
        print(f"[watch] {stem}: rebuilding from {SLOTS_NAME}...", flush=True)
        try:
            assemble_dir(out_dir)
        except (AssembleError, SlotsError) as e:
            print(f"[watch] {stem}: assemble failed: {e}", flush=True)
            return
        pdf_compile.compile_tex(out_dir / "resume.tex", RESUME_JOBNAME, 2)
        capture_human_final(stem, out_dir / SLOTS_NAME)
        print(f"[watch] {stem}: rebuilt PDF + captured human-final slot", flush=True)


def _schedule(stem: str) -> None:
    with _state_lock:
        old = _timers.get(stem)
        if old is not None:
            old.cancel()
        t = threading.Timer(DEBOUNCE_SECONDS, _rebuild, args=(stem,))
        _timers[stem] = t
        t.daemon = True
        t.start()


def _classify(path: Path) -> str | None:
    """Stem for a hand-edited ``output/<stem>/resume.slots.json`` save, else None.

    The scratch dir (``.tailor_cache``) lives outside OUTPUT, so the shared
    classifier never matches it -- mid-loop churn is invisible to the watcher.
    """
    target = classify_output(path)
    return target[0] if target is not None and target[1] == "slots" else None


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
            stem = _classify(Path(str(event.src_path)))
            if stem is not None:
                _schedule(stem)

        def on_modified(self, event: "FileSystemEvent") -> None:
            self._on(event)

        def on_created(self, event: "FileSystemEvent") -> None:
            self._on(event)

    observer = Observer()
    observer.schedule(Handler(), str(OUTPUT), recursive=True)
    observer.start()
    print(f"[watch] watching {OUTPUT}/*/{SLOTS_NAME} for hand edits. Ctrl-C to stop.",
          flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
