#!/usr/bin/env python3
"""The Slot concern, end to end -- the single home for the model's deliverable.

The **slot** is what the model produces for one JD: which experiences/projects,
which bullets (verbatim by id or a light reword), the skills rows, plus the
``company`` stem and any ``uncovered`` must-haves. This module owns that concept
whole:

  * the **canonical type** -- a plain ``@dataclass`` :class:`Slots` (with
    :class:`EntrySpec` / :class:`BulletSpec`) that the deterministic chain threads
    around. It mirrors the on-disk shape faithfully: ``company`` and ``uncovered``
    ride on it, so the chain never re-parses a dict to read them.
  * the **on-disk JSON shape** -- the :class:`SlotsData` / :class:`BlockData` /
    :class:`BulletData` TypedDicts (what lands in ``output/<stem>/resume.slots.json``).
  * **parsing / loading** -- :func:`parse_slots` (structural validator) and
    :func:`from_json` (read + validate a slot file at any path).
  * **serialization** -- :func:`to_data` (canonical -> on-disk dict) and the two
    JSON renderers :func:`compact_slots_json` (dataset baseline) /
    :func:`pretty_slots_json` (shipped slot file).

This module is deliberately **pydantic-free**: the pydantic model-output schema
lives in ``tailor/llm.py``, and the adapter ``from_model(pydantic) -> Slots`` lives
there too. The dependency points core <- llm, never the reverse, so the
deterministic core never imports the SDK contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import NotRequired, TypedDict, cast


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class SlotsError(Exception):
    """Raised when the slot file is missing, unparseable, or structurally wrong."""


# --------------------------------------------------------------------------- #
# On-disk JSON shape (the wire format of a slot file)
# --------------------------------------------------------------------------- #
# What ``to_data`` (and the llm adapter ``from_model``) emit and what the
# deterministic core threads around (chain / capture). It is the typed mirror of
# the dataclass :class:`Slots` below; :func:`parse_slots` validates arbitrary
# decoded JSON (typed ``object``) back into that dataclass.
class BulletData(TypedDict, total=False):
    """One bullet pick: exactly one of ``id`` (verbatim) XOR ``text`` (reword)."""
    id: int
    text: str


class BlockData(TypedDict):
    """One chosen experience/project: master ``key`` + bullet picks (+ optional emph)."""
    key: str
    bullets: list[BulletData]
    emph: NotRequired[str]


class SlotsData(TypedDict):
    """The full slot deliverable as plain JSON-able data (``company``/``uncovered``
    ride along; the assembler ignores them)."""
    company: str
    experiences: list[BlockData]
    projects: list[BlockData]
    skills: list[list[str]]
    uncovered: list[str]


# --------------------------------------------------------------------------- #
# Canonical type (what the deterministic chain threads around)
# --------------------------------------------------------------------------- #
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
    """The canonical slot deliverable -- a faithful mirror of the on-disk shape.

    ``company`` and ``uncovered`` ride on the dataclass (not just the dict) so the
    orchestrator reads them off one real object and the chain never re-parses.
    """
    company: str
    experiences: list[EntrySpec]
    projects: list[EntrySpec]
    skills: list[tuple[str, str]]
    uncovered: list[str]

    @property
    def selected_keys(self) -> list[str]:
        """Master keys actually picked, experiences first then projects."""
        return [e.key for e in self.experiences] + [p.key for p in self.projects]


# --------------------------------------------------------------------------- #
# Parsing / loading
# --------------------------------------------------------------------------- #
def _bullet(raw: object, where: str) -> BulletSpec:
    if not isinstance(raw, dict):
        raise SlotsError(f"{where}: each bullet must be an object, got {type(raw).__name__}")
    d = cast("dict[str, object]", raw)
    has_id = "id" in d
    has_text = "text" in d
    if has_id == has_text:  # neither, or both
        raise SlotsError(f"{where}: each bullet needs exactly one of 'id' or 'text'")
    if has_id:
        try:
            return BulletSpec(id=int(cast("str | int | float", d["id"])))
        except (TypeError, ValueError):
            raise SlotsError(f"{where}: bullet 'id' must be an integer, got {d['id']!r}")
    return BulletSpec(text=str(d["text"]))


def _entry_spec(raw: object, kind: str, idx: int) -> EntrySpec:
    where = f"{kind}[{idx}]"
    if not isinstance(raw, dict):
        raise SlotsError(f"{where}: must be an object, got {type(raw).__name__}")
    d = cast("dict[str, object]", raw)
    key = d.get("key")
    if not isinstance(key, str) or not key:
        raise SlotsError(f"{where}: missing string 'key'")
    bullets_raw = d.get("bullets", [])
    if not isinstance(bullets_raw, list):
        raise SlotsError(f"{where}: 'bullets' must be a list")
    bullets = [_bullet(b, f"{where}.bullets[{j}]")
               for j, b in enumerate(cast("list[object]", bullets_raw))]
    emph_raw = d.get("emph")
    emph = str(emph_raw) if emph_raw is not None else None
    return EntrySpec(key=key, bullets=bullets, emph=emph)


def _skill_rows(raw: object) -> list[tuple[str, str]]:
    if not isinstance(raw, list):
        raise SlotsError("'skills' must be a list of [category, content] rows")
    rows: list[tuple[str, str]] = []
    for i, row in enumerate(cast("list[object]", raw)):
        if not isinstance(row, (list, tuple)) or len(cast("list[object]", row)) != 2:
            raise SlotsError(f"skills[{i}] must be a [category, content] pair, got {row!r}")
        cat, content = cast("list[object]", row)
        rows.append((str(cat), str(content)))
    return rows


def parse_slots(raw: object) -> Slots:
    """Validate a decoded slot object's STRUCTURE and return a typed ``Slots``.

    ``company`` defaults to ``""`` and ``uncovered`` to ``[]`` when absent, so a
    slot file written before those fields existed still parses cleanly.
    """
    if not isinstance(raw, dict):
        raise SlotsError(f"slot file must be a JSON object, got {type(raw).__name__}")
    d = cast("dict[str, object]", raw)
    company_raw = d.get("company", "")
    company = str(company_raw) if company_raw is not None else ""
    exp_raw = d.get("experiences", [])
    prj_raw = d.get("projects", [])
    unc_raw = d.get("uncovered", [])
    if not isinstance(exp_raw, list) or not isinstance(prj_raw, list):
        raise SlotsError("'experiences' and 'projects' must be lists")
    if not isinstance(unc_raw, list):
        raise SlotsError("'uncovered' must be a list of strings")
    experiences = [_entry_spec(e, "experiences", i) for i, e in enumerate(cast("list[object]", exp_raw))]
    projects = [_entry_spec(p, "projects", i) for i, p in enumerate(cast("list[object]", prj_raw))]
    skills = _skill_rows(d.get("skills", []))
    uncovered = [str(x) for x in cast("list[object]", unc_raw)]
    return Slots(company=company, experiences=experiences, projects=projects,
                 skills=skills, uncovered=uncovered)


def from_json(path: Path) -> Slots:
    """Load + structurally validate a slot file at an arbitrary path.

    The orchestrator writes the LLM's slots to a scratch dir and assembles there;
    only the final accepted pass lands in ``output/<stem>/``. Both paths flow
    through this one loader so the slot-file contract has a single home.
    """
    if not path.exists():
        raise SlotsError(f"missing slot file: {path}")
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SlotsError(f"slot file is not valid JSON: {e}")
    return parse_slots(data)


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #
def to_data(slots: Slots) -> SlotsData:
    """Canonical ``Slots`` -> the plain dict written to ``resume.slots.json``.

    Bullet objects serialize to exactly ``{"id": n}`` or ``{"text": "..."}`` -- the
    closed-pool / verbatim contract the assembler validates. Key order is fixed
    (company, experiences, projects, skills, uncovered); the assembler ignores
    ``company``/``uncovered`` but they round-trip on disk.
    """
    def bullet(b: BulletSpec) -> BulletData:
        return {"id": b.id} if b.id is not None else {"text": b.text or ""}

    def block(e: EntrySpec) -> BlockData:
        d: BlockData = {"key": e.key, "bullets": [bullet(b) for b in e.bullets]}
        if e.emph:
            d["emph"] = e.emph
        return d
    return {
        "company": slots.company,
        "experiences": [block(e) for e in slots.experiences],
        "projects": [block(e) for e in slots.projects],
        "skills": [[cat, content] for cat, content in slots.skills],
        "uncovered": list(slots.uncovered),
    }


def _slots_json(slots_data: SlotsData, *, explode_lists: bool) -> str:
    """Render slots with one top-level key per line and bullets always inline.

    Plain ``json.dumps(indent=2)`` explodes every ``{"id": N}`` bullet onto 3
    lines (~80 lines total) -- unreadable. Both slot artifacts we ship instead
    keep each bullet inline; they differ only in how far a list value unfolds:

    * ``explode_lists=False`` -- collapse each top-level value (experiences /
      projects / skills / uncovered) onto a single line (~10 lines). Used for
      the dataset baseline, read at a glance and diffed section-by-section.
    * ``explode_lists=True`` -- give each list ENTRY its own line, indented one
      level, the entry itself inline. Used for the shipped ``resume.slots.json``:
      one diffable line per experience / project / skill / uncovered item, with
      the bullet pool still inline. (Empty / non-list values stay inline.)
    """
    def inline(value: object) -> str:
        return json.dumps(value, separators=(", ", ": "), ensure_ascii=False)

    items: list[tuple[str, object]] = list(slots_data.items())
    lines = ["{"]
    for i, (key, value) in enumerate(items):
        tail = "," if i < len(items) - 1 else ""
        kj = json.dumps(key, ensure_ascii=False)
        if explode_lists and isinstance(value, list) and value:
            entries = cast("list[object]", value)
            lines.append(f"  {kj}: [")
            for j, entry in enumerate(entries):
                etail = "," if j < len(entries) - 1 else ""
                lines.append(f"    {inline(entry)}{etail}")
            lines.append(f"  ]{tail}")
        else:
            lines.append(f"  {kj}: {inline(cast('object', value))}{tail}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def compact_slots_json(slots_data: SlotsData) -> str:
    """Dataset-baseline form: one top-level key per line, each value inline."""
    return _slots_json(slots_data, explode_lists=False)


def pretty_slots_json(slots_data: SlotsData) -> str:
    """Shipped form: one line per list entry, bullets inline (see reference)."""
    return _slots_json(slots_data, explode_lists=True)
