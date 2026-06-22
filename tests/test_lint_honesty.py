#!/usr/bin/env python3
# pyright: reportPrivateUsage=false
"""Tests for the honesty linter: forbidden lists, number tracing, resume/cover."""

from __future__ import annotations

import unittest

from _helpers import BLOCKS, TailorTempCase
import assemble_resume as A
import lint_honesty as L
import tex_util as T


class ForbiddenHits(unittest.TestCase):
    def test_tech_word_boundary_case_sensitive(self) -> None:
        self.assertIn("forbidden tech 'Go'", L.forbidden_hits("we use Go daily"))
        self.assertEqual(L.forbidden_hits("Google Colab, storage, Django, ago"), [])

    def test_dotnet_and_vue(self) -> None:
        hits = L.forbidden_hits("built on .NET and Vue")
        self.assertIn("forbidden tech '.NET'", hits)
        self.assertIn("forbidden tech 'Vue'", hits)

    def test_scale_and_buzzwords(self) -> None:
        hits = L.forbidden_hits("a large-scale system I spearheaded")
        self.assertIn("scale claim 'large-scale'", hits)
        self.assertIn("buzzword 'spearheaded'", hits)

    def test_clean(self) -> None:
        self.assertEqual(L.forbidden_hits("Shipped a Chrome extension with React"), [])


class TraceableNumbers(unittest.TestCase):
    def test_excludes_preamble_constants_fallback(self) -> None:
        nums = L.traceable_numbers("__no_such_company__", BLOCKS)
        self.assertNotIn("0.15", nums)
        self.assertNotIn("0.97", nums)
        any_bullet_num: set[str] = set()
        for blk in BLOCKS.values():
            for bullet in blk.bullets:
                any_bullet_num |= set(T.numbers_in(bullet))
        self.assertTrue(any_bullet_num)
        self.assertTrue(any_bullet_num <= nums)


class ReportLine(unittest.TestCase):
    def test_clean_and_flags(self) -> None:
        self.assertEqual(L.report_line([], "resume"), "honesty (resume): clean")
        self.assertEqual(L.report_line(["a", "b"], "cover"),
                         "honesty (cover): FLAGS: [a; b]")


class LintResume(TailorTempCase):
    def _assemble(self) -> None:
        self.write_slots(self.valid_slot_data())
        A.assemble(self.company)

    def test_no_forbidden_flags_on_real_resume(self) -> None:
        # An assembled resume carries no forbidden-tech / scale / buzzword flags.
        # It DOES carry the known education-number quirk (the always-copied ICPC
        # bullet's "2024, 44" live outside any @key block, so they never trace) --
        # that is pre-existing advisory noise, so we ignore those specific flags.
        self._assemble()
        flags = L.lint_resume(self.company)
        honesty_critical = [f for f in flags if not f.startswith("numbers not traceable")]
        self.assertEqual(honesty_critical, [])

    def test_scoped_numbers_flag_untraceable_metric(self) -> None:
        self._assemble()
        tex = (self.out_dir / "resume.tex").read_text(encoding="utf-8")
        # splice a fabricated number into a real body bullet (not the macro def)
        self.assertIn("Connected", tex)
        tex = tex.replace("Connected", "99999 Connected", 1)
        (self.out_dir / "resume.tex").write_text(tex, encoding="utf-8")
        flags = L.lint_resume(self.company)
        self.assertTrue(any("99999" in f for f in flags))

    def test_missing_resume(self) -> None:
        flags = L.lint_resume(self.company)
        self.assertTrue(any("missing" in f for f in flags))


class LintCover(TailorTempCase):
    def test_flags_inside_why_paragraph(self) -> None:
        cover = (
            f"body before\n{L.WHY_START}\n"
            "I spearheaded a large-scale Rust rewrite.\n"
            f"{L.WHY_END}\nbody after with Kubernetes outside\n"
        )
        self.write("cover_letter.tex", cover)
        flags = L.lint_cover(self.company)
        self.assertTrue(any("Rust" in f for f in flags))
        self.assertTrue(any("large-scale" in f for f in flags))
        # text OUTSIDE the sentinels is not scanned
        self.assertFalse(any("Kubernetes" in f for f in flags))

    def test_missing_sentinels(self) -> None:
        self.write("cover_letter.tex", "no sentinels here")
        flags = L.lint_cover(self.company)
        self.assertTrue(any("sentinel" in f for f in flags))


if __name__ == "__main__":
    unittest.main()
