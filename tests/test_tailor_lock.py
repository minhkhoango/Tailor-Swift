#!/usr/bin/env python3
# pyright: reportPrivateUsage=false, reportUnusedImport=false
"""Tests for tailor_lock: the .ai_phase.lock protocol between the /tailor layers.

``import _helpers`` is kept for its import-time side effect: it puts the skill
``scripts/`` dir on sys.path so ``import tailor_lock`` resolves when this file is run
on its own.
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

import _helpers  # noqa: F401  (path setup)
import tailor_lock


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
        self.assertFalse(tailor_lock.is_fresh(d))
        tailor_lock.mark(d, "acme")
        self.assertTrue(tailor_lock.is_fresh(d))
        self.assertFalse(tailor_lock.is_stale(d))

    def test_mark_is_idempotent_keeps_first_stamp(self) -> None:
        d = self._co("acme")
        tailor_lock.mark(d, "acme")
        first = tailor_lock.read(d)
        tailor_lock.mark(d, "acme")  # must NOT overwrite
        self.assertEqual(tailor_lock.read(d), first)
        assert first is not None
        self.assertEqual(first["company"], "acme")

    def test_clear_removes(self) -> None:
        d = self._co("acme")
        tailor_lock.mark(d, "acme")
        tailor_lock.clear(d)
        self.assertFalse(tailor_lock.is_fresh(d))
        self.assertIsNone(tailor_lock.read(d))
        tailor_lock.clear(d)  # idempotent, no raise

    def test_stale_when_old(self) -> None:
        d = self._co("acme")
        tailor_lock.mark(d, "acme")
        old = time.time() - (tailor_lock.STALE_SECONDS + 60)
        os.utime(tailor_lock.lock_path(d), (old, old))
        self.assertTrue(tailor_lock.is_stale(d))
        self.assertFalse(tailor_lock.is_fresh(d))

    def test_age_none_without_lock(self) -> None:
        self.assertIsNone(tailor_lock.age_seconds(self._co("acme")))

    def test_read_bad_json_is_none(self) -> None:
        d = self._co("acme")
        tailor_lock.lock_path(d).write_text("{nope", encoding="utf-8")
        self.assertIsNone(tailor_lock.read(d))

    def test_find_locked(self) -> None:
        tailor_lock.mark(self._co("a"), "a")
        tailor_lock.mark(self._co("b"), "b")
        self._co("c")  # no lock
        found = sorted(p.name for p in tailor_lock.find_locked(self.root))
        self.assertEqual(found, ["a", "b"])

    def test_find_locked_missing_dir(self) -> None:
        self.assertEqual(tailor_lock.find_locked(self.root / "nope"), [])


if __name__ == "__main__":
    unittest.main()
