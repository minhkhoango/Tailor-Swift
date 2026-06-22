#!/usr/bin/env python3
"""Single home for the repo layout the /tailor scripts depend on.

Every other script in this directory used to re-derive the repo root with a
fragile ``Path(__file__).resolve().parents[4]`` and re-declare OUTPUT / MASTER /
DATASET / JOBDESC. That depth-counting now lives here, once: move the skill
folder and only this file changes.

Importable from any sibling script (this dir is on sys.path when a script is run
directly, and the test harness inserts it explicitly).
"""

from __future__ import annotations

from pathlib import Path

# This file lives at <repo>/.claude/skills/tailor/scripts/paths.py.
SCRIPTS = Path(__file__).resolve().parent          # .../tailor/scripts
SKILL_DIR = SCRIPTS.parent                         # .../tailor
REPO_ROOT = SCRIPTS.parents[3]                     # scripts -> tailor -> skills -> .claude -> repo

SRC = REPO_ROOT / "src"                            # build_resume.py / build_cover_letter.py live here
OUTPUT = REPO_ROOT / "output"
DATASET = REPO_ROOT / "dataset"
JOBDESC = REPO_ROOT / "jobDescription"
MASTER = SKILL_DIR / "assets" / "master_resume.tex"
VENV_PY = REPO_ROOT / ".venv" / "bin" / "python"

# The three tailored artifacts a save can touch, and the kind each maps to. Both
# the PostToolUse hook and the watcher used to re-derive this same parse; it now
# lives here once, beside the layout it depends on.
_OUTPUT_FILE_KINDS = {
    "resume.slots.json": "slots",
    "resume.tex": "resume",
    "cover_letter.tex": "cover",
}


def classify_output(file_path: str | Path) -> tuple[str, str] | None:
    """Classify a saved file as a tailored artifact under ``output/<company>/``.

    Returns ``(company, kind)`` when ``file_path`` is one of the watched names
    sitting directly in an ``output/<company>/`` directory, else ``None``. ``kind``
    is one of ``"slots" | "resume" | "cover"``. The parent-of-parent must be the
    real OUTPUT dir (resolved), so a same-named file elsewhere is ignored.
    """
    p = Path(file_path)
    kind = _OUTPUT_FILE_KINDS.get(p.name)
    if kind is None:
        return None
    parent = p.parent
    try:
        if parent.parent.resolve() != OUTPUT.resolve():
            return None
    except OSError:
        return None
    return (parent.name, kind)
