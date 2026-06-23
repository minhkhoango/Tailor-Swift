#!/usr/bin/env python3
# pyright: reportPrivateUsage=false
"""Tests for post_save_build: the assemble -> compile -> fit -> honesty chain,
plus the two deterministic honesty checks it now owns (number-traceability +
the PR-Pilot either/or bullet).

Failure paths and the fit-JSON seam are driven with monkeypatched stages so they
run without pdflatex. One real end-to-end build is included, skipped unless both
pdflatex and pdfplumber are available -- the "everything actually works" check.
"""

from __future__ import annotations

import unittest
from unittest import mock

from _helpers import BLOCKS, TailorTempCase, has_pdflatex, has_pdfplumber
import assemble_resume as A
import post_save_build as P
import tex_util as T


# --------------------------------------------------------------------------- #
# The chain
# --------------------------------------------------------------------------- #
class FitJsonSeam(TailorTempCase):
    def test_parses_structured_report(self) -> None:
        payload = '{"ok": true, "verdict": "OK", "text": "Acme: ok"}'
        with mock.patch.object(P, "_run", return_value=(0, payload)):
            fit, text = P._fit_json(self.company)
        self.assertIsNotNone(fit)
        assert fit is not None
        self.assertTrue(fit["ok"])
        self.assertEqual(text, "Acme: ok")

    def test_non_json_is_none(self) -> None:
        with mock.patch.object(P, "_run", return_value=(2, "Traceback: boom")):
            fit, text = P._fit_json(self.company)
        self.assertIsNone(fit)
        self.assertIn("boom", text)

    def test_error_payload_is_none(self) -> None:
        with mock.patch.object(P, "_run", return_value=(2, '{"error": "missing PDF"}')):
            fit, text = P._fit_json(self.company)
        self.assertIsNone(fit)
        self.assertIn("missing PDF", text)


class BuildAndCheck(TailorTempCase):
    def test_compile_failure_short_circuits(self) -> None:
        self.write("resume.tex", "garbage")
        with mock.patch.object(P, "_compile", return_value=(False, "! LaTeX Error")):
            rep = P.build_and_check(self.company)
        self.assertFalse(rep.ok)
        self.assertIn("FAILED to compile", rep.text)
        self.assertIsNone(rep.fit)

    def test_success_combines_fit_and_honesty(self) -> None:
        self.write("resume.tex", "ok")
        fit_payload = {"ok": True, "verdict": "OK", "text": "fit: OK"}
        with mock.patch.object(P, "_compile", return_value=(True, "")), \
             mock.patch.object(P, "_fit_json", return_value=(fit_payload, "fit: OK")), \
             mock.patch.object(P, "honesty_flags", return_value=[]):
            rep = P.build_and_check(self.company)
        self.assertTrue(rep.ok)
        self.assertIn("fit: OK", rep.text)
        self.assertIn("honesty: clean", rep.text)

    def test_honesty_flag_makes_not_ok(self) -> None:
        self.write("resume.tex", "ok")
        fit_payload = {"ok": True, "verdict": "OK", "text": "fit: OK"}
        with mock.patch.object(P, "_compile", return_value=(True, "")), \
             mock.patch.object(P, "_fit_json", return_value=(fit_payload, "fit: OK")), \
             mock.patch.object(P, "honesty_flags",
                               return_value=["numbers not traceable to master: 99999"]):
            rep = P.build_and_check(self.company)
        self.assertFalse(rep.ok)
        self.assertIn("99999", rep.text)


class AssembleAndCheck(TailorTempCase):
    def test_missing_slot_reports_assemble_failure(self) -> None:
        rep = P.assemble_and_check(self.company)
        self.assertFalse(rep.ok)
        self.assertIn("assemble failed", rep.text)

    def test_assembles_then_delegates_to_build(self) -> None:
        self.write_slots(self.valid_slot_data())
        sentinel = P.Report(self.company, "resume", True, ["built"])
        with mock.patch.object(P, "build_and_check", return_value=sentinel) as bc:
            rep = P.assemble_and_check(self.company)
        bc.assert_called_once_with(self.company)
        self.assertIn("built", rep.text)


class CoverCheck(TailorTempCase):
    def test_compile_failure(self) -> None:
        self.write("cover_letter.tex", "garbage")
        with mock.patch.object(P, "_compile", return_value=(False, "! LaTeX Error")):
            rep = P.cover_check(self.company)
        self.assertFalse(rep.ok)
        self.assertIn("FAILED to compile", rep.text)


# --------------------------------------------------------------------------- #
# Honesty: the two deterministic checks
# --------------------------------------------------------------------------- #
class TraceableNumbers(unittest.TestCase):
    def test_excludes_preamble_constants_fallback(self) -> None:
        nums = P._traceable_numbers("__no_such_company__", BLOCKS)
        self.assertNotIn("0.15", nums)
        self.assertNotIn("0.97", nums)
        any_bullet_num: set[str] = set()
        for blk in BLOCKS.values():
            for bullet in blk.bullets:
                any_bullet_num |= set(T.numbers_in(bullet))
        self.assertTrue(any_bullet_num)
        self.assertTrue(any_bullet_num <= nums)


class HonestyFlags(TailorTempCase):
    def _assemble(self) -> None:
        self.write_slots(self.valid_slot_data())
        A.assemble(self.company)

    def test_real_resume_has_no_prpilot_or_buzzword_noise(self) -> None:
        # An assembled resume carries no PR-Pilot either/or flag. It MAY carry the
        # known education-number quirk (the always-copied ICPC bullet's numbers
        # live outside any @key block, so they never trace) -- pre-existing
        # advisory noise we ignore here.
        self._assemble()
        flags = P.honesty_flags(self.company)
        self.assertFalse(any("PR-Pilot" in f for f in flags))

    def test_scoped_numbers_flag_untraceable_metric(self) -> None:
        self._assemble()
        tex = (self.out_dir / "resume.tex").read_text(encoding="utf-8")
        self.assertIn("Connected", tex)
        tex = tex.replace("Connected", "99999 Connected", 1)
        (self.out_dir / "resume.tex").write_text(tex, encoding="utf-8")
        flags = P.honesty_flags(self.company)
        self.assertTrue(any("99999" in f for f in flags))

    def test_both_prpilot_bullets_flagged(self) -> None:
        self.write("resume.tex",
                   "\\begin{document}\n"
                   f"\\resumeItem{{{P.PRPILOT_SHORT_SIG} engineers from a thread}}\n"
                   f"\\resumeItem{{{P.PRPILOT_LONG_SIG} research summary}}\n"
                   "\\end{document}\n")
        flags = P.honesty_flags(self.company)
        self.assertTrue(any("PR-Pilot" in f for f in flags))

    def test_missing_resume(self) -> None:
        flags = P.honesty_flags(self.company)
        self.assertTrue(any("missing" in f for f in flags))


class HonestyLine(unittest.TestCase):
    def test_clean_and_flags(self) -> None:
        self.assertEqual(P.honesty_line([]), "honesty: clean")
        self.assertEqual(P.honesty_line(["a", "b"]), "honesty: FLAGS [a; b]")


@unittest.skipUnless(has_pdflatex() and has_pdfplumber(),
                     "needs pdflatex + pdfplumber for a real build")
class EndToEnd(TailorTempCase):
    def test_real_assemble_compile_fit_honesty(self) -> None:
        self.write_slots(self.valid_slot_data())
        rep = P.assemble_and_check(self.company)
        self.assertNotIn("FAILED to compile", rep.text)
        self.assertTrue((self.out_dir / "Khoa_Ngo_resume.pdf").exists())
        self.assertIsNotNone(rep.fit)
        assert rep.fit is not None
        self.assertIn(rep.fit["verdict"],
                      {"OK", "UNDERFULL", "OVERFULL", "SPILLOVER", "MULTIPAGE"})
        self.assertIn("honesty", rep.text)


if __name__ == "__main__":
    unittest.main()
