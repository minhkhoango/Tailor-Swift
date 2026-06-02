#!/usr/bin/env python3
"""Unit tests for check_resume_fit.py.

The pure functions are exercised with synthetic Word/Page objects and tex
snippets — no PDF and no pdfplumber needed. A final smoke test runs the full
pipeline against the real example_output/*/Khoa_Ngo_resume.pdf when pdfplumber
and those PDFs are available.

Run:  .venv/bin/python -m unittest test_check_resume_fit -v
"""

import unittest
from pathlib import Path

import check_resume_fit as m


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def words_from_lines(lines, line_h=14.0, top0=40.0):
    """lines: list[list[str]] -> list[Word] with line_id == row index."""
    ws = []
    for li, line in enumerate(lines):
        x = 72.0
        top = top0 + li * line_h
        for tok in line:
            ws.append(m.Word(tok, x, x + len(tok) * 5, top, top + 10.0, li))
            x += len(tok) * 5 + 5
    return ws


def norm_of(words):
    return [m.normalize_pdf_word(w.text) for w in words]


def spill(bullet_tokens, lines):
    words = words_from_lines(lines)
    fields, _ = m.detect_spillover(bullet_tokens, words, norm_of(words), 0)
    return fields


def page_with_bottom(content_bottom, content_top=40.0):
    w = m.Word("x", 72.0, 80.0, content_top, content_bottom, 0)
    return m.Page(m.PAGE_W_PT, m.PAGE_H_PT, [w])


# --------------------------------------------------------------------------- #
# A. tex parsing / normalization
# --------------------------------------------------------------------------- #
class TexParsing(unittest.TestCase):
    def test_A1_excludes_defs_and_comments(self):
        tex = (
            r"\newcommand{\resumeItem}[1]{\item\small{{#1}}}" "\n"
            r"\begin{document}" "\n"
            r"% \resumeItem{this is a comment and must be ignored}" "\n"
            r"\resumeItem{First real bullet here}" "\n"
            r"\resumeItemListStart" "\n"
            r"\resumeItem{Second real bullet here}" "\n"
            r"\end{document}" "\n"
        )
        items = m.extract_resume_items(tex)
        self.assertEqual(len(items), 2)
        self.assertIn("First real bullet", items[0])
        self.assertIn("Second real bullet", items[1])

    def test_A2_nested_braces_and_numbers(self):
        tex = (r"\begin{document}"
               r"\resumeItem{Defined a 0.4\% per-trade cost model clearing \$4{,}000 real capital}"
               r"\end{document}")
        items = m.extract_resume_items(tex)
        self.assertEqual(len(items), 1)
        toks = m.normalize_bullet(items[0])
        self.assertIn("0.4", toks)
        self.assertIn("4000", toks)
        self.assertIn("capital", toks)

    def test_A3_href_keeps_shown_drops_url(self):
        raw = r"Sourced from \href{http://example.com/secretpath}{the visible thread text}"
        toks = m.normalize_bullet(raw)
        self.assertIn("visible", toks)
        self.assertIn("thread", toks)
        self.assertNotIn("secretpath", toks)
        self.assertNotIn("example.com", " ".join(toks))

    def test_A4_unescape_and_markers(self):
        raw = r"R\&D \#1 priority for foo\_bar between a~b $\bullet$ done"
        toks = m.normalize_bullet(raw)
        self.assertIn("foo_bar", toks)
        self.assertIn("1", toks)          # \#1 -> 1
        self.assertIn("r&d", toks)         # internal & kept
        self.assertNotIn("bullet", toks)   # $\bullet$ stripped


# --------------------------------------------------------------------------- #
# B. line assignment
# --------------------------------------------------------------------------- #
class LineAssignment(unittest.TestCase):
    def test_B1_clusters_into_lines(self):
        raw = [m.Word("a", 0, 5, 50.0, 60, -1),
               m.Word("b", 6, 10, 50.4, 60, -1),
               m.Word("c", 0, 5, 62.0, 72, -1),
               m.Word("d", 6, 10, 62.1, 72, -1),
               m.Word("e", 0, 5, 200.0, 210, -1)]
        out = m.assign_line_ids_by_y(raw)
        self.assertEqual([w.line_id for w in out], [0, 0, 1, 1, 2])

    def test_B2_eps_boundary(self):
        raw = [m.Word("a", 0, 5, 50.0, 60, -1),
               m.Word("b", 0, 5, 52.0, 62, -1),   # gap 2 < eps -> same line
               m.Word("c", 0, 5, 58.0, 68, -1)]   # gap 6 > eps -> new line
        out = m.assign_line_ids_by_y(raw)
        self.assertEqual([w.line_id for w in out], [0, 0, 1])


# --------------------------------------------------------------------------- #
# C. alignment / spillover
# --------------------------------------------------------------------------- #
class Spillover(unittest.TestCase):
    def test_C1_three_word_last_line_flagged(self):
        toks = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda".split()
        lines = [toks[:8], toks[8:]]  # last line: iota kappa lambda (3 words)
        f = spill(toks, lines)
        self.assertEqual(f["n_lines"], 2)
        self.assertEqual(f["last_line_word_count"], 3)
        self.assertTrue(f["flagged"])

    def test_C2_six_word_last_line_not_flagged(self):
        toks = ("alpha beta gamma delta epsilon zeta eta theta "
                "iota kappa lambda mu nu xi").split()
        lines = [toks[:8], toks[8:]]  # last line 6 words
        f = spill(toks, lines)
        self.assertEqual(f["last_line_word_count"], 6)
        self.assertFalse(f["flagged"])

    def test_C3_single_line_not_flagged(self):
        toks = "one two three".split()
        f = spill(toks, [toks])
        self.assertEqual(f["n_lines"], 1)
        self.assertFalse(f["flagged"])

    def test_C4_boundaries(self):
        base = "a b c d e f g h".split()
        four = spill(base + "w x y z".split(), ["a b c d e f g h".split(), "w x y z".split()])
        self.assertEqual(four["last_line_word_count"], 4)
        self.assertTrue(four["flagged"])
        five = spill(base + "v w x y z".split(),
                     ["a b c d e f g h".split(), "v w x y z".split()])
        self.assertEqual(five["last_line_word_count"], 5)
        self.assertFalse(five["flagged"])

    def test_C5_markers_stripped(self):
        words = [m.Word("•", 0, 5, 40, 50, 0)] + words_from_lines([["alpha", "beta"]])
        kept = m.strip_markers(words)
        self.assertNotIn("•", [w.text for w in kept])
        self.assertEqual(len(kept), 2)

    def test_C6_hyphenation_prefix_match(self):
        # tex token 'client-side' vs rendered split 'client' 'side'
        toks = ["client-side", "rendering", "engine"]
        lines = [["client", "side", "rendering", "engine"]]
        f = spill(toks, lines)
        self.assertTrue(f["rendered"])
        self.assertGreaterEqual(f["match_ratio"], 0.55)

    def test_C7_ligature_match(self):
        self.assertTrue(m.tokens_match("file", m.normalize_pdf_word("ﬁle")))

    def test_C8_low_match_skipped(self):
        toks = ["completely", "different", "unmatched", "tokens", "here"]
        lines = [["nothing", "aligns", "at", "all", "really"]]
        f = spill(toks, lines)
        self.assertFalse(f["rendered"])
        self.assertLess(f["match_ratio"], 0.55)

    def test_C9_sequential_isolation(self):
        words = words_from_lines([["built", "x", "alpha"], ["built", "x", "beta"]])
        nw = norm_of(words)
        a1 = m.align_bullet(["built", "x", "alpha"], words, nw, 0)
        self.assertEqual(a1.matched_word_indices, [0, 1, 2])
        a2 = m.align_bullet(["built", "x", "beta"], words, nw, a1.end_index)
        self.assertEqual(a2.matched_word_indices, [3, 4, 5])


# --------------------------------------------------------------------------- #
# D. fullness
# --------------------------------------------------------------------------- #
class Fullness(unittest.TestCase):
    def test_D1_ninety_percent(self):
        full, _, cb = m.compute_fullness(page_with_bottom(684.0))
        self.assertAlmostEqual(full, 0.90, places=2)
        self.assertEqual(cb, 684.0)

    def test_D2_seventy_percent_underfull(self):
        full, _, _ = m.compute_fullness(page_with_bottom(540.0))
        self.assertAlmostEqual(full, 0.70, places=2)
        self.assertLess(full, m.FULLNESS_TARGET_LOW)

    def test_D3_over_one(self):
        self.assertAlmostEqual(m.compute_fullness(page_with_bottom(756.0))[0], 1.0, places=2)
        self.assertGreater(m.compute_fullness(page_with_bottom(772.0))[0], 1.0)


# --------------------------------------------------------------------------- #
# E. verdict precedence
# --------------------------------------------------------------------------- #
def _bullets(*flags):
    out = []
    for i, fl in enumerate(flags, 1):
        out.append(m.BulletReport(i, "p", True, 2, 3 if fl else 9, 1.0, fl))
    return out


class Verdict(unittest.TestCase):
    def test_E1_multipage(self):
        self.assertEqual(m.build_verdict(2, None, _bullets(True))[0], "MULTIPAGE")

    def test_E2_spillover_beats_underfull(self):
        self.assertEqual(m.build_verdict(1, 0.50, _bullets(True))[0], "SPILLOVER")

    def test_E3_ok(self):
        self.assertEqual(m.build_verdict(1, 0.90, _bullets(False, False))[0], "OK")

    def test_E4_overfull(self):
        self.assertEqual(m.build_verdict(1, 0.96, _bullets(False))[0], "OVERFULL")

    def test_E5_underfull(self):
        self.assertEqual(m.build_verdict(1, 0.70, _bullets(False))[0], "UNDERFULL")


# --------------------------------------------------------------------------- #
# F. end-to-end (pure) + real-PDF smoke
# --------------------------------------------------------------------------- #
class EndToEnd(unittest.TestCase):
    def test_F1_analyze_from_pages(self):
        tex = (r"\begin{document}"
               r"\resumeItem{Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda}"
               r"\resumeItem{Short single line bullet}"
               r"\end{document}")
        # bullet 1 wraps: last line carries the final 3 words (spillover)
        b1 = "Alpha beta gamma delta epsilon zeta eta theta".split()
        b1b = "iota kappa lambda".split()
        b2 = "Short single line bullet".split()
        words = words_from_lines([b1, b1b, b2])
        pages = [m.Page(m.PAGE_W_PT, m.PAGE_H_PT, words)]
        rep = m.analyze_from_pages(tex, pages, "Test")
        self.assertEqual(rep.page_count, 1)
        self.assertEqual(len(rep.bullets), 2)
        self.assertTrue(rep.bullets[0].flagged)
        self.assertFalse(rep.bullets[1].flagged)
        self.assertEqual(rep.verdict, "SPILLOVER")

    def test_F2_real_pdfs_smoke(self):
        if m.check_deps() is not None:
            self.skipTest("pdfplumber not installed")
        examples = m.EXAMPLES
        dirs = [d for d in examples.iterdir()
                if d.is_dir() and (d / f"{m.JOBNAME}.pdf").exists()
                and (d / "resume.tex").exists()] if examples.exists() else []
        if not dirs:
            self.skipTest("no example PDFs present")
        for d in dirs:
            rep = m.analyze_company(d.name)
            self.assertEqual(rep.page_count, 1, f"{d.name} not single page")
            self.assertTrue(0.0 < rep.fullness < 1.2, f"{d.name} fullness {rep.fullness}")
            # every bullet should align (these are real, faithfully-rendered resumes)
            skipped = [b.index for b in rep.bullets if not b.rendered]
            self.assertEqual(skipped, [], f"{d.name} had unaligned bullets {skipped}")


if __name__ == "__main__":
    unittest.main()
