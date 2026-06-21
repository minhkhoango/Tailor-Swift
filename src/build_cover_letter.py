#!/usr/bin/env python3
"""Compile cover letters (output/<company>/cover_letter.tex -> Khoa_Ngo_cover_letter.pdf).

Thin adapter over latex_build. Cover letters are standalone Jake-style LaTeX,
compiled directly with pdflatex (no pandoc, no markdown) in a single pass -- the
"% Company insights" audit block lives as LaTeX comments at the top of the .tex,
so it never renders.

Usage:
  python3 build_cover_letter.py            # build every output/*/cover_letter.tex
  python3 build_cover_letter.py A          # every company starting with "A"
  python3 build_cover_letter.py Apple      # just Apple

The argument is a case-insensitive PREFIX, so a short stem can fan out to several
companies. No match prints a one-line message listing what's available.
"""

from __future__ import annotations

import sys

import latex_build

if __name__ == "__main__":
    sys.exit(latex_build.run_cli(
        prog="build_cover_letter.py",
        jobname="Khoa_Ngo_cover_letter",
        source="cover_letter.tex",
        passes=1,
        first_hint="run /tailor --cover first",
        prefix_noun="cover letter",
    ))
