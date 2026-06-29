#!/usr/bin/env python3
# pyright: reportUnusedImport=false
"""Tests for the scrape feeder's pure helpers.

Only the network/browser-free functions are exercised here -- importing
``tailor.core.scrape`` is safe because playwright is a lazy/TYPE_CHECKING-only
dependency. The key regression guard is ``clean_lines``: a JSON ``null`` in a
requirements/responsibilities array must DROP, never become the literal word
"None" (which would pollute both the JD body and its content fingerprint).
"""

from __future__ import annotations

import unittest

import _helpers  # noqa: F401  (path setup)
from tailor.core.scrape import clean_lines, content_fingerprint, format_job_text


class CleanLinesTests(unittest.TestCase):
    def test_drops_null_number_and_dict_keeps_trimmed_strings(self) -> None:
        items = ["  Build APIs  ", None, "", 42, {"x": 1}, "Ship features", "   "]
        self.assertEqual(clean_lines(items), ["Build APIs", "Ship features"])

    def test_null_never_becomes_literal_none(self) -> None:
        # the #1 regression: str(None) == "None" used to slip through as truthy
        self.assertNotIn("None", clean_lines([None, None]))
        self.assertEqual(clean_lines([None, None]), [])

    def test_non_list_yields_empty(self) -> None:
        self.assertEqual(clean_lines(None), [])
        self.assertEqual(clean_lines("Build APIs"), [])
        self.assertEqual(clean_lines({"requirements": ["a"]}), [])


class FingerprintTests(unittest.TestCase):
    def test_null_in_array_does_not_change_fingerprint(self) -> None:
        # two postings with identical real content but a stray null differ only
        # in that null -- they must hash the same now that null is dropped.
        a = {"requirements": ["Python", "SQL"], "responsibilities": ["Ship"]}
        b = {"requirements": ["Python", None, "SQL"], "responsibilities": ["Ship", None]}
        self.assertEqual(content_fingerprint(a), content_fingerprint(b))


class FormatJobTextTests(unittest.TestCase):
    def test_body_above_marker_excludes_links_and_nulls(self) -> None:
        detail = {
            "requirements": ["Strong Python", None],
            "responsibilities": ["Own the pipeline"],
            "application_url": "https://example.com/apply",
        }
        text = format_job_text(detail, job_id="abc123")
        body = text.split("tailor ignores below")[0]
        self.assertIn("Strong Python", body)
        self.assertNotIn("None", body)
        self.assertNotIn("example.com", body)          # link sits below the marker
        self.assertIn("https://example.com/apply", text)


if __name__ == "__main__":
    unittest.main()
