#!/usr/bin/env python3
"""Recompile every example_output/*/cover_letter.md into Khoa_Ngo_cover_letter.pdf.

The ## Company insights block (audit metadata for Khoa) is stripped before
conversion: from the `## Company insights` heading through and including the
first `---` horizontal rule that follows it.

Usage:
  python rebuild_cover_letter.py             # build all
  python rebuild_cover_letter.py <company>   # build only example_output/<company>/cover_letter.md
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXAMPLES = ROOT / "example_output"
JOBNAME = "Khoa_Ngo_cover_letter"

INSIGHTS_RE = re.compile(
    r"^##\s+Company insights\b.*?^---\s*$\n?",
    re.DOTALL | re.MULTILINE,
)


def strip_insights(md_text: str) -> str:
    return INSIGHTS_RE.sub("", md_text, count=1).lstrip()


def build(md: Path) -> bool:
    out_dir = md.parent
    out_pdf = out_dir / f"{JOBNAME}.pdf"
    stripped = strip_insights(md.read_text(encoding="utf-8"))
    with tempfile.NamedTemporaryFile(
        "w", suffix=".md", dir=out_dir, delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(stripped)
        tmp_path = Path(tmp.name)
    cmd = [
        "pandoc",
        str(tmp_path),
        "-o",
        str(out_pdf),
        "--pdf-engine=pdflatex",
        "-V",
        "geometry:margin=1in",
        "-V",
        "fontsize=11pt",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  FAILED ({md})")
            tail = (result.stderr or result.stdout or "").splitlines()[-30:]
            print("\n".join(tail))
            return False
        return True
    finally:
        tmp_path.unlink(missing_ok=True)


def main() -> int:
    missing = [t for t in ("pandoc", "pdflatex") if not shutil.which(t)]
    if missing:
        print(f"missing on PATH: {', '.join(missing)}", file=sys.stderr)
        print("install: sudo apt update && sudo apt install -y pandoc texlive-latex-recommended texlive-fonts-recommended", file=sys.stderr)
        return 2

    if len(sys.argv) > 2:
        print("usage: rebuild_cover_letter.py [<company>]", file=sys.stderr)
        return 2

    if len(sys.argv) == 2:
        company = sys.argv[1]
        md = EXAMPLES / company / "cover_letter.md"
        if not md.exists():
            print(f"not found: {md}", file=sys.stderr)
            return 1
        md_files = [md]
    else:
        md_files = sorted(EXAMPLES.glob("*/cover_letter.md"))
        if not md_files:
            print(f"No cover_letter.md files under {EXAMPLES}")
            return 1

    failures = 0
    for md in md_files:
        print(f"Building {md.relative_to(ROOT)} -> {JOBNAME}.pdf")
        if not build(md):
            failures += 1
    print(f"\nDone. {len(md_files) - failures}/{len(md_files)} succeeded.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
