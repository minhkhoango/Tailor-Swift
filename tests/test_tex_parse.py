#!/usr/bin/env python3
# pyright: reportPrivateUsage=false
"""Tests for tex_parse: brace matching, comment stripping, parsing the master."""

from __future__ import annotations

import unittest

from _helpers import BLOCKS, MASTER
from tailor.core import tex_parse as T


class MatchBraces(unittest.TestCase):
    def test_nested(self) -> None:
        inner, after = T.match_braces("{a{b}c}d", 0)
        self.assertEqual(inner, "a{b}c")
        self.assertEqual(after, 7)

    def test_escaped_braces_ignored(self) -> None:
        inner, _ = T.match_braces(r"{a\{b\}c}", 0)
        self.assertEqual(inner, r"a\{b\}c")

    def test_unbalanced_returns_rest(self) -> None:
        inner, after = T.match_braces("{abc", 0)
        self.assertEqual(inner, "abc")
        self.assertEqual(after, 4)


class StripComments(unittest.TestCase):
    def test_drops_unescaped_comment(self) -> None:
        self.assertEqual(T.strip_tex_comments("a % b\nc"), "a \nc")

    def test_keeps_escaped_percent(self) -> None:
        self.assertEqual(T.strip_tex_comments(r"99\% done % cut"), r"99\% done ")


class Href(unittest.TestCase):
    def test_collapses_to_shown_text(self) -> None:
        self.assertEqual(T.replace_href(r"see \href{http://x}{the link} now"),
                         "see the link now")


class ResumeItems(unittest.TestCase):
    def test_extracts_bodies_in_order(self) -> None:
        tex = r"\resumeItem{first} \resumeItem{second{nested}}"
        self.assertEqual(T.resume_items(tex), ["first", "second{nested}"])

    def test_ignores_resumeitemlist_macros(self) -> None:
        tex = r"\resumeItemListStart \resumeItem{only} \resumeItemListEnd"
        self.assertEqual(T.resume_items(tex), ["only"])


class Numbers(unittest.TestCase):
    def test_ranges_decimals_commas(self) -> None:
        got = T.numbers_in(r"on \$4{,}000, 1--14 day, 10/10 runs, 99.9\% uptime")
        self.assertEqual(dict(got), {"4000": 1, "1": 1, "14": 1, "10": 2, "99.9": 1})


class SkillRows(unittest.TestCase):
    def test_master_first_two_categories(self) -> None:
        rows = T.extract_skill_rows(MASTER)
        self.assertEqual([c for c, _ in rows][:2], ["Languages", "Frameworks"])


class ParseMaster(unittest.TestCase):
    def test_all_keys(self) -> None:
        self.assertEqual(
            sorted(BLOCKS),
            ["autoly", "fpt", "ioe", "local_lens",
             "p4_stack", "pr_pilot", "tailor_swift"])

    def test_kinds_and_bullet_counts(self) -> None:
        self.assertEqual(BLOCKS["ioe"].kind, "experience")
        self.assertEqual(BLOCKS["local_lens"].kind, "project")
        self.assertEqual(len(BLOCKS["local_lens"].bullets), 5)
        self.assertEqual(len(BLOCKS["pr_pilot"].bullets), 2)

    def test_project_heading_has_emph(self) -> None:
        self.assertIn("\\emph", BLOCKS["local_lens"].heading_args[0])


if __name__ == "__main__":
    unittest.main()
