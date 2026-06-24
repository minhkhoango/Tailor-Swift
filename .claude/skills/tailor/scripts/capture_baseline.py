#!/usr/bin/env python3
"""Stop hook: capture the AI-baseline snapshot when a /tailor turn ends.

assemble_resume.py drops an ``output/<company>/.ai_phase.lock`` for every company
tailored this turn. When the turn ends, this Stop hook scans those locks (NOT a
blind output/ scan -- that would wrongly baseline pre-existing companies). For
each locked company whose resume is COMPLETE (the PDF exists and resume.tex has
``\\end{document}``), it copies the AI's first version into the git-tracked
dataset/:

    output/<co>/resume.tex        -> dataset/<co>/resume.ai.tex
    output/<co>/cover_letter.tex  -> dataset/<co>/cover_letter.ai.tex   (if present)
    jobDescription/<co>.txt       -> dataset/<co>/job_description.txt    (if present)

then deletes the lock. Incomplete + fresh -> leave the lock for next time.
Incomplete + stale (>10 min) -> the run was abandoned; drop the lock. A company
that already has a baseline is refused by the assembler (no redo path), so this
only ever captures a first, fresh pair. Always exits 0.

Wired in .claude/settings.local.json under hooks.Stop.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import tailor_lock
from paths import DATASET, JOBDESC, OUTPUT

RESUME_JOBNAME = "Khoa_Ngo_resume"


def _complete(out_dir: Path) -> bool:
    pdf = out_dir / f"{RESUME_JOBNAME}.pdf"
    tex = out_dir / "resume.tex"
    if not pdf.exists() or not tex.exists():
        return False
    try:
        return "\\end{document}" in tex.read_text(encoding="utf-8")
    except OSError:
        return False


def _capture(company: str) -> None:
    out_dir = OUTPUT / company
    co_dir = DATASET / company
    co_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(out_dir / "resume.tex", co_dir / "resume.ai.tex")
    cover = out_dir / "cover_letter.tex"
    if cover.exists():
        shutil.copy2(cover, co_dir / "cover_letter.ai.tex")
    jd = JOBDESC / f"{company}.txt"
    if jd.exists():
        shutil.copy2(jd, co_dir / "job_description.txt")


def main() -> int:
    # Drain stdin (Stop payload) but we don't need any field from it.
    try:
        sys.stdin.read()
    except Exception:  # noqa: BLE001
        pass

    for out_dir in tailor_lock.find_locked(OUTPUT):
        company = out_dir.name
        if _complete(out_dir):
            try:
                _capture(company)
                tailor_lock.clear(out_dir)
            except OSError:
                pass  # leave the lock; try again next turn
        elif tailor_lock.is_stale(out_dir):
            tailor_lock.clear(out_dir)  # abandoned run
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never let a hook bug surface as a turn error
        print(f"[capture_baseline] non-fatal error: {exc}", file=sys.stderr)
        sys.exit(0)
