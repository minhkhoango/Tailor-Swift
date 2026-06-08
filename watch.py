#!/usr/bin/env python3
"""Local live-rebuild watcher for tailored resumes / cover letters.

Start it once and leave it running:

    python3 watch.py            # uses .venv if present, else system python

It watches ``output/*/resume.tex`` and ``output/*/cover_letter.tex``. On save:

  * If the company still has a fresh ``.ai_phase.lock`` the AI is mid-tailor --
    the PostToolUse hook owns the build, so we SKIP (this prevents a double
    ``pdflatex`` and stops AI drafts from leaking into the *.final.tex snapshot).
  * Otherwise it's a human edit: debounce briefly, rebuild the PDF (live Overleaf-
    style refresh), and overwrite ``dataset/<co>/{resume,cover_letter}.final.tex``
    (last write wins) -- the rolling "human final" half of each training pair.

Requires `watchdog` (in requirements.txt).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
DATASET = ROOT / "dataset"
STALE_SECONDS = 10 * 60
DEBOUNCE_SECONDS = 0.75

# filename -> (build script, dataset snapshot name)
WATCHED = {
    "resume.tex": ("build_resume.py", "resume.final.tex"),
    "cover_letter.tex": ("build_cover_letter.py", "cover_letter.final.tex"),
}

_timers: dict[tuple[str, str], threading.Timer] = {}
_build_locks: dict[str, threading.Lock] = {}
_state_lock = threading.Lock()


def _ai_phase(out_dir: Path) -> bool:
    lock = out_dir / ".ai_phase.lock"
    if not lock.exists():
        return False
    try:
        return (time.time() - lock.stat().st_mtime) < STALE_SECONDS
    except OSError:
        return False


def _rebuild(company: str, filename: str) -> None:
    out_dir = OUTPUT / company
    if _ai_phase(out_dir):
        print(f"[watch] {company}/{filename}: skipped: ai_phase", flush=True)
        return
    build_script, snapshot = WATCHED[filename]
    with _state_lock:
        lock = _build_locks.setdefault(company, threading.Lock())
    with lock:
        print(f"[watch] {company}/{filename}: rebuilding PDF...", flush=True)
        subprocess.run([sys.executable, build_script, company], cwd=str(ROOT))
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
    if path.name not in WATCHED:
        return None
    if path.parent.parent != OUTPUT:
        return None
    return (path.parent.name, path.name)


def main() -> int:
    try:
        from watchdog.events import FileSystemEvent, FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        print("watchdog not installed - run: "
              "python3 -m venv .venv && .venv/bin/pip install -r requirements.txt "
              "(then run this with .venv/bin/python watch.py)", file=sys.stderr)
        return 2

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
    sys.exit(main())
