#!/usr/bin/env python3
# pyright: reportPrivateUsage=false, reportUnusedImport=false
"""Tests for capture: the slot-level dataset benchmark-pair snapshots.

The benchmark pair is now slot files, not ``.tex``: ``resume.ai.slots.json`` (the
AI's first shipped slots, frozen) + ``resume.final.slots.json`` (the rolling
human-edited slots). ``capture.DATASET`` / ``capture.JOBDESC`` are redirected to
temp dirs so the snapshots never touch the repo's real ``dataset/``.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _helpers  # noqa: F401  (path setup)
from tailor.core import capture as C
from tailor.core.slots import SlotsData


class Capture(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="__test_capture_"))
        self.dataset = self.root / "dataset"
        self.jobdesc = self.root / "jobDescription"
        for d in (self.dataset, self.jobdesc):
            d.mkdir(parents=True)
        self._patches = [
            mock.patch.object(C, "DATASET", self.dataset),
            mock.patch.object(C, "JOBDESC", self.jobdesc),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def _slots(self, company: str = "acme") -> SlotsData:
        return {"company": company, "experiences": [], "projects": [],
                "skills": [], "uncovered": []}

    # -- is_frozen --------------------------------------------------------- #
    def test_not_frozen_when_no_baseline(self) -> None:
        self.assertFalse(C.is_frozen("acme"))

    def test_frozen_after_baseline_written(self) -> None:
        C.capture_ai_baseline("acme", self._slots())
        self.assertTrue(C.is_frozen("acme"))

    # -- capture_ai_baseline ---------------------------------------------- #
    def test_ai_baseline_writes_slots_and_copies_jd(self) -> None:
        (self.jobdesc / "acme.txt").write_text("the JD", encoding="utf-8")
        dest = C.capture_ai_baseline("acme", self._slots())
        self.assertIsNotNone(dest)
        baseline = self.dataset / "acme" / C.AI_BASELINE
        self.assertTrue(baseline.exists())
        self.assertEqual(json.loads(baseline.read_text(encoding="utf-8"))["company"], "acme")
        self.assertEqual((self.dataset / "acme" / "job_description.txt")
                         .read_text(encoding="utf-8"), "the JD")

    def test_ai_baseline_skips_when_frozen(self) -> None:
        first = C.capture_ai_baseline("acme", self._slots())
        assert first is not None
        first.write_text('{"company": "ORIGINAL"}', encoding="utf-8")
        # A second capture must NOT clobber the frozen baseline.
        second = C.capture_ai_baseline("acme", self._slots("CHANGED"))
        self.assertIsNone(second)
        self.assertEqual(json.loads(first.read_text(encoding="utf-8"))["company"], "ORIGINAL")

    def test_ai_baseline_without_jd_still_writes(self) -> None:
        dest = C.capture_ai_baseline("acme", self._slots())
        self.assertIsNotNone(dest)
        self.assertFalse((self.dataset / "acme" / "job_description.txt").exists())

    # -- capture_human_final ---------------------------------------------- #
    def test_human_final_snapshots_output_slot(self) -> None:
        src = self.root / "resume.slots.json"
        src.write_text('{"company": "edited"}', encoding="utf-8")
        dest = C.capture_human_final("acme", src, "slots")
        self.assertEqual(dest, self.dataset / "acme" / C.HUMAN_FINAL_SLOTS)
        self.assertEqual(json.loads(dest.read_text(encoding="utf-8"))["company"], "edited")

    def test_human_final_last_write_wins(self) -> None:
        src = self.root / "resume.slots.json"
        src.write_text('{"company": "v1"}', encoding="utf-8")
        C.capture_human_final("acme", src, "slots")
        src.write_text('{"company": "v2"}', encoding="utf-8")
        dest = C.capture_human_final("acme", src, "slots")
        self.assertEqual(json.loads(dest.read_text(encoding="utf-8"))["company"], "v2")

    def test_human_final_snapshots_output_tex(self) -> None:
        src = self.root / "resume.tex"
        src.write_text("\\documentclass{article}", encoding="utf-8")
        dest = C.capture_human_final("acme", src, "resume")
        self.assertEqual(dest, self.dataset / "acme" / C.HUMAN_FINAL_TEX)
        self.assertEqual(dest.read_text(encoding="utf-8"), "\\documentclass{article}")

    def test_capturing_tex_drops_stale_slots_final(self) -> None:
        slots = self.root / "resume.slots.json"
        slots.write_text('{"company": "v1"}', encoding="utf-8")
        C.capture_human_final("acme", slots, "slots")
        tex = self.root / "resume.tex"
        tex.write_text("\\documentclass{article}", encoding="utf-8")
        C.capture_human_final("acme", tex, "resume")
        # Latest save was tex -> only the tex final survives.
        self.assertTrue((self.dataset / "acme" / C.HUMAN_FINAL_TEX).exists())
        self.assertFalse((self.dataset / "acme" / C.HUMAN_FINAL_SLOTS).exists())

    def test_capturing_slots_drops_stale_tex_final(self) -> None:
        tex = self.root / "resume.tex"
        tex.write_text("\\documentclass{article}", encoding="utf-8")
        C.capture_human_final("acme", tex, "resume")
        slots = self.root / "resume.slots.json"
        slots.write_text('{"company": "v1"}', encoding="utf-8")
        C.capture_human_final("acme", slots, "slots")
        # Latest save was slots -> only the slots final survives.
        self.assertTrue((self.dataset / "acme" / C.HUMAN_FINAL_SLOTS).exists())
        self.assertFalse((self.dataset / "acme" / C.HUMAN_FINAL_TEX).exists())


if __name__ == "__main__":
    unittest.main()
