#!/usr/bin/env python3
# pyright: reportPrivateUsage=false
"""Tests for tailor_hook: the assemble -> compile -> fit -> honesty chain,
plus the one deterministic honesty check it now owns (number-traceability).

Failure paths and the fit-JSON seam are driven with monkeypatched stages so they
run without pdflatex. One real end-to-end build is included, skipped unless both
pdflatex and pdfplumber are available -- the "everything actually works" check.
"""

from __future__ import annotations

import unittest
from unittest import mock

from _helpers import BLOCKS, TailorTempCase, has_pdflatex, has_pdfplumber
import assemble_resume as A
import tailor_hook as P
import tex_parse as T


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

    def test_scoped_numbers_flag_untraceable_metric(self) -> None:
        self._assemble()
        tex = (self.out_dir / "resume.tex").read_text(encoding="utf-8")
        self.assertIn("Connected", tex)
        tex = tex.replace("Connected", "99999 Connected", 1)
        (self.out_dir / "resume.tex").write_text(tex, encoding="utf-8")
        flags = P.honesty_flags(self.company)
        self.assertTrue(any("99999" in f for f in flags))

    def test_missing_resume(self) -> None:
        flags = P.honesty_flags(self.company)
        self.assertTrue(any("missing" in f for f in flags))


class HonestyLine(unittest.TestCase):
    def test_clean_and_flags(self) -> None:
        self.assertEqual(P.honesty_line([]), "honesty: clean")
        self.assertEqual(P.honesty_line(["a", "b"]), "honesty: FLAGS [a; b]")


# --------------------------------------------------------------------------- #
# Structure: the project-count advisory (always exactly three)
# --------------------------------------------------------------------------- #
class StructureSegment(TailorTempCase):
    def _slots_with_projects(self, n: int) -> dict[str, object]:
        data = self.valid_slot_data()
        data["projects"] = [{"key": f"p{i}", "bullets": [{"id": 1}]} for i in range(n)]
        return data

    def test_three_projects_no_warning(self) -> None:
        self.write_slots(self._slots_with_projects(P.EXPECTED_PROJECTS))
        warn, line = P.structure_segment(self.company)
        self.assertFalse(warn)
        self.assertEqual(line, f"structure: {P.EXPECTED_PROJECTS} projects")

    def test_wrong_count_warns(self) -> None:
        self.write_slots(self._slots_with_projects(P.EXPECTED_PROJECTS + 1))
        warn, line = P.structure_segment(self.company)
        self.assertTrue(warn)
        assert line is not None
        self.assertIn("WARN", line)
        self.assertIn(f"{P.EXPECTED_PROJECTS + 1} projects", line)

    def test_no_slot_file_is_silent(self) -> None:
        warn, line = P.structure_segment(self.company)
        self.assertFalse(warn)
        self.assertIsNone(line)

    def test_warn_keeps_report_actionable_without_flipping_ok(self) -> None:
        self.write("resume.tex", "ok")
        self.write_slots(self._slots_with_projects(P.EXPECTED_PROJECTS + 1))
        fit_payload = {"ok": True, "verdict": "OK", "text": "fit: OK"}
        with mock.patch.object(P, "_compile", return_value=(True, "")), \
             mock.patch.object(P, "_fit_json", return_value=(fit_payload, "fit: OK")), \
             mock.patch.object(P, "honesty_flags", return_value=[]):
            rep = P.build_and_check(self.company)
        self.assertTrue(rep.ok)                       # advisory: fit+honesty still clean
        self.assertIn("structure: WARN", rep.text)    # but the warning is surfaced


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
