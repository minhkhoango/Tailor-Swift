#!/usr/bin/env python3
"""Shared pdflatex compile core for the root build scripts.

One home for the company prefix-matching, the multi-pass ``pdflatex`` run, and
the aux-file cleanup that ``build_resume.py`` and ``build_cover_letter.py`` used
to carry as near-identical copies. Those two scripts are now thin adapters that
call :func:`run_cli` with their own jobname / source / pass-count.

Public surface:
    companies_matching(prefix, source) -> [output/<co> dirs that hold `source`]
    compile_tex(tex, jobname, passes)  -> True on success (PDF built, aux cleaned)
    run_cli(prog, jobname, source, passes, first_hint, prefix_noun) -> exit code
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# The repo layout is owned once by the tailor layer's paths.py; import it rather
# than re-deriving OUTPUT here. The skill scripts dir is added to the path so a
# bare ``python3 src/build_resume.py`` (sys.path[0] == src/) can still find it.
_SCRIPTS = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "tailor" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from paths import OUTPUT, REPO_ROOT as ROOT  # noqa: E402

AUX_EXTS = (".aux", ".log", ".out", ".synctex.gz", ".fls", ".fdb_latexmk", ".toc", ".bbl", ".blg")


def companies_matching(prefix: str | None, source: str) -> list[Path]:
    """Sorted output/ subdirs that contain `source`, optionally prefix-filtered.

    `prefix` is a case-insensitive stem, so a short stem can fan out to several
    companies (``"A"`` -> Apple and Asana). ``None`` returns every match.
    """
    if not OUTPUT.is_dir():
        return []
    dirs = sorted((d for d in OUTPUT.iterdir() if d.is_dir() and (d / source).exists()),
                  key=lambda d: d.name.lower())
    if prefix is None:
        return dirs
    p = prefix.lower()
    return [d for d in dirs if d.name.lower().startswith(p)]


def compile_tex(tex: Path, jobname: str, passes: int) -> bool:
    """Compile `tex` to `<jobname>.pdf` with `passes` pdflatex runs, then clean aux.

    Two passes let refs/outlines settle (resumes); cover letters need only one.
    On failure prints the last 30 stdout lines and returns False without cleanup.
    """
    out_dir = tex.parent
    cmd = [
        "pdflatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-jobname={jobname}",
        f"-output-directory={out_dir}",
        tex.name,
    ]
    for _ in range(passes):
        result = subprocess.run(cmd, cwd=out_dir, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  FAILED ({tex})")
            print("\n".join((result.stdout or "").splitlines()[-30:]))
            return False
    for ext in AUX_EXTS:
        f = out_dir / f"{jobname}{ext}"
        if f.exists():
            f.unlink()
    missfont = out_dir / "missfont.log"
    if missfont.exists():
        missfont.unlink()
    return True


def run_cli(prog: str, jobname: str, source: str, passes: int,
            first_hint: str, prefix_noun: str) -> int:
    """Full CLI for a build script: parse one optional prefix arg, compile matches.

    `prog` names the script for the usage line; `first_hint` is the no-output
    suggestion (e.g. "run /tailor first"); `prefix_noun` is what a missing prefix
    match is called ("company" / "cover letter"). Mirrors the old per-script main:
    exit 2 on bad usage / missing pdflatex, 1 on no match or a compile failure.
    """
    if not shutil.which("pdflatex"):
        print("pdflatex not found on PATH — install TeX Live "
              "(texlive-latex-recommended texlive-fonts-recommended texlive-latex-extra).")
        return 2
    if len(sys.argv) > 2:
        print(f"usage: {prog} [<company-prefix>]")
        return 2

    prefix = sys.argv[1] if len(sys.argv) == 2 else None
    targets = companies_matching(prefix, source)

    if not targets:
        if prefix is None:
            print(f"No {source} files found under {OUTPUT}/ — {first_hint}.")
        else:
            avail = ", ".join(d.name for d in companies_matching(None, source)) or "(none yet)"
            print(f'No {prefix_noun} under output/ starts with "{prefix}". Available: {avail}')
        return 1

    failures = 0
    for d in targets:
        tex = d / source
        print(f"Building {tex.relative_to(ROOT)} -> {jobname}.pdf")
        if not compile_tex(tex, jobname, passes):
            failures += 1
    print(f"\nDone. {len(targets) - failures}/{len(targets)} succeeded.")
    return 0 if failures == 0 else 1
