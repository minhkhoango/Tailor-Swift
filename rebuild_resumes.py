#!/usr/bin/env python3
"""Recompile every example_output/*/resume.tex into Khoa_Ngo_resume.pdf."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXAMPLES = ROOT / "example_output"
JOBNAME = "Khoa_Ngo_resume"
AUX_EXTS = (".aux", ".log", ".out", ".synctex.gz", ".fls", ".fdb_latexmk", ".toc", ".bbl", ".blg")


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
    # Two passes so refs/outlines settle.
    for _ in range(2):
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
        print("pdflatex not found on PATH", file=sys.stderr)
        return 2
    tex_files = sorted(EXAMPLES.glob("*/resume.tex"))
    if not tex_files:
        print(f"No resume.tex files under {EXAMPLES}")
        return 1
    failures = 0
    for tex in tex_files:
        print(f"Building {tex.relative_to(ROOT)} -> {JOBNAME}.pdf")
        if not build(tex):
            failures += 1
    print(f"\nDone. {len(tex_files) - failures}/{len(tex_files)} succeeded.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
