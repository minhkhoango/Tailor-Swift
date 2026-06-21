#!/usr/bin/env python3
"""Compile tailored resumes (output/<company>/resume.tex -> Khoa_Ngo_resume.pdf).

Thin adapter over latex_build: resumes compile with two pdflatex passes so refs
and outlines settle.

Usage:
  python3 build_resume.py            # build every output/*/resume.tex
  python3 build_resume.py A          # build every company starting with "A"
  python3 build_resume.py Apple      # build just Apple

The argument is a case-insensitive PREFIX, so a short stem can fan out to
several companies (e.g. "A" -> Apple and Asana). No match prints a one-line
message listing what's available -- no traceback.
"""

from __future__ import annotations

import sys

import latex_build

if __name__ == "__main__":
    sys.exit(latex_build.run_cli(
        prog="build_resume.py",
        jobname="Khoa_Ngo_resume",
        source="resume.tex",
        passes=2,
        first_hint="run /tailor first",
        prefix_noun="company",
    ))
