#!/usr/bin/env python3
# pyright: reportPrivateUsage=false, reportUnusedImport=false
"""Tests for ai_phase: the .ai_phase.lock protocol between the /tailor layers.

``import _helpers`` is kept for its import-time side effect: it puts the skill
``scripts/`` dir on sys.path so ``import ai_phase`` resolves when this file is run
on its own.
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

import _helpers  # noqa: F401  (path setup)
import ai_phase


class LockProtocol(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="__test_aiphase_"))

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def _co(self, name: str) -> Path:
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_mark_then_fresh(self) -> None:
        d = self._co("acme")
        self.assertFalse(ai_phase.is_fresh(d))
        ai_phase.mark(d, "acme")
        self.assertTrue(ai_phase.is_fresh(d))
        self.assertFalse(ai_phase.is_stale(d))

    def test_mark_is_idempotent_keeps_first_stamp(self) -> None:
        d = self._co("acme")
        ai_phase.mark(d, "acme")
        first = ai_phase.read(d)
        ai_phase.mark(d, "acme")  # must NOT overwrite
        self.assertEqual(ai_phase.read(d), first)
        assert first is not None
        self.assertEqual(first["company"], "acme")

    def test_clear_removes(self) -> None:
        d = self._co("acme")
        ai_phase.mark(d, "acme")
        ai_phase.clear(d)
        self.assertFalse(ai_phase.is_fresh(d))
        self.assertIsNone(ai_phase.read(d))
        ai_phase.clear(d)  # idempotent, no raise

    def test_stale_when_old(self) -> None:
        d = self._co("acme")
        ai_phase.mark(d, "acme")
        old = time.time() - (ai_phase.STALE_SECONDS + 60)
        os.utime(ai_phase.lock_path(d), (old, old))
        self.assertTrue(ai_phase.is_stale(d))
        self.assertFalse(ai_phase.is_fresh(d))

    def test_age_none_without_lock(self) -> None:
        self.assertIsNone(ai_phase.age_seconds(self._co("acme")))

    def test_read_bad_json_is_none(self) -> None:
        d = self._co("acme")
        ai_phase.lock_path(d).write_text("{nope", encoding="utf-8")
        self.assertIsNone(ai_phase.read(d))

    def test_find_locked(self) -> None:
        ai_phase.mark(self._co("a"), "a")
        ai_phase.mark(self._co("b"), "b")
        self._co("c")  # no lock
        found = sorted(p.name for p in ai_phase.find_locked(self.root))
        self.assertEqual(found, ["a", "b"])

    def test_find_locked_missing_dir(self) -> None:
        self.assertEqual(ai_phase.find_locked(self.root / "nope"), [])


if __name__ == "__main__":
    unittest.main()
