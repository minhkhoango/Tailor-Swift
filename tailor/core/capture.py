#!/usr/bin/env python3
"""Dataset benchmark-pair capture, slot-level.

The benchmark pair for a company is now slot files, not ``.tex`` (ADR-less "why"
note in CONTEXT.md): the slot file is the LLM's actual deliverable -- tiny, and it
diffs cleanly against a later human-edited slot for prompt tuning.

  dataset/<stem>/resume.ai.slots.json      the AI's first shipped slots (baseline)
  dataset/<stem>/resume.final.slots.json   the human-edited slots (rolling final)
  dataset/<stem>/job_description.txt       the JD that produced them

The orchestrator calls :func:`capture_ai_baseline` when it ships a company that is
not already frozen; the live watcher calls :func:`capture_human_final` when you
hand-edit the output slot. Old ``.tex`` pairs stay as-is (historical); new pairs
use this slot format.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .paths import DATASET, JOBDESC

AI_BASELINE = "resume.ai.slots.json"
HUMAN_FINAL = "resume.final.slots.json"


def is_frozen(stem: str) -> bool:
    """True when an AI baseline slot already exists -- do not overwrite it."""
    return (DATASET / stem / AI_BASELINE).exists()


def capture_ai_baseline(stem: str, slots_data: dict[str, Any]) -> Path | None:
    """Snapshot the AI's shipped slots as the frozen baseline (skips if frozen).

    Also copies the JD that produced it, so a benchmark pair is self-contained.
    Returns the written path, or ``None`` when the company is already frozen.
    """
    if is_frozen(stem):
        return None
    co_dir = DATASET / stem
    co_dir.mkdir(parents=True, exist_ok=True)
    dest = co_dir / AI_BASELINE
    dest.write_text(json.dumps(slots_data, indent=2), encoding="utf-8")
    jd = JOBDESC / f"{stem}.txt"
    if jd.exists():
        shutil.copy2(jd, co_dir / "job_description.txt")
    return dest


def capture_human_final(stem: str, slots_path: Path) -> Path:
    """Snapshot a hand-edited output slot as the rolling human-final (last wins)."""
    co_dir = DATASET / stem
    co_dir.mkdir(parents=True, exist_ok=True)
    dest = co_dir / HUMAN_FINAL
    shutil.copy2(slots_path, dest)
    return dest
