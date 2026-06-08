#!/usr/bin/env python3
"""Deterministic honesty linter for tailored resumes / cover letters.

This is the SINGLE SOURCE OF TRUTH for the mechanical FORBIDDEN list (the
module constants below). references/keywords.md and references/honesty-rules.md
point here; the markdown keeps only the *judgment* rules a human/LLM must apply
(category relabeling, IOE/FPT attribution, etc.).

It is advisory: it always exits 0 and prints either ``honesty: clean`` or
``honesty: FLAGS: [...]``. It scans only the honesty-bearing surface -- resume
bullet + skill-row text (never headings/layout, so phone numbers, URLs, and
geometry constants like 0.15/0.97 can't trip it) -- or, with --cover, only the
``why this company`` paragraph between the sentinel comments (never the fixed
body, which legitimately contains the teammate-attributed "XGBoost ... 93%").

Usage:
    python3 lint_honesty.py <company> [--cover]
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
OUTPUT = REPO_ROOT / "output"
JOBDESC = REPO_ROOT / "jobDescription"

# --- FORBIDDEN list (the one source of truth) ------------------------------- #
# Case-sensitive, word-boundary tech names with no defensible source.
FORBIDDEN_TECH = ["Java", "Kubernetes", "Rust", "Go", ".NET", "Angular", "Vue",
                  "Solana", "Spring", "RAG"]
# Case-insensitive scale claims Khoa's work never operated at.
FORBIDDEN_SCALE = ["large-scale", "production-grade", "high-throughput"]
# Case-insensitive generic resume buzzwords.
BUZZWORDS = ["spearheaded", "leveraged", "owned", "world-class", "10x",
             "best-in-class", "synergize"]

# PR-Pilot either/or cold-email bullets: these distinguish the two forms.
PRPILOT_LONG_SIG = "Perplexity-assisted"
PRPILOT_SHORT_SIG = "Validated by cold-emailing"

WHY_START = "% @lint:why-company-start"
WHY_END = "% @lint:why-company-end"


def forbidden_hits(text: str) -> list[str]:
    hits: list[str] = []
    for tok in FORBIDDEN_TECH:
        if re.search(r"(?<![A-Za-z0-9.])" + re.escape(tok) + r"(?![A-Za-z0-9])", text):
            hits.append(f"forbidden tech '{tok}'")
    low = text.lower()
    for phrase in FORBIDDEN_SCALE:
        if phrase in low:
            hits.append(f"scale claim '{phrase}'")
    for word in BUZZWORDS:
        if re.search(r"\b" + re.escape(word) + r"\b", text, re.IGNORECASE):
            hits.append(f"buzzword '{word}'")
    return hits


def lint_resume(company: str) -> list[str]:
    resume = (OUTPUT / company / "resume.tex")
    if not resume.exists():
        return [f"missing {resume.relative_to(REPO_ROOT)}"]
    tex = resume.read_text(encoding="utf-8")
    bullets = tex_util.resume_items(tex)
    skills = [c for _, c in tex_util.extract_skill_rows(tex)]
    scan = " \n ".join([tex_util.replace_href(b) for b in bullets] + skills)

    flags = forbidden_hits(scan)

    # Rule "agent": resume says agent/agentic but the JD never does.
    jd_path = JOBDESC / f"{company}.txt"
    jd_low = jd_path.read_text(encoding="utf-8").lower() if jd_path.exists() else ""
    if re.search(r"\bagent(ic)?\b", scan, re.IGNORECASE) and "agent" not in jd_low:
        flags.append("'agent/agentic' used but JD never mentions it")

    # Rule numbers: every number in an output bullet must trace to the master.
    master = MASTER.read_text(encoding="utf-8")
    master_nums = set(tex_util.numbers_in(master))
    out_nums: set[str] = set()
    for b in bullets:
        out_nums |= set(tex_util.numbers_in(b))
    strays = sorted(out_nums - master_nums)
    if strays:
        flags.append(f"numbers not traceable to master: {', '.join(strays)}")

    # PR-Pilot either/or: never ship both the long and short cold-email bullet.
    if PRPILOT_LONG_SIG in scan and PRPILOT_SHORT_SIG in scan:
        flags.append("both PR-Pilot cold-email bullets present (use exactly one)")

    return flags


def lint_cover(company: str) -> list[str]:
    cover = (OUTPUT / company / "cover_letter.tex")
    if not cover.exists():
        return [f"missing {cover.relative_to(REPO_ROOT)}"]
    tex = cover.read_text(encoding="utf-8")
    i = tex.find(WHY_START)
    j = tex.find(WHY_END)
    if i == -1 or j == -1 or j < i:
        return [f"why-company sentinels ({WHY_START} / {WHY_END}) not found"]
    why = tex[i + len(WHY_START):j]
    return forbidden_hits(why)


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic honesty linter (advisory).")
    ap.add_argument("company", help="company stem under output/")
    ap.add_argument("--cover", action="store_true",
                    help="lint the cover letter's why-company paragraph only")
    args = ap.parse_args()

    flags = lint_cover(args.company) if args.cover else lint_resume(args.company)
    label = "cover" if args.cover else "resume"
    if flags:
        print(f"honesty ({label}): FLAGS: [{'; '.join(flags)}]")
    else:
        print(f"honesty ({label}): clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
