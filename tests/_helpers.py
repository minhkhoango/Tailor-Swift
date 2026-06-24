#!/usr/bin/env python3
# pyright: reportPrivateUsage=false
"""Shared fixtures for the /tailor test suite.

Puts the skill ``scripts/`` dir on the path (it owns every importable module now),
loads the real master pool once, and offers a temp-company base case so the
file-driven modules (slots, assembler, linter, pipeline) can be exercised against
real ``output/<company>/`` + ``dataset/<company>/`` dirs that are torn down after.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent          # tests/ -> repo root
SCRIPTS = ROOT / ".claude" / "skills" / "tailor" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import tex_parse  # noqa: E402
from paths import DATASET, MASTER as MASTER_PATH, OUTPUT  # noqa: E402

MASTER = MASTER_PATH.read_text(encoding="utf-8")
BLOCKS = tex_parse.parse_master(MASTER)


def has_pdflatex() -> bool:
    return shutil.which("pdflatex") is not None


def has_pdfplumber() -> bool:
    import importlib.util
    return importlib.util.find_spec("pdfplumber") is not None


class TailorTempCase(unittest.TestCase):
    """Base case giving each test an isolated throwaway company under output/."""

    def setUp(self) -> None:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        self.out_dir = Path(tempfile.mkdtemp(prefix="__test_", dir=OUTPUT))
        self.company = self.out_dir.name
        self.dataset_dir = DATASET / self.company

    def tearDown(self) -> None:
        shutil.rmtree(self.out_dir, ignore_errors=True)
        shutil.rmtree(self.dataset_dir, ignore_errors=True)

    # -- factories -------------------------------------------------------- #
    def write_slots(self, data: dict[str, Any]) -> Path:
        p = self.out_dir / "resume.slots.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return p

    def write(self, name: str, text: str) -> Path:
        p = self.out_dir / name
        p.write_text(text, encoding="utf-8")
        return p

    def valid_slot_data(self) -> dict[str, Any]:
        """A minimal slot file that assembles cleanly against the real master."""
        return {
            "experiences": [
                {"key": "ioe", "bullets": [{"id": 1}]},
                {"key": "fpt", "bullets": [{"id": 1}]},
            ],
            "projects": [
                {"key": "local_lens", "bullets": [{"id": 1}, {"id": 2}]},
            ],
            "skills": [["Languages", "Python, TypeScript"]],
        }
