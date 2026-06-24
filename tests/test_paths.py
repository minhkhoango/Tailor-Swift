#!/usr/bin/env python3
# pyright: reportUnusedImport=false
"""Tests for paths.classify_output: the single output-file classifier.

``import _helpers`` is kept for its path-setup side effect (see test_tailor_lock).
"""

from __future__ import annotations

import unittest

import _helpers  # noqa: F401  (path setup)
from paths import OUTPUT, classify_output


class ClassifyOutput(unittest.TestCase):
    def test_slots_resume_cover(self) -> None:
        self.assertEqual(classify_output(OUTPUT / "Acme" / "resume.slots.json"),
                         ("Acme", "slots"))
        self.assertEqual(classify_output(OUTPUT / "Acme" / "resume.tex"),
                         ("Acme", "resume"))
        self.assertEqual(classify_output(OUTPUT / "Acme" / "cover_letter.tex"),
                         ("Acme", "cover"))

    def test_unwatched_name_is_none(self) -> None:
        self.assertIsNone(classify_output(OUTPUT / "Acme" / "notes.txt"))
        self.assertIsNone(classify_output(OUTPUT / "Acme" / "Khoa_Ngo_resume.pdf"))

    def test_outside_output_is_none(self) -> None:
        # right filename, wrong parent-of-parent
        self.assertIsNone(classify_output(OUTPUT / "resume.tex"))
        self.assertIsNone(classify_output(OUTPUT.parent / "Acme" / "resume.tex"))

    def test_company_is_immediate_parent(self) -> None:
        got = classify_output(OUTPUT / "Two_Words_Co" / "resume.slots.json")
        self.assertIsNotNone(got)
        assert got is not None
        self.assertEqual(got[0], "Two_Words_Co")


if __name__ == "__main__":
    unittest.main()
