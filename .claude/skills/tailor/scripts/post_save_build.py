#!/usr/bin/env python3
"""PostToolUse hook: auto-compile + fit-check on resume/cover-letter saves.

When Claude writes output/<company>/resume.tex, this recompiles the PDF via
build_resume.py and runs check_resume_fit.py, then feeds the verdict back to
Claude as additionalContext -- so the fit loop runs WITHOUT Claude manually
invoking the checker. output/<company>/cover_letter.tex is recompiled via
build_cover_letter.py the same way.

Wired in .claude/settings.json under hooks.PostToolUse (matcher Write|Edit|...).
Reads the tool-call JSON on stdin; no-ops silently for any other file, and never
blocks the tool call (always exits 0).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
OUTPUT = REPO_ROOT / "output"
VENV_PY = REPO_ROOT / ".venv" / "bin" / "python"
CHECKER = REPO_ROOT / ".claude" / "skills" / "tailor" / "scripts" / "check_resume_fit.py"


def emit(context: str) -> None:
    """Surface text back to Claude as PostToolUse additional context."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": context,
        }
    }))


def classify(file_path: str) -> tuple[str, str] | None:
    """Return (company, kind) if file_path is output/<company>/{resume,cover_letter}.tex."""
    p = Path(file_path)
    if p.name == "resume.tex":
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

    if kind == "cover":
        code, out = run(["python3", "build_cover_letter.py", company])
        status = "compiled" if code == 0 else "FAILED to compile"
        emit(f"[tailor hook] cover_letter.tex for {company} {status}.\n{out[-600:]}")
        return 0

    code, out = run(["python3", "build_resume.py", company])
    if code != 0:
        emit(f"[tailor hook] resume.tex for {company} FAILED to compile:\n{out[-800:]}")
        return 0
    py = str(VENV_PY) if VENV_PY.exists() else "python3"
    _, report = run([py, str(CHECKER), company])
    emit(f"[tailor hook] {company} resume recompiled; deterministic fit check:\n{report}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never let a hook bug block Claude's tool call
        print(f"[tailor hook] non-fatal error: {exc}", file=sys.stderr)
        sys.exit(0)
