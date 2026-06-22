#!/usr/bin/env python3
"""PostToolUse hook: run the /tailor chain on saves, as a thin adapter.

The normal /tailor flow writes a small ``output/<company>/resume.slots.json``;
this hook then runs the whole deterministic chain WITHOUT Claude invoking
anything, feeding the combined fit + honesty report back as additionalContext.
All the chain logic lives in :mod:`tailor_pipeline`; this file only:

  * reads the tool-call JSON on stdin,
  * classifies the saved path (``slots`` / ``resume`` / ``cover``) via
    :func:`paths.classify_output`,
  * dispatches to the matching pipeline entrypoint,
  * emits the Report text.

Direct ``resume.tex`` writes are still honored (skip the assemble step) but
discouraged -- edit the slot, not the tex. No-ops silently for any other file,
and never blocks the tool call (always exits 0).

Wired in .claude/settings.json under hooks.PostToolUse (matcher Write|Edit|...).
"""

from __future__ import annotations

import json
import sys
from typing import Any

import tailor_pipeline as pipeline
from paths import classify_output


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
        emit(f"[tailor hook] {pipeline.assemble_and_check(company).text}")
    elif kind == "resume":
        emit("[tailor hook] (direct resume.tex write -- prefer editing the slot file) "
             f"{pipeline.build_and_check(company).text}")
    else:  # cover
        emit(f"[tailor hook] {pipeline.cover_check(company).text}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never let a hook bug block Claude's tool call
        print(f"[tailor hook] non-fatal error: {exc}", file=sys.stderr)
        sys.exit(0)
