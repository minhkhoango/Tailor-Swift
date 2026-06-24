#!/usr/bin/env python3
"""The skill's shared pdflatex compile core.

One home for the multi-pass ``pdflatex`` run and the aux-file cleanup. Both the
PostToolUse chain (``tailor_hook.py``) and the live watcher (``watch.py``)
compile in-process through :func:`compile_tex` — neither shells out.

The root user-convenience scripts (``build_resume.py`` / ``build_cover_letter.py``
at the repo root) are deliberately standalone and carry their OWN copy of this
logic; they do not import this module, so the skill stays self-contained.

Public surface:
    compile_tex(tex, jobname, passes) -> True on success (PDF built, aux cleaned)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

AUX_EXTS = (".aux", ".log", ".out", ".synctex.gz", ".fls", ".fdb_latexmk", ".toc", ".bbl", ".blg")


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
