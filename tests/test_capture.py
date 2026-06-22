#!/usr/bin/env python3
# pyright: reportPrivateUsage=false, reportUnusedImport=false
"""Tests for capture_baseline: the Stop-hook AI-baseline snapshot logic.

The module's OUTPUT / DATASET / JOBDESC are redirected to temp dirs so main()
can run its real OUTPUT scan in isolation (it must not touch the repo's output/).
"""

from __future__ import annotations

import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import _helpers  # noqa: F401  (path setup)
import ai_phase
import capture_baseline as C


class Capture(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="__test_capture_"))
        self.output = self.root / "output"
        self.dataset = self.root / "dataset"
        self.jobdesc = self.root / "jobDescription"
        for d in (self.output, self.dataset, self.jobdesc):
            d.mkdir(parents=True)
        self._patches = [
            mock.patch.object(C, "OUTPUT", self.output),
            mock.patch.object(C, "DATASET", self.dataset),
            mock.patch.object(C, "JOBDESC", self.jobdesc),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def _company(self, name: str, *, complete: bool, locked: bool) -> Path:
        d = self.output / name
        d.mkdir(parents=True)
        (d / "resume.tex").write_text(
            "x\n\\end{document}\n" if complete else "incomplete", encoding="utf-8")
        if complete:
            (d / f"{C.RESUME_JOBNAME}.pdf").write_bytes(b"%PDF-1.4 fake")
        (self.jobdesc / f"{name}.txt").write_text("the JD", encoding="utf-8")
        if locked:
            ai_phase.mark(d, name, force=False)
        return d

    def test_complete_locked_company_is_captured_and_unlocked(self) -> None:
        d = self._company("acme", complete=True, locked=True)
        C.main()
        self.assertTrue((self.dataset / "acme" / "resume.ai.tex").exists())
        self.assertTrue((self.dataset / "acme" / "job_description.txt").exists())
        self.assertFalse(ai_phase.is_fresh(d))  # lock cleared

    def test_incomplete_fresh_lock_is_left_alone(self) -> None:
        d = self._company("acme", complete=False, locked=True)
        C.main()
        self.assertFalse((self.dataset / "acme" / "resume.ai.tex").exists())
        self.assertTrue(ai_phase.is_fresh(d))  # lock kept for next turn

    def test_incomplete_stale_lock_is_dropped(self) -> None:
        d = self._company("acme", complete=False, locked=True)
        old = time.time() - (ai_phase.STALE_SECONDS + 60)
        import os
        os.utime(ai_phase.lock_path(d), (old, old))
        C.main()
        self.assertFalse((self.dataset / "acme" / "resume.ai.tex").exists())
        self.assertIsNone(ai_phase.read(d))  # abandoned lock removed

    def test_unlocked_company_is_ignored(self) -> None:
        self._company("acme", complete=True, locked=False)
        C.main()
        self.assertFalse((self.dataset / "acme").exists())

    def test_re_tailor_archives_prior_pair(self) -> None:
        # existing baseline -> a fresh complete+locked run archives the old one
        (self.dataset / "acme").mkdir(parents=True)
        (self.dataset / "acme" / "resume.ai.tex").write_text("OLD", encoding="utf-8")
        self._company("acme", complete=True, locked=True)
        C.main()
        new_text = (self.dataset / "acme" / "resume.ai.tex").read_text(encoding="utf-8")
        self.assertIn("\\end{document}", new_text)
        prevs = list((self.dataset / "acme").glob(".prev-*"))
        self.assertEqual(len(prevs), 1)
        self.assertEqual((prevs[0] / "resume.ai.tex").read_text(encoding="utf-8"), "OLD")


if __name__ == "__main__":
    unittest.main()
