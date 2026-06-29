#!/usr/bin/env python3
"""The deterministic chain: slots -> assemble -> compile -> fit -> honesty -> Report.

This is the code half of /tailor, lifted out of the old PostToolUse hook. The
orchestrator hands it a slot dict and a working directory; it assembles the
``.tex``, compiles the PDF, measures the 1-page fit, runs the one deterministic
honesty check (number-traceability), and returns one combined :class:`Report`.

Everything runs in-process under the venv interpreter (which has pdfplumber), so
unlike the old hook there is no subprocess for the fit check. A scratch dir holds
in-flight passes; only the final accepted pass is copied to ``output/<stem>/``.

HONESTY here is only the check an LLM self-audit reliably misses: every number in
an output bullet must trace to a *selected* master block. The FORBIDDEN-tech /
scale / buzzword rules are the model's checklist from the master's ``% KEYWORD
LEDGER`` plus the ``SYSTEM_PROMPT`` golden rules -- not linted here. A tailored
resume always carries exactly three projects; any other count yields a
non-blocking ``structure: WARN`` (the fit verdict stays the gate).
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass, field
from pathlib import Path
from . import pdf_compile, tex_parse
from .capture import pretty_slots_json
from .assemble_resume import (
    AssembleError,
    Slots,
    SlotsData,
    SlotsError,
    assemble_to,
    parse_slots,
)
from .check_resume_fit import FitDict, analyze_dir
from .paths import MASTER, RESUME_JOBNAME, SLOTS_NAME

# A tailored resume always carries exactly this many projects (golden rule).
# Off-by-one is advisory, not fatal -- the page-fit verdict is the real gate.
EXPECTED_PROJECTS = 3


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
@dataclass
class Report:
    """Outcome of one chain pass: structured result + the human text to surface.

    ``ok`` is the loop-stop condition (fit OK *and* honesty clean). ``shippable``
    is the weaker bar the orchestrator accepts after the pass cap: a real PDF
    (verdict not ERROR) with clean honesty -- an accepted UNDERFULL still ships.
    Honesty is absolute: if it never clears, nothing ships (see the orchestrator).
    """
    stem: str
    verdict: str                       # OK / UNDERFULL / OVERFULL / MULTIPAGE / SPILLOVER / ERROR
    fill: float | None
    honesty_flags: list[str]
    structure_warn: bool
    flags: list[str] = field(default_factory=list[str])     # actionable fit lines
    uncovered: list[str] = field(default_factory=list[str])  # threaded from the model
    passes: int = 0
    text: str = ""                     # combined human report (becomes the next user turn)

    @property
    def ok(self) -> bool:
        return self.verdict == "OK" and not self.honesty_flags

    @property
    def shippable(self) -> bool:
        return self.verdict != "ERROR" and not self.honesty_flags


# --------------------------------------------------------------------------- #
# Honesty: number-traceability (the one deterministic check)
# --------------------------------------------------------------------------- #
def _traceable_numbers(slots: Slots, blocks: dict[str, tex_parse.Block]) -> set[str]:
    """Numbers an output bullet may legitimately carry: those in the master
    bullets + headings of the *selected* experiences/projects.

    Excludes the master preamble geometry constants and the contact phone number
    (a fabricated metric must not borrow them), and excludes unselected projects,
    so a figure unique to an unshipped project is flagged rather than waved through.
    """
    keys = [k for k in slots.selected_keys if k in blocks]
    chosen = [blocks[k] for k in keys] if keys else list(blocks.values())
    nums: set[str] = set()
    for blk in chosen:
        nums |= set(tex_parse.numbers_in(blk.heading))
        for bullet in blk.bullets:
            nums |= set(tex_parse.numbers_in(bullet))
    return nums


def honesty_flags(work_dir: Path, slots: Slots) -> list[str]:
    """Deterministic honesty flags for an assembled resume in ``work_dir``.

    One check: every number in an output bullet must trace to a master
    bullet/heading of a *selected* block. The rest of the honesty audit is the
    model's, from the ``SYSTEM_PROMPT`` golden rules.

    Scoped to the EXPERIENCE marker onward -- Education lives in the preamble and
    carries static numbers (ICPC placement, year, team count) that are constants
    of the resume, not selectable facts, so scanning them would false-flag every
    tailored resume.
    """
    resume = work_dir / "resume.tex"
    if not resume.exists():
        return [f"missing {resume.name}"]
    tex = resume.read_text(encoding="utf-8")
    exp = tex.find("%-----------EXPERIENCE-----------")
    bullets = tex_parse.resume_items(tex[exp:] if exp != -1 else tex)

    blocks = tex_parse.parse_master(MASTER.read_text(encoding="utf-8"))
    master_nums = _traceable_numbers(slots, blocks)
    out_nums: set[str] = set()
    for b in bullets:
        out_nums |= set(tex_parse.numbers_in(b))
    strays = sorted(out_nums - master_nums)
    if strays:
        return [f"numbers not traceable to master: {', '.join(strays)}"]
    return []


def honesty_line(flags: list[str]) -> str:
    return f"honesty: FLAGS [{'; '.join(flags)}]" if flags else "honesty: clean"


# --------------------------------------------------------------------------- #
# The chain
# --------------------------------------------------------------------------- #
def _compile(tex: Path, jobname: str, passes: int) -> tuple[bool, str]:
    """Compile in-process via pdf_compile, capturing its failure tail as text."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = pdf_compile.compile_tex(tex, jobname, passes)
    return ok, buf.getvalue().strip()


def _fit_flags(fit: FitDict) -> list[str]:
    """Pull the actionable lines (spillover FLAGs, skill WRAPs, notes) out of a
    fit report's human text -- everything after the headline line."""
    text = str(fit.get("text", ""))
    return [ln.strip() for ln in text.splitlines()[1:] if ln.strip()]


def run_chain(stem: str, slots_data: SlotsData, work_dir: Path) -> Report:
    """Assemble + compile + measure + honesty-check ``slots_data`` in ``work_dir``.

    Writes the slot file, then runs the deterministic chain. A slot/assemble error
    or a compile failure short-circuits to a ``verdict="ERROR"`` report carrying
    the message (so the model can react on the next pass). The shipped artifact is
    the final accepted ``resume.slots.json`` + PDF in ``work_dir``.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / SLOTS_NAME).write_text(pretty_slots_json(slots_data), encoding="utf-8")

    try:
        slots = parse_slots(slots_data)
    except SlotsError as e:
        return Report(stem, "ERROR", None, [], False, text=f"slot file invalid: {e}")

    struct_warn = len(slots.projects) != EXPECTED_PROJECTS
    s_line = (f"structure: WARN {len(slots.projects)} projects "
              f"(must be {EXPECTED_PROJECTS})" if struct_warn
              else f"structure: {len(slots.projects)} projects")

    try:
        assemble_to(slots, work_dir)
    except (AssembleError, SlotsError) as e:
        return Report(stem, "ERROR", None, [], struct_warn,
                      text=f"assemble failed: {e}\n{s_line}")

    ok_c, log = _compile(work_dir / "resume.tex", RESUME_JOBNAME, 2)
    if not ok_c:
        return Report(stem, "ERROR", None, [], struct_warn,
                      text=f"resume.tex FAILED to compile:\n{log[-800:]}\n{s_line}")

    from .check_resume_fit import report_to_dict
    fit = report_to_dict(analyze_dir(work_dir, stem))

    honesty = honesty_flags(work_dir, slots)
    h_line = honesty_line(honesty)
    fit_text = str(fit.get("text", ""))
    flags = _fit_flags(fit)

    verdict = "OK" if fit.get("ok") else str(fit.get("verdict", "ERROR"))
    fill = fit.get("fullness")

    # One compact line when everything's clean; otherwise headline + each advisory.
    if verdict == "OK" and not honesty and not struct_warn:
        text = f"{fit_text}  |  {h_line}"
    else:
        text = "\n".join([fit_text, h_line, s_line])

    return Report(stem, verdict, fill, honesty, struct_warn, flags, text=text)
