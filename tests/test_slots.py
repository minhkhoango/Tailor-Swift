#!/usr/bin/env python3
# pyright: reportPrivateUsage=false
"""Tests for the slot schema (now owned by tailor.core.slots): structural
validation of the slot file into typed values."""

from __future__ import annotations

import unittest

from _helpers import TailorTempCase
from tailor.core import slots as A
from tailor.core.slots import SlotsError


class Parse(unittest.TestCase):
    def test_full_shape(self) -> None:
        raw: dict[str, object] = {
            "experiences": [{"key": "ioe", "bullets": [{"id": 2}, {"text": "x"}]}],
            "projects": [{"key": "lens", "emph": "A, B", "bullets": []}],
            "skills": [["Languages", "Python"]],
        }
        got = A.parse_slots(raw)
        self.assertEqual(got.experiences[0].key, "ioe")
        self.assertEqual(got.experiences[0].bullets[0].id, 2)
        self.assertIsNone(got.experiences[0].bullets[0].text)
        self.assertEqual(got.experiences[0].bullets[1].text, "x")
        self.assertEqual(got.projects[0].emph, "A, B")
        self.assertEqual(got.skills, [("Languages", "Python")])

    def test_defaults_when_keys_absent(self) -> None:
        got = A.parse_slots({})
        self.assertEqual(got.experiences, [])
        self.assertEqual(got.projects, [])
        self.assertEqual(got.skills, [])

    def test_selected_keys_order(self) -> None:
        raw: dict[str, object] = {
            "experiences": [{"key": "ioe", "bullets": []}, {"key": "fpt", "bullets": []}],
            "projects": [{"key": "lens", "bullets": []}],
        }
        got = A.parse_slots(raw)
        self.assertEqual(got.selected_keys, ["ioe", "fpt", "lens"])

    def test_bullet_needs_exactly_one_of_id_text(self) -> None:
        neither: dict[str, object] = {"experiences": [{"key": "ioe", "bullets": [{}]}]}
        with self.assertRaises(SlotsError):
            A.parse_slots(neither)
        with self.assertRaises(SlotsError):
            A.parse_slots({"experiences": [{"key": "ioe", "bullets": [{"id": 1, "text": "x"}]}]})

    def test_bullet_id_must_be_int(self) -> None:
        with self.assertRaises(SlotsError):
            A.parse_slots({"experiences": [{"key": "ioe", "bullets": [{"id": "two"}]}]})

    def test_missing_key_raises(self) -> None:
        no_key: dict[str, object] = {"experiences": [{"bullets": []}]}
        with self.assertRaises(SlotsError):
            A.parse_slots(no_key)

    def test_skill_row_must_be_pair(self) -> None:
        with self.assertRaises(SlotsError):
            A.parse_slots({"skills": [["only-one"]]})

    def test_top_level_must_be_object(self) -> None:
        with self.assertRaises(SlotsError):
            A.parse_slots([1, 2, 3])

    def test_experiences_must_be_list(self) -> None:
        with self.assertRaises(SlotsError):
            A.parse_slots({"experiences": {"key": "ioe"}})


class LoadFromDisk(TailorTempCase):
    def test_load_slots_round_trip(self) -> None:
        self.write_slots(self.valid_slot_data())
        got = A.from_json(self.out_dir / "resume.slots.json")
        self.assertEqual([e.key for e in got.experiences], ["ioe", "fpt"])

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(SlotsError):
            A.from_json(self.out_dir / "resume.slots.json")

    def test_bad_json_raises(self) -> None:
        self.write("resume.slots.json", "{not json")
        with self.assertRaises(SlotsError):
            A.from_json(self.out_dir / "resume.slots.json")


if __name__ == "__main__":
    unittest.main()
