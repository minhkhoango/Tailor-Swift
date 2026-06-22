#!/usr/bin/env python3
# pyright: reportPrivateUsage=false
"""Tests for tailor_pipeline: the assemble -> compile -> fit -> honesty chain.

Failure paths and the fit-JSON seam are driven with monkeypatched stages so they
run without pdflatex. One real end-to-end build is included, skipped unless both
pdflatex and pdfplumber are available -- that is the "everything actually works"
check the suite is built around.
"""

from __future__ import annotations

import unittest
from unittest import mock

from _helpers import TailorTempCase, has_pdflatex, has_pdfplumber
import tailor_pipeline as P


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
             mock.patch("lint_honesty.lint_resume", return_value=[]):
            rep = P.build_and_check(self.company)
        self.assertTrue(rep.ok)
        self.assertIn("fit: OK", rep.text)
        self.assertIn("honesty (resume): clean", rep.text)

    def test_honesty_flag_makes_not_ok(self) -> None:
        self.write("resume.tex", "ok")
        fit_payload = {"ok": True, "verdict": "OK", "text": "fit: OK"}
        with mock.patch.object(P, "_compile", return_value=(True, "")), \
             mock.patch.object(P, "_fit_json", return_value=(fit_payload, "fit: OK")), \
             mock.patch("lint_honesty.lint_resume", return_value=["forbidden tech 'Rust'"]):
            rep = P.build_and_check(self.company)
        self.assertFalse(rep.ok)
        self.assertIn("Rust", rep.text)


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
        self.assertIn("assembled from slots", rep.text)
        self.assertIn("built", rep.text)


class CoverCheck(TailorTempCase):
    def test_compile_failure(self) -> None:
        self.write("cover_letter.tex", "garbage")
        with mock.patch.object(P, "_compile", return_value=(False, "! LaTeX Error")):
            rep = P.cover_check(self.company)
        self.assertFalse(rep.ok)
        self.assertIn("FAILED to compile", rep.text)


@unittest.skipUnless(has_pdflatex() and has_pdfplumber(),
                     "needs pdflatex + pdfplumber for a real build")
class EndToEnd(TailorTempCase):
    def test_real_assemble_compile_fit_honesty(self) -> None:
        self.write_slots(self.valid_slot_data())
        rep = P.assemble_and_check(self.company)
        # compiled (not a FAILED report) and produced a real PDF
        self.assertNotIn("FAILED to compile", rep.text)
        self.assertTrue((self.out_dir / "Khoa_Ngo_resume.pdf").exists())
        # the fit checker ran and returned a structured verdict
        self.assertIsNotNone(rep.fit)
        assert rep.fit is not None
        self.assertIn(rep.fit["verdict"],
                      {"OK", "UNDERFULL", "OVERFULL", "SPILLOVER", "MULTIPAGE"})
        self.assertIn("recompiled", rep.text)
        # honesty linter ran on the assembled resume
        self.assertIn("honesty (resume)", rep.text)


if __name__ == "__main__":
    unittest.main()
