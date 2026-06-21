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

OUTPUT = REPO_ROOT / "output"
DATASET = REPO_ROOT / "dataset"
JOBDESC = REPO_ROOT / "jobDescription"
MASTER = SKILL_DIR / "assets" / "master_resume.tex"
VENV_PY = REPO_ROOT / ".venv" / "bin" / "python"
