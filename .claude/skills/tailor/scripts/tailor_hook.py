#!/usr/bin/env python3
"""PostToolUse hook + the deterministic /tailor chain, in one module.

The normal /tailor flow writes a small ``output/<company>/resume.slots.json``.
Saving it fires this PostToolUse hook, which runs the whole deterministic chain
WITHOUT Claude invoking anything and feeds the combined fit + honesty report back
as additionalContext. This file is BOTH the hook adapter and the chain:

  * the chain -- assemble the slot file into ``resume.tex``, compile it, measure
    the 1-page fit, run the deterministic honesty check -- exposed as
    ``assemble_and_check`` / ``build_and_check`` / ``cover_check`` (exercised
    in-process by the test suite, no hook needed), and
  * the hook -- read the tool-call JSON on stdin, classify the saved path
    (``slots`` / ``resume`` / ``cover``) via :func:`paths.classify_output`,
    dispatch, and emit the Report text. Never blocks the tool call (exits 0).

Most stages run in-process (assemble + honesty are pure stdlib; the pdflatex
build is captured from ``pdf_compile.compile_tex``). Only the fit check stays a
subprocess: it needs pdfplumber from ``.venv``, which the hook's own interpreter
may lack. It is invoked with ``check_resume_fit.py --json`` and returns a parsed
report, never scraped text.

HONESTY here is only the one check an LLM self-audit silently misses:
number-traceability (every number in an output bullet traces to a *selected*
master block). The FORBIDDEN-tech / scale / buzzword / "agentic" rules are a
checklist the model applies from ``references/honesty-rules.md`` -- they are NOT
linted here.

The report also carries a STRUCTURE advisory: a tailored resume always has exactly
three projects, so a slot file with any other count gets a non-blocking WARN line
(the page-fit verdict stays the real gate).

Wired in .claude/settings.json under hooks.PostToolUse (matcher Write|Edit|...).
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

import pdf_compile
import tex_parse
from assemble_resume import AssembleError, SlotsError, assemble, load_slots
from paths import MASTER, OUTPUT, REPO_ROOT, SCRIPTS, VENV_PY, classify_output

RESUME_JOBNAME = "Khoa_Ngo_resume"
COVER_JOBNAME = "Khoa_Ngo_cover_letter"
CHECKER = SCRIPTS / "check_resume_fit.py"

# A tailored resume always carries exactly this many projects (SKILL.md golden
# rule). Off-by-one is advisory, not fatal -- the page-fit verdict is the real
# gate -- but it is surfaced so the model packs/prunes to three before relying
# on fullness alone.
EXPECTED_PROJECTS = 3


# --------------------------------------------------------------------------- #
# Honesty: the one deterministic check the model can't reliably self-audit
# --------------------------------------------------------------------------- #
def _traceable_numbers(company: str, blocks: dict[str, tex_parse.Block]) -> set[str]:
    """Numbers an output bullet may legitimately carry: those in the master
    bullets + headings of the *selected* experiences/projects.

    Scoped from the slot file when present (falls back to every master block
    otherwise). Deliberately EXCLUDES the master preamble geometry constants and
    the contact line's phone number -- numbers a fabricated metric must not be
    able to borrow -- and excludes unselected projects, so a figure unique to an
    unshipped project is flagged rather than waved through.
    """
    try:
        keys: list[str] | None = [k for k in load_slots(company).selected_keys if k in blocks]
    except SlotsError:
        keys = None  # no/invalid slot file -> fall back to every master block
    chosen = [blocks[k] for k in keys] if keys else list(blocks.values())
    nums: set[str] = set()
    for blk in chosen:
        nums |= set(tex_parse.numbers_in(blk.heading))
        for bullet in blk.bullets:
            nums |= set(tex_parse.numbers_in(bullet))
    return nums


def honesty_flags(company: str) -> list[str]:
    """Deterministic honesty flags for a tailored resume (advisory, never blocks).

    One check only: every number in an output bullet must trace to a master
    bullet/heading of a *selected* block. The rest of the honesty audit is the
    model's, from honesty-rules.md.

    Scoped to the EXPERIENCE marker onward. Education lives in the preamble above
    it and carries static \\resumeItem numbers (ICPC placement, year, team count)
    that are constants of the resume, not selectable facts -- so they neither
    trace to nor need to trace to any master block. Scanning them would false-flag
    every single tailored resume; the slice excludes them.
    """
    resume = OUTPUT / company / "resume.tex"
    if not resume.exists():
        return [f"missing {resume.relative_to(REPO_ROOT)}"]
    tex = resume.read_text(encoding="utf-8")
    exp = tex.find("%-----------EXPERIENCE-----------")
    bullets = tex_parse.resume_items(tex[exp:] if exp != -1 else tex)

    flags: list[str] = []
    blocks = tex_parse.parse_master(MASTER.read_text(encoding="utf-8"))
    master_nums = _traceable_numbers(company, blocks)
    out_nums: set[str] = set()
    for b in bullets:
        out_nums |= set(tex_parse.numbers_in(b))
    strays = sorted(out_nums - master_nums)
    if strays:
        flags.append(f"numbers not traceable to master: {', '.join(strays)}")
    return flags


def honesty_line(flags: list[str]) -> str:
    """One-line honesty verdict."""
    return f"honesty: FLAGS [{'; '.join(flags)}]" if flags else "honesty: clean"


def structure_segment(company: str) -> tuple[bool, str | None]:
    """Project-count advisory for a slot-driven resume: ``(is_warning, line)``.

    A tailored resume always carries exactly ``EXPECTED_PROJECTS`` projects. We
    read the count from the slot file; when it differs, the returned line is a
    WARN the model should act on (add or drop a project) before leaning on the
    fullness number alone. Returns ``(False, None)`` when there is no/invalid
    slot file (e.g. a direct ``resume.tex`` write) -- nothing to count, so no
    structure segment is emitted at all.
    """
    try:
        n = len(load_slots(company).projects)
    except SlotsError:
        return (False, None)
    if n != EXPECTED_PROJECTS:
        return (True, f"structure: WARN {n} projects (must be {EXPECTED_PROJECTS}; "
                      f"add or drop one to hit {EXPECTED_PROJECTS})")
    return (False, f"structure: {n} projects")


# --------------------------------------------------------------------------- #
# The chain
# --------------------------------------------------------------------------- #
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
    """Compile in-process via pdf_compile, capturing its failure tail as text."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = pdf_compile.compile_tex(tex, jobname, passes)
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
    """Compile resume.tex, measure fit, run honesty checks -> Report (no assemble)."""
    out_dir = OUTPUT / company
    ok_c, log = _compile(out_dir / "resume.tex", RESUME_JOBNAME, 2)
    if not ok_c:
        return Report(company, "resume", False,
                      [f"resume.tex for {company} FAILED to compile:", log[-800:]])
    fit, fit_text = _fit_json(company)
    honesty = honesty_flags(company)
    struct_warn, s_line = structure_segment(company)
    fit_ok = bool(fit and fit.get("ok"))
    ok = fit_ok and not honesty   # advisory project-count WARN does NOT flip ok
    h_line = honesty_line(honesty)
    segments = [h_line] + ([s_line] if s_line else [])
    # Clean fit + honesty AND exactly three projects -> one compact line.
    # Anything actionable (incl. a structure WARN) -> fit + each advisory on its own line.
    if ok and not struct_warn:
        lines = [f"{fit_text}  |  " + "  |  ".join(segments)]
    else:
        lines = [fit_text, *segments]
    return Report(company, "resume", ok, lines, fit, honesty)


def assemble_and_check(company: str) -> Report:
    """Assemble resume.tex from the slot file, then build + check it."""
    try:
        assemble(company)
    except (AssembleError, SlotsError) as e:
        return Report(company, "resume", False,
                      [f"assemble failed for {company}; not building:", str(e)])
    return build_and_check(company)


def cover_check(company: str) -> Report:
    """Compile cover_letter.tex and flag a >1-page spill.

    The why-paragraph's honesty (no fabricated company facts) is the model's job
    per references/cover-letter.md -- nothing deterministic to lint here.
    """
    out_dir = OUTPUT / company
    ok_c, log = _compile(out_dir / "cover_letter.tex", COVER_JOBNAME, 1)
    if not ok_c:
        return Report(company, "cover", False,
                      [f"cover_letter.tex for {company} FAILED to compile:", log[-600:]])
    cover_pdf = out_dir / f"{COVER_JOBNAME}.pdf"
    pc_code, pc_out = _run([_venv_py(), str(CHECKER), "--pages", str(cover_pdf)])
    overfull = pc_code == 0 and pc_out.strip().isdigit() and int(pc_out.strip()) > 1
    if overfull:
        return Report(company, "cover", False,
                      [f"OVERFLOW: {company} cover letter is {pc_out.strip()} pages (must be 1)."])
    return Report(company, "cover", True, [f"{company} cover_letter: OK 1 page."])


# --------------------------------------------------------------------------- #
# Hook adapter
# --------------------------------------------------------------------------- #
def emit(context: str) -> None:
    """Surface text back to Claude as PostToolUse additional context."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": context,
        }
    }))


def main() -> int:
    try:
        payload: Any = json.loads(sys.stdin.read())
        tool_input: Any = payload.get("tool_input") or {}
        file_path: Any = tool_input.get("file_path")
    except (ValueError, TypeError, AttributeError):
        return 0
    if not isinstance(file_path, str):
        return 0

    target = classify_output(file_path)
    if target is None:
        return 0
    company, kind = target

    if kind == "slots":
        emit(f"[tailor hook] {assemble_and_check(company).text}")
    elif kind == "resume":
        emit("[tailor hook] (direct resume.tex write -- prefer editing the slot file) "
             f"{build_and_check(company).text}")
    else:  # cover
        emit(f"[tailor hook] {cover_check(company).text}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never let a hook bug block Claude's tool call
        print(f"[tailor hook] non-fatal error: {exc}", file=sys.stderr)
        sys.exit(0)
