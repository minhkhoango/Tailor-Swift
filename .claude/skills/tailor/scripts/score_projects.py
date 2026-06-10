#!/usr/bin/env python3
"""Rank the 5 pool projects by JD-keyword overlap (advisory).

Reads the JD plus each project block's bullets and ``% Default/Other defensible
stack:`` comments (keyed by ``@key`` in master_resume.tex) and prints a ranked
overlap table. Claude runs this at selection time to sanity-check its picks --
the final choice still belongs to Claude.

Usage:
    python3 score_projects.py <company>
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import tex_util

REPO_ROOT = Path(__file__).resolve().parents[4]
SKILL_DIR = Path(__file__).resolve().parents[1]
MASTER = SKILL_DIR / "assets" / "master_resume.tex"
JOBDESC = REPO_ROOT / "jobDescription"

_STOP = {
    "the", "and", "for", "with", "you", "your", "our", "are", "will", "have",
    "this", "that", "from", "they", "them", "their", "has", "but", "not", "all",
    "can", "use", "using", "work", "working", "team", "teams", "role", "job",
    "who", "what", "how", "why", "into", "out", "per", "etc", "able", "across",
    "experience", "experiences", "skills", "knowledge", "ability", "strong",
    "years", "year", "plus", "preferred", "required", "requirements", "looking",
}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9.+#]+", text.lower())
            if len(t) >= 3 and t not in _STOP}


def score(company: str) -> int:
    jd_path = JOBDESC / f"{company}.txt"
    if not jd_path.exists():
        print(f"missing JD: {jd_path.relative_to(REPO_ROOT)}", file=sys.stderr)
        return 1
    jd = _tokens(jd_path.read_text(encoding="utf-8"))

    blocks = tex_util.parse_master(MASTER.read_text(encoding="utf-8"))
    projects = [b for b in blocks.values() if b.kind == "project"]

    rows: list[tuple[str, int, list[str]]] = []
    for b in projects:
        text = " ".join(b.bullets + b.stack_comments)
        overlap = sorted(jd & _tokens(text))
        rows.append((b.key, len(overlap), overlap))
    rows.sort(key=lambda r: r[1], reverse=True)

    print(f"{company}: project JD-keyword overlap (advisory; you pick the final set)")
    for key, n, overlap in rows:
        sample = ", ".join(overlap[:12])
        print(f"  {n:>3}  {key:<18} {sample}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Rank pool projects by JD overlap.")
    ap.add_argument("company", help="company stem under jobDescription/")
    args = ap.parse_args()
    return score(args.company)


if __name__ == "__main__":
    sys.exit(main())
