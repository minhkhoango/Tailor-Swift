#!/usr/bin/env python3
"""The /tailor deterministic chain, as one testable module.

The chain that IS the product -- assemble the slot file into ``resume.tex``,
compile it, measure the 1-page fit, lint honesty -- used to live only inside the
``post_save_build.py`` PostToolUse hook, invoked as four subprocesses whose rich
results (the ``FitReport`` dataclass, the honesty flags) were flattened to text
and scraped back out of stdout.

It now lives here behind one interface:

    assemble_and_check(company) -> Report     # slot-file save: assemble, then build+check
    build_and_check(company)    -> Report     # direct resume.tex save: build+check
    cover_check(company)        -> Report     # cover_letter.tex save: build, page-check, lint

A ``Report`` carries the structured fit result and honesty flags AND the human
text the hook surfaces -- so the hook is a thin adapter (stdin JSON in,
additionalContext out) and the chain is exercised in-process by the test suite.

Most stages run in-process (assemble + honesty are pure stdlib; the pdflatex
build is captured from ``latex_build.compile_tex``). Only the fit check stays a
subprocess: it needs pdfplumber from ``.venv``, which the hook's own interpreter
may lack. It is invoked with ``check_resume_fit.py --json`` and returns a parsed
report, never scraped text.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import assemble_resume
import lint_honesty
import slots as slots_mod
from assemble_resume import AssembleError
from paths import OUTPUT, REPO_ROOT, SCRIPTS, SRC, VENV_PY
from slots import SlotsError

# latex_build lives in src/ (the build layer); put it on the path to import it.
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
import latex_build  # noqa: E402

RESUME_JOBNAME = "Khoa_Ngo_resume"
COVER_JOBNAME = "Khoa_Ngo_cover_letter"
CHECKER = SCRIPTS / "check_resume_fit.py"


@dataclass
class Report:
    """Outcome of one chain run: structured result + the human text to surface."""
    company: str
    kind: str                       # "resume" | "cover"
    ok: bool
    lines: list[str]
    fit: dict[str, Any] | None = None
    honesty: list[str] = field(default_factory=list[str])

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _venv_py() -> str:
    """The pdfplumber-equipped interpreter for the fit check, else system python."""
    return str(VENV_PY) if VENV_PY.exists() else "python3"


def _run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def _compile(tex: Path, jobname: str, passes: int) -> tuple[bool, str]:
    """Compile in-process via latex_build, capturing its failure tail as text."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = latex_build.compile_tex(tex, jobname, passes)
    return ok, buf.getvalue().strip()


def _fit_json(company: str) -> tuple[dict[str, Any] | None, str]:
    """Run the fit checker in --json mode; return (parsed_report, human_text)."""
    _, out = _run([_venv_py(), str(CHECKER), "--json", company])
    try:
        data: Any = json.loads(out)
    except ValueError:
        return None, out or "fit check produced no output"
    if not isinstance(data, dict):
        return None, out
    d = cast("dict[str, Any]", data)
    if "error" in d:
        return None, str(d["error"])
    return d, str(d.get("text", ""))


def build_and_check(company: str) -> Report:
    """Compile resume.tex, measure fit, lint honesty -> Report (no assemble step)."""
    out_dir = OUTPUT / company
    ok_c, log = _compile(out_dir / "resume.tex", RESUME_JOBNAME, 2)
    if not ok_c:
        return Report(company, "resume", False,
                      [f"resume.tex for {company} FAILED to compile:", log[-800:]])
    fit, fit_text = _fit_json(company)
    honesty = lint_honesty.lint_resume(company)
    fit_ok = bool(fit and fit.get("ok"))
    lines = [f"{company} resume recompiled; deterministic fit check:",
             fit_text, lint_honesty.report_line(honesty, "resume")]
    return Report(company, "resume", fit_ok and not honesty, lines, fit, honesty)


def assemble_and_check(company: str) -> Report:
    """Assemble resume.tex from the slot file, then build + check it."""
    force = slots_mod.read_force(company)
    try:
        assemble_resume.assemble(company, force)
    except (AssembleError, SlotsError) as e:
        return Report(company, "resume", False,
                      [f"assemble failed for {company}; not building:", str(e)])
    rep = build_and_check(company)
    rep.lines = [f"{company} assembled from slots."] + rep.lines
    return rep


def cover_check(company: str) -> Report:
    """Compile cover_letter.tex, flag a >1-page spill, honesty-lint the why-paragraph."""
    out_dir = OUTPUT / company
    ok_c, log = _compile(out_dir / "cover_letter.tex", COVER_JOBNAME, 1)
    if not ok_c:
        return Report(company, "cover", False,
                      [f"cover_letter.tex for {company} FAILED to compile:", log[-600:]])
    lines = [f"cover_letter.tex for {company} compiled."]
    cover_pdf = out_dir / f"{COVER_JOBNAME}.pdf"
    pc_code, pc_out = _run([_venv_py(), str(CHECKER), "--pages", str(cover_pdf)])
    overfull = pc_code == 0 and pc_out.strip().isdigit() and int(pc_out.strip()) > 1
    if overfull:
        lines.append(f"OVERFLOW: cover letter is {pc_out.strip()} pages (must be 1).")
    honesty = lint_honesty.lint_cover(company)
    lines.append(lint_honesty.report_line(honesty, "cover"))
    return Report(company, "cover", (not overfull) and not honesty, lines, None, honesty)
