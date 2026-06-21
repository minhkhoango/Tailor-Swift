#!/usr/bin/env python3
"""PostToolUse hook: auto-assemble + compile + fit/honesty-check on saves.

The normal /tailor flow is to write a small ``output/<company>/resume.slots.json``;
this hook then runs the whole deterministic chain WITHOUT Claude invoking
anything: assemble_resume.py -> build_resume.py -> check_resume_fit.py ->
lint_honesty.py, feeding the combined fit + honesty report back as
additionalContext. Direct ``resume.tex`` writes are still honored (skip the
assemble step) but discouraged -- edit the slot, not the tex.
``output/<company>/cover_letter.tex`` is compiled via build_cover_letter.py,
flagged if it spills past one page, and honesty-linted (why-company only).

Wired in .claude/settings.json under hooks.PostToolUse (matcher Write|Edit|...).
Reads the tool-call JSON on stdin; no-ops silently for any other file, and never
blocks the tool call (always exits 0).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from paths import OUTPUT, REPO_ROOT, SCRIPTS, VENV_PY

CHECKER = SCRIPTS / "check_resume_fit.py"
ASSEMBLER = SCRIPTS / "assemble_resume.py"
LINTER = SCRIPTS / "lint_honesty.py"
COVER_JOBNAME = "Khoa_Ngo_cover_letter"


def emit(context: str) -> None:
    """Surface text back to Claude as PostToolUse additional context."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": context,
        }
    }))


def classify(file_path: str) -> tuple[str, str] | None:
    """Return (company, kind) for output/<company>/{resume.slots.json,resume.tex,cover_letter.tex}."""
    p = Path(file_path)
    if p.name == "resume.slots.json":
        kind = "slots"
    elif p.name == "resume.tex":
        kind = "resume"
    elif p.name == "cover_letter.tex":
        kind = "cover"
    else:
        return None
    parent = p.parent
    if parent.parent.resolve() != OUTPUT.resolve():
        return None
    return (parent.name, kind)


def run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def venv_py() -> str:
    return str(VENV_PY) if VENV_PY.exists() else "python3"


def build_and_check(company: str) -> str:
    """Compile resume.tex, run the fit checker + honesty linter, return a report."""
    code, out = run(["python3", "build_resume.py", company])
    if code != 0:
        return f"resume.tex for {company} FAILED to compile:\n{out[-800:]}"
    _, fit = run([venv_py(), str(CHECKER), company])
    _, honesty = run(["python3", str(LINTER), company])
    return f"{company} resume recompiled; deterministic fit check:\n{fit}\n{honesty}"


def main() -> int:
    try:
        payload: Any = json.loads(sys.stdin.read())
        tool_input: Any = payload.get("tool_input") or {}
        file_path: Any = tool_input.get("file_path")
    except (ValueError, TypeError, AttributeError):
        return 0
    if not isinstance(file_path, str):
        return 0

    target = classify(file_path)
    if target is None:
        return 0
    company, kind = target

    if kind == "slots":
        cmd = ["python3", str(ASSEMBLER), company]
        # A re-tailor (baseline already captured) must opt in via "force": true in
        # the slot file, so the assembler won't otherwise clobber human edits.
        try:
            slots = json.loads((OUTPUT / company / "resume.slots.json").read_text(encoding="utf-8"))
            if isinstance(slots, dict) and cast("dict[str, Any]", slots).get("force"):
                cmd.append("--force")
        except (OSError, ValueError):
            pass
        code, out = run(cmd)
        if code != 0:
            emit(f"[tailor hook] assemble failed for {company}; not building:\n{out[-800:]}")
            return 0
        emit(f"[tailor hook] {company} assembled from slots. {build_and_check(company)}")
        return 0

    if kind == "resume":
        emit(f"[tailor hook] (direct resume.tex write -- prefer editing the slot file) "
             f"{build_and_check(company)}")
        return 0

    # kind == "cover"
    code, out = run(["python3", "build_cover_letter.py", company])
    if code != 0:
        emit(f"[tailor hook] cover_letter.tex for {company} FAILED to compile:\n{out[-600:]}")
        return 0
    notes: list[str] = [f"cover_letter.tex for {company} compiled."]
    cover_pdf = OUTPUT / company / f"{COVER_JOBNAME}.pdf"
    pc_code, pc_out = run([venv_py(), str(CHECKER), "--pages", str(cover_pdf)])
    if pc_code == 0 and pc_out.strip().isdigit() and int(pc_out.strip()) > 1:
        notes.append(f"OVERFLOW: cover letter is {pc_out.strip()} pages (must be 1).")
    _, honesty = run(["python3", str(LINTER), company, "--cover"])
    notes.append(honesty)
    emit("[tailor hook] " + "\n".join(notes))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never let a hook bug block Claude's tool call
        print(f"[tailor hook] non-fatal error: {exc}", file=sys.stderr)
        sys.exit(0)
