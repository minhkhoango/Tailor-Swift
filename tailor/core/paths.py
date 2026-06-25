#!/usr/bin/env python3
"""Single home for the repo layout the tailor program depends on.

This file is the one place that knows where things live. Relocate the package
and only this file changes -- every other module imports its paths from here
(CONTEXT.md: "paths.py is the single home for repo layout").

Layout (this file lives at ``<repo>/tailor/core/paths.py``)::

    <repo>/
      tailor/            the program (orchestrator + llm + core/)
      assets/master_resume.tex
      references/{honesty-rules,keywords,cover-letter}.md
      jobDescription/<stem>.txt        JD inputs (gitignored)
      output/<stem>/                   shipped resume.slots.json + resume.pdf
      dataset/<stem>/                  frozen AI-baseline / human-final pairs
      .tailor_cache/<stem>/            scratch for in-flight passes (gitignored)
      logs/tailor-<ts>.jsonl           run logs (gitignored)
"""

from __future__ import annotations

from pathlib import Path

CORE = Path(__file__).resolve().parent          # .../tailor/core
PACKAGE = CORE.parent                            # .../tailor
REPO_ROOT = PACKAGE.parent                       # repo root

OUTPUT = REPO_ROOT / "output"
DATASET = REPO_ROOT / "dataset"
JOBDESC = REPO_ROOT / "jobDescription"
SCRATCH = REPO_ROOT / ".tailor_cache"
LOGS = REPO_ROOT / "logs"

ASSETS = REPO_ROOT / "assets"
MASTER = ASSETS / "master_resume.tex"

REFERENCES = REPO_ROOT / "references"
HONESTY_RULES = REFERENCES / "honesty-rules.md"
KEYWORDS = REFERENCES / "keywords.md"
COVER_LETTER_REF = REFERENCES / "cover-letter.md"   # mined for the why-prompt bar (E2)

VENV_PY = REPO_ROOT / ".venv" / "bin" / "python"

# The shipped slot/pdf names a tailored company directory carries.
SLOTS_NAME = "resume.slots.json"
RESUME_TEX = "resume.tex"
RESUME_JOBNAME = "Khoa_Ngo_resume"

# The two output files the live watcher cares about, and the kind each maps to.
_OUTPUT_FILE_KINDS = {
    SLOTS_NAME: "slots",
    RESUME_TEX: "resume",
}


def classify_output(file_path: str | Path) -> tuple[str, str] | None:
    """Classify a saved file as a tailored artifact under ``output/<stem>/``.

    Returns ``(stem, kind)`` when ``file_path`` is one of the watched names
    sitting directly in an ``output/<stem>/`` directory, else ``None``. ``kind``
    is ``"slots" | "resume"``. The parent-of-parent must resolve to OUTPUT, so a
    same-named file elsewhere is ignored.
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
