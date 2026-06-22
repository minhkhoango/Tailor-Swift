#!/usr/bin/env python3
"""Typed loader for the slot file -- the LLM's contract with the assembler.

``output/<company>/resume.slots.json`` is the small declarative pick a /tailor
turn writes: which experiences/projects, which bullets (verbatim by id or a light
reword by text), the project tech-stack overrides, and the skills rows. Its shape
used to be re-read with raw ``json.loads`` + ``.get(...)`` in three places --
``assemble_resume.py`` (the full structure), ``lint_honesty.py`` (the selected
keys), and ``post_save_build.py`` (the ``force`` flag). The schema now lives here
once, parsed into typed values; callers cross one interface.

This module owns the file's STRUCTURE only (types, required keys, id-XOR-text per
bullet). The SEMANTIC rules -- id in range, reword not padded, both experiences
kept in master order, <=5 skill rows, <=3 stack items -- stay in the assembler,
where they are checked against the master pool.

Public surface:
    load_slots(company) -> Slots          # strict; raises SlotsError on bad shape
    read_force(company) -> bool           # lenient; never raises
    parse(raw) -> Slots                    # pure: dict -> Slots
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from paths import OUTPUT


class SlotsError(Exception):
    """Raised when the slot file is missing, unparseable, or structurally wrong."""


@dataclass(frozen=True)
class BulletSpec:
    """One chosen bullet: verbatim by ``id`` XOR a reworded ``text``."""
    id: int | None = None
    text: str | None = None


@dataclass(frozen=True)
class EntrySpec:
    """One chosen experience or project: its master ``key`` + bullet picks.

    ``emph`` is the optional project tech-stack override (ignored for experiences).
    """
    key: str
    bullets: list[BulletSpec]
    emph: str | None = None


@dataclass(frozen=True)
class Slots:
    experiences: list[EntrySpec]
    projects: list[EntrySpec]
    skills: list[tuple[str, str]]
    force: bool

    @property
    def selected_keys(self) -> list[str]:
        """Master keys actually picked, experiences first then projects."""
        return [e.key for e in self.experiences] + [p.key for p in self.projects]


def _slots_path(company: str) -> Path:
    return OUTPUT / company / "resume.slots.json"


def _bullet(raw: Any, where: str) -> BulletSpec:
    if not isinstance(raw, dict):
        raise SlotsError(f"{where}: each bullet must be an object, got {type(raw).__name__}")
    d = cast("dict[str, Any]", raw)
    has_id = "id" in d
    has_text = "text" in d
    if has_id == has_text:  # neither, or both
        raise SlotsError(f"{where}: each bullet needs exactly one of 'id' or 'text'")
    if has_id:
        try:
            return BulletSpec(id=int(d["id"]))
        except (TypeError, ValueError):
            raise SlotsError(f"{where}: bullet 'id' must be an integer, got {d['id']!r}")
    return BulletSpec(text=str(d["text"]))


def _entry(raw: Any, kind: str, idx: int) -> EntrySpec:
    where = f"{kind}[{idx}]"
    if not isinstance(raw, dict):
        raise SlotsError(f"{where}: must be an object, got {type(raw).__name__}")
    d = cast("dict[str, Any]", raw)
    key = d.get("key")
    if not isinstance(key, str) or not key:
        raise SlotsError(f"{where}: missing string 'key'")
    bullets_raw = d.get("bullets", [])
    if not isinstance(bullets_raw, list):
        raise SlotsError(f"{where}: 'bullets' must be a list")
    bullets = [_bullet(b, f"{where}.bullets[{j}]")
               for j, b in enumerate(cast("list[Any]", bullets_raw))]
    emph_raw = d.get("emph")
    emph = str(emph_raw) if emph_raw is not None else None
    return EntrySpec(key=key, bullets=bullets, emph=emph)


def _skill_rows(raw: Any) -> list[tuple[str, str]]:
    if not isinstance(raw, list):
        raise SlotsError("'skills' must be a list of [category, content] rows")
    rows: list[tuple[str, str]] = []
    for i, row in enumerate(cast("list[Any]", raw)):
        if not isinstance(row, (list, tuple)) or len(cast("list[Any]", row)) != 2:
            raise SlotsError(f"skills[{i}] must be a [category, content] pair, got {row!r}")
        cat, content = cast("list[Any]", row)
        rows.append((str(cat), str(content)))
    return rows


def parse(raw: Any) -> Slots:
    """Validate a decoded slot object's STRUCTURE and return a typed ``Slots``."""
    if not isinstance(raw, dict):
        raise SlotsError(f"slot file must be a JSON object, got {type(raw).__name__}")
    d = cast("dict[str, Any]", raw)
    exp_raw = d.get("experiences", [])
    prj_raw = d.get("projects", [])
    if not isinstance(exp_raw, list) or not isinstance(prj_raw, list):
        raise SlotsError("'experiences' and 'projects' must be lists")
    experiences = [_entry(e, "experiences", i) for i, e in enumerate(cast("list[Any]", exp_raw))]
    projects = [_entry(p, "projects", i) for i, p in enumerate(cast("list[Any]", prj_raw))]
    skills = _skill_rows(d.get("skills", []))
    return Slots(experiences, projects, skills, bool(d.get("force", False)))


def load_raw(company: str) -> dict[str, Any]:
    """Read + JSON-decode the slot file. Raises ``SlotsError`` on missing/bad JSON."""
    path = _slots_path(company)
    if not path.exists():
        raise SlotsError(f"missing slot file: {path}")
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SlotsError(f"slot file is not valid JSON: {e}")
    if not isinstance(data, dict):
        raise SlotsError("slot file must be a JSON object")
    return cast("dict[str, Any]", data)


def load_slots(company: str) -> Slots:
    """Load + structurally validate ``output/<company>/resume.slots.json``."""
    return parse(load_raw(company))


def read_force(company: str) -> bool:
    """The ``force`` flag, read leniently -- never raises, defaults ``False``.

    Used by the hook to decide whether to pass ``--force`` to the assembler; a
    malformed slot file is left for the assembler to report, so this stays quiet.
    """
    try:
        return bool(load_raw(company).get("force", False))
    except SlotsError:
        return False
