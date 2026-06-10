#!/usr/bin/env python3
# pyright: reportPrivateUsage=false
"""Unit tests for the /tailor helper scripts (pure logic; no pdflatex/pdfplumber).

Run:  python3 -m unittest test_tailor_scripts -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / ".claude" / "skills" / "tailor" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import assemble_resume as A  # noqa: E402
import lint_honesty as L  # noqa: E402
import tex_util as T  # noqa: E402

MASTER = (SCRIPTS / ".." / "assets" / "master_resume.tex").resolve().read_text()
BLOCKS = T.parse_master(MASTER)


class TexUtil(unittest.TestCase):
    def test_all_seven_keys_parse(self) -> None:
        self.assertEqual(
            sorted(BLOCKS),
            ["autoly", "fpt", "ioe", "linkedin_outreach", "local_lens",
             "p4_stack", "pr_pilot"])

    def test_block_kinds_and_bullets(self) -> None:
        self.assertEqual(BLOCKS["ioe"].kind, "experience")
        self.assertEqual(BLOCKS["local_lens"].kind, "project")
        self.assertEqual(len(BLOCKS["local_lens"].bullets), 5)
        self.assertEqual(len(BLOCKS["pr_pilot"].bullets), 3)  # long + short cold-email both present

    def test_project_heading_has_emph(self) -> None:
        self.assertIn("\\emph", BLOCKS["local_lens"].heading_args[0])

    def test_numbers_in_ranges_decimals_commas(self) -> None:
        got = T.numbers_in(r"on \$4{,}000, 1--14 day, 10/10 runs, 99.9\% uptime")
        self.assertEqual(dict(got), {"4000": 1, "1": 1, "14": 1, "10": 2, "99.9": 1})

    def test_skill_rows(self) -> None:
        rows = T.extract_skill_rows(MASTER)
        cats = [c for c, _ in rows]
        self.assertEqual(cats[:2], ["Languages", "AI/ML"])

    def test_match_braces_nested(self) -> None:
        inner, after = T.match_braces("{a{b}c}d", 0)
        self.assertEqual(inner, "a{b}c")
        self.assertEqual(after, 7)


class Assembler(unittest.TestCase):
    def test_bullet_by_id_is_verbatim(self) -> None:
        block = BLOCKS["fpt"]
        line = A._bullet_tex({"id": 1}, block)
        self.assertEqual(line, f"        \\resumeItem{{{block.bullets[0].strip()}}}")

    def test_bullet_id_out_of_range(self) -> None:
        with self.assertRaises(A.AssembleError):
            A._bullet_tex({"id": 99}, BLOCKS["fpt"])

    def test_bullet_text_form(self) -> None:
        self.assertEqual(A._bullet_tex({"text": "hello"}, BLOCKS["fpt"]),
                         "        \\resumeItem{hello}")

    def test_splice_emph(self) -> None:
        out = A._splice_emph(BLOCKS["local_lens"].heading, "Foo, Bar")
        self.assertIn("\\emph{Foo, Bar}", out)
        self.assertNotIn("PaddleOCR", out)  # original emph content replaced

    def test_skills_row_cap(self) -> None:
        with self.assertRaises(A.AssembleError):
            A._skills_section([["a", "b"]] * 6)

    def test_experiences_both_in_order_ok(self) -> None:
        A._validate_experiences([{"key": "ioe"}, {"key": "fpt"}], BLOCKS)  # no raise

    def test_experiences_missing_one_raises(self) -> None:
        with self.assertRaises(A.AssembleError):
            A._validate_experiences([{"key": "ioe"}], BLOCKS)

    def test_experiences_wrong_order_raises(self) -> None:
        with self.assertRaises(A.AssembleError):
            A._validate_experiences([{"key": "fpt"}, {"key": "ioe"}], BLOCKS)


class Linter(unittest.TestCase):
    def test_forbidden_tech_word_boundary(self) -> None:
        self.assertIn("forbidden tech 'Go'", L.forbidden_hits("we use Go daily"))
        # case-sensitive + boundary: these must NOT trip
        self.assertEqual(L.forbidden_hits("Google Colab, storage, Django, ago"), [])

    def test_dotnet_and_vue(self) -> None:
        hits = L.forbidden_hits("built on .NET and Vue")
        self.assertIn("forbidden tech '.NET'", hits)
        self.assertIn("forbidden tech 'Vue'", hits)

    def test_scale_and_buzzwords(self) -> None:
        hits = L.forbidden_hits("a large-scale system I spearheaded")
        self.assertIn("scale claim 'large-scale'", hits)
        self.assertIn("buzzword 'spearheaded'", hits)

    def test_clean_text(self) -> None:
        self.assertEqual(L.forbidden_hits("Shipped a Chrome extension with React"), [])

    def test_traceable_numbers_excludes_preamble_constants(self) -> None:
        # Fallback scope (no slot file) = every master block's bullets + headings.
        nums = L.traceable_numbers("__no_such_company__", BLOCKS)
        # Geometry constants live only in the preamble -> must NOT be traceable.
        self.assertNotIn("0.15", nums)
        self.assertNotIn("0.97", nums)
        # A genuine bullet metric (from a master block) IS traceable.
        any_bullet_num = set()
        for blk in BLOCKS.values():
            for bullet in blk.bullets:
                any_bullet_num |= set(T.numbers_in(bullet))
        self.assertTrue(any_bullet_num)
        self.assertTrue(any_bullet_num <= nums)


if __name__ == "__main__":
    unittest.main()
