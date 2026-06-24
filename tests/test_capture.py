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
import tailor_lock
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
            tailor_lock.mark(d, name)
        return d

    def test_complete_locked_company_is_captured_and_unlocked(self) -> None:
        d = self._company("acme", complete=True, locked=True)
        C.main()
        self.assertTrue((self.dataset / "acme" / "resume.ai.tex").exists())
        self.assertTrue((self.dataset / "acme" / "job_description.txt").exists())
        self.assertFalse(tailor_lock.is_fresh(d))  # lock cleared

    def test_incomplete_fresh_lock_is_left_alone(self) -> None:
        d = self._company("acme", complete=False, locked=True)
        C.main()
        self.assertFalse((self.dataset / "acme" / "resume.ai.tex").exists())
        self.assertTrue(tailor_lock.is_fresh(d))  # lock kept for next turn

    def test_incomplete_stale_lock_is_dropped(self) -> None:
        d = self._company("acme", complete=False, locked=True)
        old = time.time() - (tailor_lock.STALE_SECONDS + 60)
        import os
        os.utime(tailor_lock.lock_path(d), (old, old))
        C.main()
        self.assertFalse((self.dataset / "acme" / "resume.ai.tex").exists())
        self.assertIsNone(tailor_lock.read(d))  # abandoned lock removed

    def test_unlocked_company_is_ignored(self) -> None:
        self._company("acme", complete=True, locked=False)
        C.main()
        self.assertFalse((self.dataset / "acme").exists())


if __name__ == "__main__":
    unittest.main()
