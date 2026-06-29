#!/usr/bin/env python3
"""Single home for the repo layout the tailor program depends on.

This file is the one place that knows where things live. Relocate the package
and only this file changes -- every other module imports its paths from here
(CONTEXT.md: "paths.py is the single home for repo layout").

Layout (this file lives at ``<repo>/tailor/core/paths.py``)::

    <repo>/
      tailor/            the program (orchestrator + llm + core/)
      assets/master_resume.tex         the pool + Technical Skills + keyword ledger
      jobDescription/<stem>.txt        JD inputs (gitignored)
      output/<stem>/                   shipped resume.slots.json + resume.pdf
      dataset/<stem>/                  frozen AI-baseline / human-final pairs
      .tailor_cache/<stem>/            scratch for in-flight passes (gitignored)
      logs/tailor-<ts>.jsonl           run logs (gitignored)
"""

from __future__ import annotations

import os
from pathlib import Path

CORE = Path(__file__).resolve().parent          # .../tailor/core
PACKAGE = CORE.parent                            # .../tailor
REPO_ROOT = PACKAGE.parent                       # repo root

ENV_FILE = REPO_ROOT / ".env"           # local secrets (gitignored): ANTHROPIC_API_KEY=...

OUTPUT = REPO_ROOT / "output"
DATASET = REPO_ROOT / "dataset"
JOBDESC = REPO_ROOT / "jobDescription"
SCRATCH = REPO_ROOT / ".tailor_cache"
LOGS = REPO_ROOT / "logs"

ASSETS = REPO_ROOT / "assets"
MASTER = ASSETS / "master_resume.tex"   # pool + \section{Technical Skills} + % KEYWORD LEDGER

VENV_PY = REPO_ROOT / ".venv" / "bin" / "python"

# Scrape feeder (deterministic, part of tailor -- NOT an agent skill): the search
# config is committed; the browser login + run manifest are gitignored runtime state.
SCRAPE_CONFIG = REPO_ROOT / "scrape.config.json"
SCRAPE_STATE = REPO_ROOT / ".scrape"                    # runtime state (gitignored)
SCRAPE_PROFILE = SCRAPE_STATE / "profile"               # persistent simplify login
SCRAPE_LAST_RUN = SCRAPE_STATE / "last_run.json"        # last run manifest

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


def load_env(env_file: Path = ENV_FILE, *, override: bool = False) -> dict[str, str]:
    """Load a ``.env`` file into ``os.environ`` and return the names+values applied.

    A deliberately small, zero-dependency dotenv reader (the project stays
    self-contained -- no ``python-dotenv``). It parses ``KEY=value`` one per
    line; this is the one place the program bridges the gitignored ``.env`` to
    the process environment the Anthropic SDK reads.

    Parsing rules, matching the common dotenv dialect:

      * blank lines and ``#`` comment lines are skipped;
      * an optional leading ``export `` on a line is ignored;
      * the key is everything before the first ``=`` (trimmed); a line with no
        ``=`` or an empty key is skipped rather than raising -- a malformed
        ``.env`` never crashes startup;
      * the value is everything after the first ``=`` (trimmed), with one layer
        of surrounding matching single/double quotes stripped (so spaces or
        ``#`` inside a quoted value survive).

    Precedence follows dotenv convention: a variable already present in
    ``os.environ`` is **not** overwritten unless ``override`` is True, so a key
    exported in the shell always wins over the file. A missing file is a no-op
    (returns ``{}``) -- ``.env`` is optional, not required.

    Returns the ``{name: value}`` map actually written to ``os.environ`` so a
    caller can log which keys were picked up (log the NAMES, never the values).
    """
    if not env_file.is_file():
        return {}
    applied: dict[str, str] = {}
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if override or key not in os.environ:
            os.environ[key] = value
            applied[key] = value
    return applied
