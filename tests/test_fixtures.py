#!/usr/bin/env python3
# pyright: reportPrivateUsage=false, reportUnusedImport=false
"""Data-driven tailor fixtures: every subject under ``tests/fixtures/`` carries
its own labels, so adding a case is dropping a folder -- never editing this file.

Each subject folder mirrors the real ``output/<company>/`` layout::

    tests/fixtures/<subject>/
        resume.slots.json   the assembler's input
        expected.tex        (optional) byte-exact golden for golden_tex subjects
        expected.json        the labels

``expected.json`` fields (all optional; an absent field is simply not checked):

    assemble_error  str   assembler must raise with this substring (text, no compile)
    golden_tex      str   assembled resume.tex must byte-equal this sibling file
    honesty_flags   list  honesty_flags() substrings that must be present ([] == clean)
    project_count   int   number of projects the slot carries
    structure_warn  bool  True iff the slot's project count != EXPECTED_PROJECTS
    verdict         str   fit verdict (needs compile) -- OK/UNDERFULL/MULTIPAGE/...
    fullness_range  [lo,hi] measured fullness must fall in [lo, hi] (needs compile)
    spillover_flags int   number of spillover-flagged bullets (needs compile)
    page_count      int   rendered page count (needs compile)

Execution is split so the no-compile checks always run while the PDF-dependent
ones skip cleanly without a LaTeX toolchain: ``test_text_subjects`` covers the
first five fields, ``test_fit_subjects`` the last four.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

import _helpers  # noqa: F401  (puts the repo root on sys.path)
from _helpers import has_pdflatex, has_pdfplumber

from tailor.core import assemble_resume, check_resume_fit, pdf_compile
from tailor.core.assemble_resume import AssembleError, SlotsError
from tailor.core.chain import EXPECTED_PROJECTS, honesty_flags
from tailor.core.paths import DATASET, OUTPUT, RESUME_JOBNAME

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FIT_FIELDS = ("verdict", "fullness_range", "spillover_flags", "page_count")


def discover_subjects() -> list[tuple[str, Path, dict[str, Any]]]:
    """Every fixture dir holding an expected.json, as (name, dir, labels)."""
    if not FIXTURES.is_dir():
        return []
    out: list[tuple[str, Path, dict[str, Any]]] = []
    for d in sorted(FIXTURES.iterdir()):
        label_file = d / "expected.json"
        if d.is_dir() and label_file.is_file():
            labels = json.loads(label_file.read_text(encoding="utf-8"))
            out.append((d.name, d, labels))
    return out


class FixtureSubjects(unittest.TestCase):
    """Discover-and-stage every subject; assert only the labels it declares.

    Staging copies a subject's input files into a throwaway ``output/<tmp>/`` so
    the real path-resolving core (assemble / chain) runs unmodified, then the temp
    company is torn down -- the fixture dir itself stays read-only.
    """

    def setUp(self) -> None:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        self.subjects = discover_subjects()

    def _stage(self, subject_dir: Path) -> str:
        """Copy a subject's artifacts into a fresh temp company; return its name."""
        out_dir = Path(tempfile.mkdtemp(prefix="__fixture_", dir=OUTPUT))
        for name in ("resume.slots.json", "resume.tex"):
            src = subject_dir / name
            if src.is_file():
                shutil.copy(src, out_dir / name)
        return out_dir.name

    def _unstage(self, company: str) -> None:
        shutil.rmtree(OUTPUT / company, ignore_errors=True)
        shutil.rmtree(DATASET / company, ignore_errors=True)

    def test_text_subjects(self) -> None:
        """No-compile checks: assemble_error, golden_tex, honesty, structure, counts."""
        self.assertTrue(self.subjects, f"no fixtures discovered under {FIXTURES}")
        for name, sdir, labels in self.subjects:
            with self.subTest(subject=name):
                company = self._stage(sdir)
                try:
                    self._check_text(company, sdir, labels)
                finally:
                    self._unstage(company)

    def _check_text(self, company: str, sdir: Path, labels: dict[str, Any]) -> None:
        # assemble_error subjects: the assembler must reject; nothing else applies.
        if "assemble_error" in labels:
            with self.assertRaises((AssembleError, SlotsError)) as ctx:
                assemble_resume.assemble(company)
            self.assertIn(labels["assemble_error"], str(ctx.exception))
            return

        # Everything else needs a successfully assembled resume.tex first.
        assemble_resume.assemble(company)
        slots = assemble_resume.load_slots(company)

        if "golden_tex" in labels:
            produced = (OUTPUT / company / "resume.tex").read_text(encoding="utf-8")
            golden = (sdir / labels["golden_tex"]).read_text(encoding="utf-8")
            self.assertEqual(produced, golden, "assembled .tex drifted from golden")

        if "honesty_flags" in labels:
            flags = honesty_flags(OUTPUT / company, slots)
            expected = labels["honesty_flags"]
            if expected == []:
                self.assertEqual(flags, [], f"expected honesty clean, got {flags}")
            else:
                for needle in expected:
                    self.assertTrue(any(needle in f for f in flags),
                                    f"honesty flag {needle!r} not in {flags}")

        if "project_count" in labels:
            self.assertEqual(len(slots.projects), labels["project_count"])

        if "structure_warn" in labels:
            warn = len(slots.projects) != EXPECTED_PROJECTS
            self.assertEqual(warn, labels["structure_warn"])

    @unittest.skipUnless(has_pdflatex() and has_pdfplumber(),
                         "fit checks need pdflatex + pdfplumber")
    def test_fit_subjects(self) -> None:
        """PDF-dependent checks: verdict, fullness_range, spillover_flags, page_count."""
        for name, sdir, labels in self.subjects:
            if not any(k in labels for k in FIT_FIELDS):
                continue
            with self.subTest(subject=name):
                company = self._stage(sdir)
                try:
                    self._check_fit(company, labels)
                finally:
                    self._unstage(company)

    def _check_fit(self, company: str, labels: dict[str, Any]) -> None:
        work = OUTPUT / company
        assemble_resume.assemble(company)
        ok = pdf_compile.compile_tex(work / "resume.tex", RESUME_JOBNAME, 2)
        self.assertTrue(ok, f"{company}: resume.tex failed to compile")
        fit = check_resume_fit.report_to_dict(check_resume_fit.analyze_dir(work, company))

        if "verdict" in labels:
            self.assertEqual(fit["verdict"], labels["verdict"])
        if "page_count" in labels:
            self.assertEqual(fit["page_count"], labels["page_count"])
        if "spillover_flags" in labels:
            self.assertEqual(fit["spillover_flags"], labels["spillover_flags"])
        if "fullness_range" in labels:
            lo, hi = labels["fullness_range"]
            full = fit["fullness"]
            self.assertIsNotNone(full, "fullness is None (multi-page?) but a range was set")
            self.assertGreaterEqual(full, lo)
            self.assertLessEqual(full, hi)


if __name__ == "__main__":
    unittest.main()
