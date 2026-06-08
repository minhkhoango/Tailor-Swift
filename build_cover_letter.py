#!/usr/bin/env python3
"""Compile cover letters (output/<company>/cover_letter.tex -> Khoa_Ngo_cover_letter.pdf).

Cover letters are standalone Jake-style LaTeX, compiled directly with pdflatex --
no pandoc, no markdown. The "% Company insights" audit block lives as LaTeX
comments at the top of the .tex, so it never renders.

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

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
JOBNAME = "Khoa_Ngo_cover_letter"
SOURCE = "cover_letter.tex"
AUX_EXTS = (".aux", ".log", ".out", ".synctex.gz", ".fls", ".fdb_latexmk", ".toc", ".bbl", ".blg")


def all_companies() -> list[Path]:
    """Sorted output/ subdirs that actually contain a cover_letter.tex."""
    if not OUTPUT.is_dir():
        return []
    return sorted((d for d in OUTPUT.iterdir() if d.is_dir() and (d / SOURCE).exists()),
                  key=lambda d: d.name.lower())


def companies_matching(prefix: str | None) -> list[Path]:
    dirs = all_companies()
    if prefix is None:
        return dirs
    p = prefix.lower()
    return [d for d in dirs if d.name.lower().startswith(p)]


def build(tex: Path) -> bool:
    out_dir = tex.parent
    cmd = [
        "pdflatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-jobname={JOBNAME}",
        f"-output-directory={out_dir}",
        tex.name,
    ]
    result = subprocess.run(cmd, cwd=out_dir, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  FAILED ({tex})")
        tail = (result.stdout or "").splitlines()[-30:]
        print("\n".join(tail))
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
            avail = ", ".join(d.name for d in all_companies()) or "(none yet)"
            print(f'No cover letter under output/ starts with "{prefix}". Available: {avail}')
        return 1

    failures = 0
    for d in targets:
        tex = d / SOURCE
        print(f"Building {tex.relative_to(ROOT)} -> {JOBNAME}.pdf")
        if not build(tex):
            failures += 1
    print(f"\nDone. {len(targets) - failures}/{len(targets)} succeeded.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
