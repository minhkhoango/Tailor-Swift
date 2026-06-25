#!/usr/bin/env python3
# pyright: reportPrivateUsage=false, reportMissingParameterType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
"""Tier-3 inspect harness: run the REAL chain on slot files and DUMP a full report.

Not a CLI subcommand -- a pytest-collected harness marked ``@pytest.mark.inspect``.
For each ``tests/inspect_inputs/<stem>/resume.slots.json`` (and, conveniently, every
``tests/fixtures/*/resume.slots.json``) it runs the real assemble -> compile -> fit ->
honesty chain WITHOUT raising on the first violation, and prints a complete status
report for a HUMAN to eyeball::

    pytest -s -m inspect

The test only asserts the chain *ran* (a Report came back); judging the CONTENT is
yours, from the terminal. The per-bullet reword deltas, emph cap, skills line-fit,
spillover list, number-traceability detail, and the advisory FORBIDDEN scan all come
from the pure checkers in ``core`` -- the harness just tabulates them.

Needs pdflatex + pdfplumber; skips cleanly without them.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import pytest

from _helpers import BLOCKS, has_pdflatex, has_pdfplumber

from tailor.core import check_resume_fit
from tailor.core.assemble_resume import (
    MAX_PROJECT_STACK,
    Slots,
    check_reword,
    load_slots_from,
    stack_items,
)
from tailor.core.chain import honesty_flags, run_chain
from tailor.core.paths import KEYWORDS

# Mark every test in this module as `inspect` so `pytest -m "not inspect"` skips it.
pytestmark = pytest.mark.inspect

INSPECT_INPUTS = Path(__file__).resolve().parent / "inspect_inputs"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def discover_inputs() -> list[tuple[str, Path]]:
    """(label, slots_path) for every inspect input + every fixture slot file."""
    found: list[tuple[str, Path]] = []
    for root in (INSPECT_INPUTS, FIXTURES):
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            slot = d / "resume.slots.json"
            if slot.is_file():
                found.append((f"{root.name}/{d.name}", slot))
    return found


def _forbidden_terms() -> list[str]:
    """Parse the FORBIDDEN section of keywords.md into a flat advisory term list."""
    text = KEYWORDS.read_text(encoding="utf-8")
    after = text.split("## FORBIDDEN", 1)
    if len(after) < 2:
        return []
    terms: list[str] = []
    for line in after[1].splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        body = re.sub(r"\*\*[^*]+:\*\*", "", line[2:])      # drop the "**Label:**"
        body = re.split(r"\(", body)[0]                      # drop parentheticals
        for tok in re.split(r"[,.]", body):
            tok = tok.strip().strip("*").strip()
            if len(tok) >= 2 and tok.lower() not in {"if", "off-limits", "until then"}:
                terms.append(tok)
    return terms


def _bullet_report(slots: Slots) -> list[str]:
    """Per-bullet: verbatim-by-id vs a `text` reword's word-delta + <=4-word verdict."""
    lines: list[str] = []
    for kind, entries in (("exp", slots.experiences), ("prj", slots.projects)):
        for e in entries:
            block = BLOCKS.get(e.key)
            for i, b in enumerate(e.bullets):
                if block is None:
                    lines.append(f"    [{kind}:{e.key}#{i}] UNKNOWN KEY")
                elif b.id is not None:
                    lines.append(f"    [{kind}:{e.key}#{i}] id={b.id} verbatim")
                else:
                    c = check_reword(b.text or "", block)
                    verdict = "ok" if c.ok else "OVER-PAD"
                    lines.append(
                        f"    [{kind}:{e.key}#{i}] reword {verdict}: "
                        f"{c.word_count}w vs master {c.master_len}w "
                        f"(delta {c.extra_words:+d}, jaccard {c.ratio:.2f})")
    return lines


def _emph_report(slots: Slots) -> list[str]:
    """Per-project emph tech-stack item count vs the cap."""
    lines: list[str] = []
    for p in slots.projects:
        if p.emph:
            items = [x.strip() for x in p.emph.split(",") if x.strip()]
            tag = "ok" if len(items) <= MAX_PROJECT_STACK else "OVER CAP"
            lines.append(f"    {p.key}: emph {len(items)} techs ({tag}) -> {p.emph}")
        else:
            block = BLOCKS.get(p.key)
            n = len(stack_items(block.heading)) if block else 0
            lines.append(f"    {p.key}: emph default ({n} master techs)")
    return lines


def _forbidden_report(work_dir: Path, terms: list[str]) -> list[str]:
    """Advisory: any FORBIDDEN term appearing as a whole word in the assembled tex."""
    tex = (work_dir / "resume.tex").read_text(encoding="utf-8").lower()
    hits = [t for t in terms if re.search(rf"\b{re.escape(t.lower())}\b", tex)]
    return [f"    ADVISORY hit: {h}" for h in hits] or ["    (clean)"]


def inspect_one(label: str, slots_path: Path) -> tuple[str, str]:
    """Run the real chain on one slot file; return (verdict, human report block)."""
    slots = load_slots_from(slots_path)
    scratch = Path(tempfile.mkdtemp(prefix="__inspect_"))
    try:
        slots_data = json.loads(slots_path.read_text(encoding="utf-8"))
        report = run_chain(label, slots_data, scratch)

        out: list[str] = [f"\n=== {label} ===",
                          f"  verdict: {report.verdict}  fill: {report.fill}  "
                          f"projects: {len(slots.projects)}  "
                          f"structure_warn: {report.structure_warn}"]

        out.append("  bullets:")
        out.extend(_bullet_report(slots))
        out.append("  emph (cap 3):")
        out.extend(_emph_report(slots))

        out.append("  number-traceability:")
        flags = honesty_flags(scratch, slots) if (scratch / "resume.tex").exists() else \
            ["(no resume.tex — assemble/compile failed)"]
        out.extend([f"    {f}" for f in (flags or ["clean"])])

        out.append("  FORBIDDEN scan (advisory):")
        if (scratch / "resume.tex").exists():
            out.extend(_forbidden_report(scratch, _forbidden_terms()))
        else:
            out.append("    (skipped — no tex)")

        # spillover + skills line-fit come from the compiled PDF, when present.
        pdf = scratch / "Khoa_Ngo_resume.pdf"
        if pdf.exists():
            fit = check_resume_fit.analyze_dir(scratch, label)
            spill = [b for b in fit.bullets if b.flagged]
            out.append(f"  spillover flags: {len(spill)}")
            out.extend([f"    [{b.index:02d}] last-line {b.last_line_word_count}w "
                        f'"{b.preview}"' for b in spill])
            wrapped = [s.category for s in fit.skill_rows if s.wrapped]
            out.append(f"  skills WRAP: {wrapped or 'none'}")
        else:
            out.append("  spillover/skills: (no PDF)")

        return report.verdict, "\n".join(out)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


class Inspect(unittest.TestCase):
    @unittest.skipUnless(has_pdflatex() and has_pdfplumber(),
                         "inspect harness needs pdflatex + pdfplumber")
    def test_inspect_dump(self) -> None:
        # Sanity-check the parser before the loop relies on it.
        self.assertIn("Java", _forbidden_terms())
        self.assertIn("Kubernetes", _forbidden_terms())

        inputs = discover_inputs()
        self.assertTrue(inputs, f"no inspect inputs under {INSPECT_INPUTS} or {FIXTURES}")
        for label, slot in inputs:
            with self.subTest(input=label):
                verdict, block = inspect_one(label, slot)
                print(block)                       # for the human (run with -s)
                self.assertTrue(verdict, f"{label}: chain produced no verdict")


if __name__ == "__main__":
    unittest.main()
