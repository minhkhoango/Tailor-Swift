#!/usr/bin/env python3
"""Dataset benchmark-pair capture, slot-level.

The benchmark pair for a company is now slot files, not ``.tex`` (ADR-less "why"
note in CONTEXT.md): the slot file is the LLM's actual deliverable -- tiny, and it
diffs cleanly against a later human-edited slot for prompt tuning.

  dataset/<stem>/resume.ai.slots.json      the AI's first shipped slots (baseline)
  dataset/<stem>/resume.final.slots.json   the human-edited slots (rolling final)
  dataset/<stem>/resume.final.tex          the human-edited tex (rolling final)
  dataset/<stem>/job_description.txt       the JD that produced them

The orchestrator calls :func:`capture_ai_baseline` when it ships a company that is
not already frozen; the live watcher calls :func:`capture_human_final` when you
hand-edit either the output slot OR the output tex. A company keeps exactly ONE
human-final: whichever format you saved last wins, and capturing it removes the
other format's stale final. Old ``.tex`` pairs stay as-is (historical).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .slots import SlotsData, compact_slots_json
from .paths import DATASET, JOBDESC

AI_BASELINE = "resume.ai.slots.json"
HUMAN_FINAL_SLOTS = "resume.final.slots.json"
HUMAN_FINAL_TEX = "resume.final.tex"

# The classifier's kind -> (final to write, final to drop). Capturing one format
# always removes the other, so dataset/<stem> holds a single, unambiguous final.
_FINAL_BY_KIND = {
    "slots": (HUMAN_FINAL_SLOTS, HUMAN_FINAL_TEX),
    "resume": (HUMAN_FINAL_TEX, HUMAN_FINAL_SLOTS),
}


def is_frozen(stem: str) -> bool:
    """True when an AI baseline slot already exists -- do not overwrite it."""
    return (DATASET / stem / AI_BASELINE).exists()


def capture_ai_baseline(stem: str, slots_data: SlotsData) -> Path | None:
    """Snapshot the AI's shipped slots as the frozen baseline (skips if frozen).

    Also copies the JD that produced it, so a benchmark pair is self-contained.
    Returns the written path, or ``None`` when the company is already frozen.
    """
    if is_frozen(stem):
        return None
    co_dir = DATASET / stem
    co_dir.mkdir(parents=True, exist_ok=True)
    dest = co_dir / AI_BASELINE
    dest.write_text(compact_slots_json(slots_data), encoding="utf-8")
    jd = JOBDESC / f"{stem}.txt"
    if jd.exists():
        shutil.copy2(jd, co_dir / "job_description.txt")
    return dest


def capture_human_final(stem: str, src_path: Path, kind: str) -> Path:
    """Snapshot a hand-edited output file as the rolling human-final (last wins).

    ``kind`` is the classifier's kind (``"slots" | "resume"``). A company keeps
    exactly ONE human-final: this copies ``src_path`` to the matching
    ``resume.final.*`` and deletes the other format's stale final, so the latest
    save -- in whichever format -- is unambiguously the benchmark final.
    """
    keep, drop = _FINAL_BY_KIND[kind]
    co_dir = DATASET / stem
    co_dir.mkdir(parents=True, exist_ok=True)
    dest = co_dir / keep
    shutil.copy2(src_path, dest)
    (co_dir / drop).unlink(missing_ok=True)
    return dest
