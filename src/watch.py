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

# Repo layout, the AI-phase lock protocol, and the output-file classifier are all
# owned by the tailor layer; import them so the watcher and the hook agree byte for
# byte. The skill scripts dir is added to the path for a bare ``python3 watch.py``.
SRC = Path(__file__).resolve().parent          # src/ — holds the build scripts
_SCRIPTS = SRC.parent / ".claude" / "skills" / "tailor" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
import ai_phase  # noqa: E402
from paths import DATASET, OUTPUT, REPO_ROOT, classify_output  # noqa: E402

DEBOUNCE_SECONDS = 0.75

# filename -> (build script, dataset snapshot name)
WATCHED = {
    "resume.tex": ("build_resume.py", "resume.final.tex"),
    "cover_letter.tex": ("build_cover_letter.py", "cover_letter.final.tex"),
}

_timers: dict[tuple[str, str], threading.Timer] = {}
_build_locks: dict[str, threading.Lock] = {}
_state_lock = threading.Lock()


def _rebuild(company: str, filename: str) -> None:
    out_dir = OUTPUT / company
    if ai_phase.is_fresh(out_dir):
        print(f"[watch] {company}/{filename}: skipped: ai_phase", flush=True)
        return
    build_script, snapshot = WATCHED[filename]
    with _state_lock:
        lock = _build_locks.setdefault(company, threading.Lock())
    with lock:
        print(f"[watch] {company}/{filename}: rebuilding PDF...", flush=True)
        subprocess.run([sys.executable, str(SRC / build_script), company], cwd=str(REPO_ROOT))
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
