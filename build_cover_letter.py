#!/usr/bin/env python3
"""Compile cover letters (output/<company>/cover_letter.tex -> Khoa_Ngo_cover_letter.pdf).

A standalone user convenience tool — run it by hand to (re)build cover-letter
PDFs outside a /tailor turn. It is deliberately self-contained: it imports
nothing from the tailor skill, so the skill stays self-contained too. (The
skill's own chain compiles in-process via its own copy of this logic.)

Cover letters are standalone Jake-style LaTeX, compiled directly with pdflatex
(no pandoc, no markdown) in a single pass -- the "% Company insights" audit block
lives as LaTeX comments at the top of the .tex, so it never renders.

Usage:
  python3 build_cover_letter.py            # build every output/*/cover_letter.tex
  python3 build_cover_letter.py A          # every company starting with "A"
  python3 build_cover_letter.py Apple      # just Apple

The argument is a case-insensitive PREFIX, so a short stem can fan out to several
companies. No match prints a one-line message listing what's available.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

JOBNAME = "Khoa_Ngo_cover_letter"
SOURCE = "cover_letter.tex"
PASSES = 1  # cover letters need only one pass

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
AUX_EXTS = (".aux", ".log", ".out", ".synctex.gz", ".fls", ".fdb_latexmk", ".toc", ".bbl", ".blg")


def companies_matching(prefix: str | None) -> list[Path]:
    """Sorted output/ subdirs that contain SOURCE, optionally prefix-filtered.

    `prefix` is a case-insensitive stem, so a short stem can fan out to several
    companies (``"A"`` -> Apple and Asana). ``None`` returns every match.
    """
    if not OUTPUT.is_dir():
        return []
    dirs = sorted((d for d in OUTPUT.iterdir() if d.is_dir() and (d / SOURCE).exists()),
                  key=lambda d: d.name.lower())
    if prefix is None:
        return dirs
    p = prefix.lower()
    return [d for d in dirs if d.name.lower().startswith(p)]


def compile_tex(tex: Path) -> bool:
    """Compile `tex` to `<JOBNAME>.pdf` with PASSES pdflatex runs, then clean aux.

    On failure prints the last 30 stdout lines and returns False without cleanup.
    """
    out_dir = tex.parent
    cmd = [
        "pdflatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-jobname={JOBNAME}",
        f"-output-directory={out_dir}",
        tex.name,
    ]
    for _ in range(PASSES):
        result = subprocess.run(cmd, cwd=out_dir, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  FAILED ({tex})")
            print("\n".join((result.stdout or "").splitlines()[-30:]))
            return False
    for ext in AUX_EXTS:
        f = out_dir / f"{JOBNAME}{ext}"
        if f.exists():
            f.unlink()
    missfont = out_dir / "missfont.log"
    if missfont.exists():
        missfont.unlink()
    return True


def main() -> int:
    """Parse one optional prefix arg, compile every matching cover letter.

    Exit 2 on bad usage / missing pdflatex, 1 on no match or a compile failure.
    """
    if not shutil.which("pdflatex"):
        print("pdflatex not found on PATH — install TeX Live "
              "(texlive-latex-recommended texlive-fonts-recommended texlive-latex-extra).")
        return 2
    if len(sys.argv) > 2:
        print("usage: build_cover_letter.py [<company-prefix>]")
        return 2

    prefix = sys.argv[1] if len(sys.argv) == 2 else None
    targets = companies_matching(prefix)
    if not targets:
        if prefix is None:
            print(f"No {SOURCE} files found under {OUTPUT}/ — run /tailor --cover first.")
        else:
            avail = ", ".join(d.name for d in companies_matching(None)) or "(none yet)"
            print(f'No cover letter under output/ starts with "{prefix}". Available: {avail}')
        return 1

    failures = 0
    for d in targets:
        tex = d / SOURCE
        print(f"Building {tex.relative_to(ROOT)} -> {JOBNAME}.pdf")
        if not compile_tex(tex):
            failures += 1
    print(f"\nDone. {len(targets) - failures}/{len(targets)} succeeded.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
