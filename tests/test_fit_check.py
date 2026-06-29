#!/usr/bin/env python3
# pyright: reportPrivateUsage=false, reportUnusedImport=false
"""Tests for the deterministic fit-check core (no PDF / pdfplumber needed).

``import _helpers`` is kept for its path-setup side effect.
"""

from __future__ import annotations

import unittest

import _helpers  # noqa: F401  (path setup)
from tailor.core import check_resume_fit as F
from tailor.core.check_resume_fit import BulletReport, FitReport, Page, SkillRowReport, Word


def words(*specs: tuple[str, int]) -> list[Word]:
    """Build a word stream from (text, line_id) pairs with synthetic geometry."""
    out: list[Word] = []
    for i, (text, line_id) in enumerate(specs):
        top = 40.0 + line_id * 12.0
        out.append(Word(text, x0=float(i * 10), x1=float(i * 10 + 8),
                        top=top, bottom=top + 9.0, line_id=line_id))
    return out


class TokenMatching(unittest.TestCase):
    def test_exact_and_hyphen(self) -> None:
        self.assertTrue(F.tokens_match("fine-tuned", "finetuned"))
        self.assertTrue(F.tokens_match("react", "react"))

    def test_prefix_long_tokens(self) -> None:
        self.assertTrue(F.tokens_match("optimization", "optimiz"))
        self.assertFalse(F.tokens_match("go", "golang"))  # too short to prefix-match

    def test_numbers(self) -> None:
        self.assertTrue(F.tokens_match("4000", "4,000"))


class NormalizeBullet(unittest.TestCase):
    def test_strips_latex_and_lowercases(self) -> None:
        toks = F.normalize_bullet(r"\textbf{Built} a \href{http://x}{Chrome} ext 99\%")
        self.assertIn("built", toks)
        self.assertIn("chrome", toks)
        self.assertIn("99", toks)
        self.assertNotIn("textbf", toks)


class Fullness(unittest.TestCase):
    def test_full_page_is_one(self) -> None:
        page = Page(612.0, 792.0, words(("a", 0)))
        # force content_bottom to the printable bottom
        page.words[0] = Word("a", 0, 8, F.PRINTABLE_TOP_PT,
                             F.PRINTABLE_BOTTOM_PT, 0)
        full, _, _ = F.compute_fullness(page)
        self.assertAlmostEqual(full, 1.0, places=3)

    def test_empty_page_is_zero(self) -> None:
        self.assertEqual(F.compute_fullness(Page(612.0, 792.0, [])), (0.0, 0.0, 0.0))


class Verdict(unittest.TestCase):
    def _bullets(self, flagged: bool) -> list[BulletReport]:
        return [BulletReport(1, "x", True, 2, 1, 1.0, flagged)]

    def _skills(self, wrapped: bool) -> list[SkillRowReport]:
        return [SkillRowReport("Languages", True, 2 if wrapped else 1, wrapped)]

    def test_multipage(self) -> None:
        self.assertEqual(F.build_verdict(2, None, [], [])[0], "MULTIPAGE")

    def test_overfull(self) -> None:
        self.assertEqual(F.build_verdict(1, 1.05, [], [])[0], "OVERFULL")

    def test_underfull(self) -> None:
        self.assertEqual(F.build_verdict(1, 0.80, [], [])[0], "UNDERFULL")

    def test_spillover(self) -> None:
        self.assertEqual(F.build_verdict(1, 0.97, self._bullets(True), [])[0], "SPILLOVER")

    def test_wrapped_skill_row_is_wrap(self) -> None:
        # An otherwise-clean page with a 2-line skills row is WRAP, not OK.
        self.assertEqual(
            F.build_verdict(1, 0.97, self._bullets(False), self._skills(True))[0], "WRAP")

    def test_spillover_outranks_wrap(self) -> None:
        # A real spillover is worse than a skills wrap; SPILLOVER wins.
        self.assertEqual(
            F.build_verdict(1, 0.97, self._bullets(True), self._skills(True))[0], "SPILLOVER")

    def test_ok(self) -> None:
        self.assertEqual(
            F.build_verdict(1, 0.97, self._bullets(False), self._skills(False))[0], "OK")


class Spillover(unittest.TestCase):
    def test_flags_short_last_line(self) -> None:
        stream = words(("alpha", 0), ("beta", 0), ("gamma", 0),
                       ("delta", 0), ("epsilon", 0), ("zeta", 1))
        norm = [F.normalize_pdf_word(w.text) for w in stream]
        toks = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"]
        fields, _ = F.detect_spillover(toks, stream, norm, 0)
        self.assertTrue(fields.rendered)
        self.assertEqual(fields.n_lines, 2)
        self.assertEqual(fields.last_line_word_count, 1)
        self.assertTrue(fields.flagged)

    def test_single_line_not_flagged(self) -> None:
        stream = words(("alpha", 0), ("beta", 0), ("gamma", 0))
        norm = [F.normalize_pdf_word(w.text) for w in stream]
        fields, _ = F.detect_spillover(["alpha", "beta", "gamma"], stream, norm, 0)
        self.assertEqual(fields.n_lines, 1)
        self.assertFalse(fields.flagged)

    def test_low_confidence_not_rendered(self) -> None:
        stream = words(("zzz", 0), ("qqq", 0))
        norm = [F.normalize_pdf_word(w.text) for w in stream]
        fields, _ = F.detect_spillover(["alpha", "beta", "gamma"], stream, norm, 0)
        self.assertFalse(fields.rendered)


class FormatReport(unittest.TestCase):
    def _report(self, verdict: str, flagged: bool, **kw: object) -> FitReport:
        bullets = [BulletReport(1, "lead bullet", True, 2, 9, 1.0, False),
                   BulletReport(2, "danger bullet", True, 2, 1, 1.0, flagged)]
        return FitReport("Acme", 1, 0.97, 40.0, 740.0, bullets, verdict, **kw)  # type: ignore[arg-type]

    def test_clean_is_one_line(self) -> None:
        out = F.format_report(self._report("OK", flagged=False))
        self.assertEqual(out.count("\n"), 0)
        self.assertIn("Acme: OK", out)
        self.assertIn("fullness 0.97", out)
        self.assertIn("spillover 0", out)
        # no per-bullet table on the clean path
        self.assertNotIn("[01]", out)

    def test_actionable_shows_only_flagged_bullet(self) -> None:
        out = F.format_report(self._report("SPILLOVER", flagged=True))
        self.assertIn("Acme: SPILLOVER", out)
        self.assertIn("[02] FLAG", out)        # the flagged bullet is surfaced
        self.assertNotIn("[01]", out)          # the OK bullet is not


class ReportToDict(unittest.TestCase):
    def test_shape(self) -> None:
        r = FitReport("Acme", 1, 0.97, 40.0, 740.0,
                      [BulletReport(1, "x", True, 2, 1, 1.0, True)], "SPILLOVER",
                      ["1 bullet(s) with <= 4-word last line"])
        d = F.report_to_dict(r)
        self.assertEqual(d["company"], "Acme")
        self.assertEqual(d["verdict"], "SPILLOVER")
        self.assertFalse(d["ok"])
        self.assertEqual(d["spillover_flags"], 1)
        self.assertIn("text", d)
        self.assertIn("Acme", d["text"])
        self.assertEqual(d["report"]["page_count"], 1)


if __name__ == "__main__":
    unittest.main()
