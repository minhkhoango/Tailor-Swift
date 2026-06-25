#!/usr/bin/env python3
"""JSONL run logger: one event per action, console echoes off the same events.

One stream per run at ``logs/tailor-<timestamp>.jsonl`` -- one JSON object per
line, so cron-era analytics need no separate ledger
(``jq 'select(.event=="jd_done" and .verdict!="OK")'`` answers "what failed").
The console echo is a short human line derived from the same event, so what you
read live and what lands on disk never drift.

Event taxonomy (see PLAN.md §G): run_start, jd_start, skip, llm_call, slots,
assemble, compile, fit, honesty, why_search, why_write, abort, jd_done, run_done.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from .core.paths import LOGS

# event -> (template, fields used). Kept tiny: only events with a worthwhile echo
# get a custom line; everything else prints "event key=val ...".
_ECHO: dict[str, str] = {
    "run_start": "tailor: {jd_count} JD(s) — {argv}",
    "jd_start":  "▶ {stem}",
    "skip":      "  skip {stem} ({reason})",
    "llm_call":  "  llm pass {pass} ({out_tok} out tok, cache_read={cache_read_tok})",
    "fit":       "  fit pass {pass}: {verdict} fill={fill}",
    "honesty":   "  honesty pass {pass}: {flags}",
    "why_write": "  why {stem} -> {path}{todo_tag}",
    "abort":     "✗ ABORT {stem}: {reason}",
    "jd_done":   "✓ {stem}: {verdict} honesty={honesty} ({passes} pass) uncovered={uncovered}",
    "run_done":  "tailor done: {jd_count} JD(s), {failures} failure(s)",
}


class RunLogger:
    """Append-only JSONL logger; every :meth:`event` is one line + one echo."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._fh = path.open("a", encoding="utf-8")

    def event(self, event: str, **fields: Any) -> None:
        record = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
                  "event": event, **fields}
        self._fh.write(json.dumps(record, default=str) + "\n")
        self._fh.flush()
        print(self._echo(event, fields))

    def _echo(self, event: str, fields: dict[str, Any]) -> str:
        tmpl = _ECHO.get(event)
        if tmpl is None:
            extra = " ".join(f"{k}={v}" for k, v in fields.items())
            return f"  {event} {extra}".rstrip()
        safe = dict(fields)
        safe.setdefault("todo_tag", "  [TODO]" if fields.get("todo") else "")
        try:
            return tmpl.format(**safe)
        except (KeyError, IndexError):
            return f"  {event} {fields}"

    def close(self) -> None:
        self._fh.close()


def new_logger(prefix: str = "tailor") -> RunLogger:
    """Open a fresh ``logs/tailor-<timestamp>.jsonl`` stream for this run."""
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return RunLogger(LOGS / f"{prefix}-{ts}.jsonl")
