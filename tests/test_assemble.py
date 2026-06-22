#!/usr/bin/env python3
# pyright: reportPrivateUsage=false
"""Tests for the assembler: bullet/skill rendering, invariants, full assemble()."""

from __future__ import annotations

import unittest

from _helpers import BLOCKS, TailorTempCase
import ai_phase
import assemble_resume as A
from slots import BulletSpec, EntrySpec, SlotsError


class BulletRendering(unittest.TestCase):
    def test_id_is_verbatim(self) -> None:
        block = BLOCKS["fpt"]
        line = A._bullet_tex(BulletSpec(id=1), block)
        self.assertEqual(line, f"        \\resumeItem{{{block.bullets[0].strip()}}}")

    def test_id_out_of_range(self) -> None:
        with self.assertRaises(A.AssembleError):
            A._bullet_tex(BulletSpec(id=99), BLOCKS["fpt"])

    def test_text_form(self) -> None:
        self.assertEqual(A._bullet_tex(BulletSpec(text="hello"), BLOCKS["fpt"]),
                         "        \\resumeItem{hello}")

    def test_reword_padding_rejected(self) -> None:
        # Take a real master bullet and pad it well past the +4-word ceiling.
        base = BLOCKS["fpt"].bullets[0]
        from assemble_resume import _reword_tokens
        padded = base + " " + " ".join(f"extraword{i}" for i in range(12))
        # only rejected if it still resembles its source (ratio >= floor)
        self.assertTrue(_reword_tokens(padded))
        with self.assertRaises(A.AssembleError):
            A._bullet_tex(BulletSpec(text=padded), BLOCKS["fpt"])


class SkillsSection(unittest.TestCase):
    def test_renders_rows(self) -> None:
        out = A._skills_section([("Languages", "Python"), ("AI/ML", "PyTorch")])
        self.assertIn(r"\textbf{Languages}{: Python}", out)
        self.assertIn(r"\textbf{AI/ML}{: PyTorch}", out)

    def test_row_cap(self) -> None:
        with self.assertRaises(A.AssembleError):
            A._skills_section([("a", "b")] * 6)


class ExperienceInvariant(unittest.TestCase):
    def _exp(self, *keys: str) -> list[EntrySpec]:
        return [EntrySpec(key=k, bullets=[]) for k in keys]

    def test_both_in_order_ok(self) -> None:
        A._validate_experiences(self._exp("ioe", "fpt"), BLOCKS)  # no raise

    def test_missing_one_raises(self) -> None:
        with self.assertRaises(A.AssembleError):
            A._validate_experiences(self._exp("ioe"), BLOCKS)

    def test_wrong_order_raises(self) -> None:
        with self.assertRaises(A.AssembleError):
            A._validate_experiences(self._exp("fpt", "ioe"), BLOCKS)


class SpliceEmph(unittest.TestCase):
    def test_replaces_inner(self) -> None:
        out = A._splice_emph(BLOCKS["local_lens"].heading, "Foo, Bar")
        self.assertIn("\\emph{Foo, Bar}", out)
        self.assertNotIn("PaddleOCR", out)


class StackCap(unittest.TestCase):
    def test_project_stack_over_three_raises(self) -> None:
        spec = EntrySpec(key="local_lens", bullets=[], emph="A, B, C, D")
        with self.assertRaises(A.AssembleError):
            A._entry(spec, BLOCKS, "project")

    def test_unknown_key_raises(self) -> None:
        with self.assertRaises(A.AssembleError):
            A._entry(EntrySpec(key="nope", bullets=[]), BLOCKS, "experience")

    def test_kind_mismatch_raises(self) -> None:
        with self.assertRaises(A.AssembleError):
            A._entry(EntrySpec(key="local_lens", bullets=[]), BLOCKS, "experience")


class FullAssemble(TailorTempCase):
    def test_assembles_valid_slot_file(self) -> None:
        self.write_slots(self.valid_slot_data())
        out = A.assemble(self.company)
        tex = out.read_text(encoding="utf-8")
        self.assertIn("\\documentclass", tex)
        self.assertIn("\\end{document}", tex)
        self.assertIn("\\section{Experience}", tex)
        self.assertIn("\\section{Projects}", tex)
        self.assertIn(r"\textbf{Languages}", tex)

    def test_assemble_writes_ai_phase_lock(self) -> None:
        self.write_slots(self.valid_slot_data())
        A.assemble(self.company)
        self.assertTrue(ai_phase.is_fresh(self.out_dir))

    def test_missing_slot_file_raises_slotserror(self) -> None:
        with self.assertRaises(SlotsError):
            A.assemble(self.company)

    def test_refuses_to_clobber_existing_baseline(self) -> None:
        self.write_slots(self.valid_slot_data())
        self.dataset_dir.mkdir(parents=True, exist_ok=True)
        (self.dataset_dir / "resume.ai.tex").write_text("human", encoding="utf-8")
        with self.assertRaises(A.AssembleError):
            A.assemble(self.company, force=False)
        # force overrides the clobber guard
        out = A.assemble(self.company, force=True)
        self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
