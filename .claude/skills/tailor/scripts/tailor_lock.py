#!/usr/bin/env python3
"""Owner of the ``.ai_phase.lock`` protocol between the /tailor layers.

The lock is the one signal that says "an AI /tailor turn is mid-flight for this
company". Three modules used to each know its on-disk shape independently:

  * ``assemble_resume.py`` WROTE ``{company, ts}`` by hand,
  * ``capture_baseline.py`` SCANNED for the locks, judged staleness with its own
    ``STALE_SECONDS = 600``, and unlinked them,
  * ``watch.py`` (in scripts/) re-read the same file and re-declared the SAME
    ``STALE_SECONDS = 600`` to decide whether to skip a rebuild.

That schema, the staleness window, and the lock lifecycle now live here once.
Callers cross a small interface (``mark`` / ``is_fresh`` / ``clear`` /
``find_locked``) and never touch the file format. Pure stdlib.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, cast

LOCK_NAME = ".ai_phase.lock"
# A lock older than this is from an abandoned run: capture drops it, the watcher
# stops treating the company as AI-owned. Defined ONCE, here.
STALE_SECONDS = 10 * 60


def lock_path(out_dir: Path) -> Path:
    """The lock file for an ``output/<company>/`` directory."""
    return out_dir / LOCK_NAME


def mark(out_dir: Path, company: str) -> None:
    """Stamp the AI-phase lock for ``company`` (idempotent: keep the first stamp).

    Written by the assembler at the start of a tailor. Re-stamping would reset the
    age and could mask an abandoned run, so an existing lock is left untouched.
    """
    lock = lock_path(out_dir)
    if lock.exists():
        return
    lock.write_text(
        json.dumps({"company": company, "ts": time.time()}),
        encoding="utf-8",
    )


def age_seconds(out_dir: Path) -> float | None:
    """Seconds since the lock was stamped, or ``None`` if there is no lock."""
    lock = lock_path(out_dir)
    try:
        return time.time() - lock.stat().st_mtime
    except OSError:
        return None


def is_fresh(out_dir: Path) -> bool:
    """True when a non-stale lock exists (an AI turn owns this company right now)."""
    age = age_seconds(out_dir)
    return age is not None and age < STALE_SECONDS


def is_stale(out_dir: Path) -> bool:
    """True when a lock exists but is older than the staleness window."""
    age = age_seconds(out_dir)
    return age is not None and age >= STALE_SECONDS


def read(out_dir: Path) -> dict[str, Any] | None:
    """The decoded lock payload, or ``None`` if absent/unreadable."""
    try:
        data: Any = json.loads(lock_path(out_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return cast("dict[str, Any]", data)


def clear(out_dir: Path) -> None:
    """Remove the lock if present (no error if already gone)."""
    lock_path(out_dir).unlink(missing_ok=True)


def find_locked(output: Path) -> list[Path]:
    """Every ``output/<company>/`` dir currently carrying a lock (stale or fresh)."""
    if not output.is_dir():
        return []
    return [lock.parent for lock in output.glob(f"*/{LOCK_NAME}")]
