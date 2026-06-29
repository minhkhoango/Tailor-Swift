#!/usr/bin/env python3
"""Assemble output/<company>/resume.tex from a slot file + the master pool.

The LLM writes a small ``output/<company>/resume.slots.json`` (which projects /
experiences, which bullets by id, reworded bullets, the skills rows). This
script owns BOTH ends of that contract:

  * the slot-file SCHEMA -- the typed loader (``load_slots``) that turns the raw
    JSON into ``Slots`` (experiences/projects/skills), enforcing structure
    (id-XOR-text per bullet, [category, content] skill rows), and
  * the mechanical ASSEMBLY -- copy the preamble + heading + Education verbatim
    from ``assets/master_resume.tex``, emit the chosen experiences and projects
    (headings verbatim by ``@key``; bullets pulled byte-identical by id, or
    emitted from the slot's ``text``), then rebuild Technical Skills from the
    slot rows.

Ordering is deterministic and owned here, not by the model: experiences are
validated into master order (IOE before FPT); projects are sorted by their
master end-date, most recent first ("Present" beats any dated end). A stable
sort keeps slot order for a same-date tie -- the model's only ordering job.

Verbatim-by-id bullets are honesty-safe by construction. Errors (unknown key,
out-of-range id, >5 skill rows, a project stack with >3 items, or a `text`
reword padded materially longer than its source bullet) abort with a clear
message and a nonzero exit. Skipping a company already frozen in ``dataset/`` is
the orchestrator's job, not the assembler's -- this module just renders slots.

Usage:
    python3 -m tailor.core.assemble_resume <company>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NotRequired, TypedDict, cast

from . import tex_parse
from .tex_parse import Block, match_braces
from .paths import MASTER, OUTPUT, REPO_ROOT, RESUME_TEX, SLOTS_NAME


# --------------------------------------------------------------------------- #
# Slot-file schema (the LLM's contract with the assembler)
# --------------------------------------------------------------------------- #
class SlotsError(Exception):
    """Raised when the slot file is missing, unparseable, or structurally wrong."""


# The wire shape of a slot file: what ``slots_to_data`` (llm.py) emits and what
# the deterministic core threads around (chain / capture). It is the typed mirror
# of the dataclass ``Slots`` below; ``parse_slots`` validates arbitrary decoded
# JSON (typed ``object``) back into that dataclass.
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

    @property
    def selected_keys(self) -> list[str]:
        """Master keys actually picked, experiences first then projects."""
        return [e.key for e in self.experiences] + [p.key for p in self.projects]


def _slots_path(company: str) -> Path:
    return OUTPUT / company / SLOTS_NAME


def load_slots_from(path: Path) -> Slots:
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
    """Validate a decoded slot object's STRUCTURE and return a typed ``Slots``."""
    if not isinstance(raw, dict):
        raise SlotsError(f"slot file must be a JSON object, got {type(raw).__name__}")
    d = cast("dict[str, object]", raw)
    exp_raw = d.get("experiences", [])
    prj_raw = d.get("projects", [])
    if not isinstance(exp_raw, list) or not isinstance(prj_raw, list):
        raise SlotsError("'experiences' and 'projects' must be lists")
    experiences = [_entry_spec(e, "experiences", i) for i, e in enumerate(cast("list[object]", exp_raw))]
    projects = [_entry_spec(p, "projects", i) for i, p in enumerate(cast("list[object]", prj_raw))]
    skills = _skill_rows(d.get("skills", []))
    return Slots(experiences, projects, skills)


def load_slots(company: str) -> Slots:
    """Load + structurally validate ``output/<company>/resume.slots.json``."""
    path = _slots_path(company)
    if not path.exists():
        raise SlotsError(f"missing slot file: {path}")
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SlotsError(f"slot file is not valid JSON: {e}")
    return parse_slots(data)


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #
MAX_SKILL_ROWS = 5
# A project's \emph{} tech-stack line carries at most this many comma-separated
# items -- keep only the most relevant ones (the rest is noise on a packed page).
MAX_PROJECT_STACK = 3
# A `text` reword may swap a verb or splice in a JD keyword, but it must NOT pad
# the bullet to grow its rendered height: it may exceed its closest master
# bullet by at most this many words. Beyond that it reads as filler -- add a real
# pool bullet/project to fill the page instead. (UNDERFULL is never fixed by
# lengthening a bullet.) The match floor decides which master bullet it rewords.
MAX_REWORD_EXTRA_WORDS = 4
REWORD_MATCH_MIN = 0.40

_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*")

# Month name (full or 3-letter) -> ordinal, for parsing a project's end-date.
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
# A "Present" end sorts above every dated end.
_PRESENT_KEY = (9999, 13)


class AssembleError(Exception):
    """Raised for any unrecoverable slot/master mismatch."""


def _reword_tokens(body: str) -> list[str]:
    """Lowercased word tokens of a bullet body, for length/overlap comparison."""
    s = tex_parse.replace_href(body)
    s = re.sub(r"\\[A-Za-z]+", " ", s)        # strip control sequences
    s = s.replace("{", " ").replace("}", " ")
    return [t.lower() for t in _WORD_RE.findall(s)]


def _closest_master_bullet(text_tokens: list[str], block: Block) -> tuple[float, int]:
    """Best (jaccard_overlap, word_count) over the block's master bullets.

    The reworded ``text`` is meant to be a light reword of one master bullet;
    this finds which one (highest token-set overlap) and returns that master
    bullet's length so the caller can reject a reword that pads it taller.
    """
    tset = set(text_tokens)
    best_ratio = 0.0
    best_len = 0
    for raw in block.bullets:
        mtoks = _reword_tokens(raw)
        mset = set(mtoks)
        if not mset:
            continue
        ratio = len(tset & mset) / len(tset | mset)
        if ratio > best_ratio:
            best_ratio, best_len = ratio, len(mtoks)
    return best_ratio, best_len


@dataclass(frozen=True)
class RewordCheck:
    """Pure verdict on whether a ``text`` reword pads its closest master bullet.

    The assembler raises on ``not ok``; the inspect harness tabulates every
    field across all bullets without raising on the first violation.
    """
    ratio: float          # token-set jaccard vs the closest master bullet
    word_count: int       # length of the reword
    master_len: int       # length of that closest master bullet
    extra_words: int      # word_count - master_len (can be negative)
    ok: bool              # False only when it resembles a source AND over-pads it


def check_reword(text: str, block: Block) -> RewordCheck:
    """Measure a ``text`` reword against the block's master bullets (no raise)."""
    toks = _reword_tokens(text)
    ratio, master_len = _closest_master_bullet(toks, block)
    extra = len(toks) - master_len
    ok = not (ratio >= REWORD_MATCH_MIN and extra > MAX_REWORD_EXTRA_WORDS)
    return RewordCheck(ratio, len(toks), master_len, extra, ok)


def _bullet_tex(spec: BulletSpec, block: Block) -> str:
    """Render one bullet spec to a `\\resumeItem{...}` line body.

    ``spec`` carries exactly one of ``id`` / ``text`` (enforced by the slots
    loader). A verbatim ``id`` is pulled byte-identical; a ``text`` reword is
    rejected if it pads its closest master bullet beyond MAX_REWORD_EXTRA_WORDS.
    """
    if spec.id is not None:
        i = spec.id
        if not (1 <= i <= len(block.bullets)):
            raise AssembleError(
                f"{block.key}: bullet id {i} out of range (1..{len(block.bullets)})")
        body = block.bullets[i - 1].strip()
    else:
        body = (spec.text or "").strip()
        chk = check_reword(body, block)
        if not chk.ok:
            raise AssembleError(
                f"{block.key}: reworded bullet pads its source by "
                f"{chk.extra_words} words ({chk.word_count} vs master {chk.master_len}); "
                f"a reword may add at most {MAX_REWORD_EXTRA_WORDS}. Don't lengthen a "
                f"bullet to fill the page -- use the verbatim id, trim the reword, or "
                f"add a whole pool bullet/project instead.")
    return f"        \\resumeItem{{{body}}}"


def _bullets_block(specs: list[BulletSpec], block: Block) -> str:
    lines = ["      \\resumeItemListStart"]
    for spec in specs:
        lines.append(_bullet_tex(spec, block))
    lines.append("      \\resumeItemListEnd")
    return "\n".join(lines)


def _splice_emph(heading: str, new_emph: str) -> str:
    """Replace the inner of the heading's first \\emph{...} with new_emph."""
    m = re.search(r"\\emph\s*\{", heading)
    if not m:
        return heading
    _, after = match_braces(heading, m.end() - 1)
    return f"{heading[:m.start()]}\\emph{{{new_emph}}}{heading[after:]}"


def _emph_inner(heading: str) -> str | None:
    """Inner text of the heading's first \\emph{...}, or None if it has none."""
    m = re.search(r"\\emph\s*\{", heading)
    if not m:
        return None
    inner, _ = match_braces(heading, m.end() - 1)
    return inner


def stack_items(heading: str) -> list[str]:
    """The comma-separated tech items in a heading's first \\emph{...} (pure)."""
    inner = _emph_inner(heading)
    if inner is None:
        return []
    return [p.strip() for p in inner.split(",") if p.strip()]


def _validate_stack(key: str, heading: str) -> None:
    """A project's tech-stack \\emph{} line may list at most MAX_PROJECT_STACK items."""
    items = stack_items(heading)
    if items and len(items) > MAX_PROJECT_STACK:
        raise AssembleError(
            f"{key}: tech stack has {len(items)} items "
            f"({', '.join(items)}); keep the {MAX_PROJECT_STACK} most JD-relevant "
            f"and set 'emph' in the slot accordingly.")


def _validate_experiences(exp_specs: list[EntrySpec], blocks: dict[str, Block]) -> None:
    """Enforce the hard invariant: every master experience is kept, in master order.

    ``blocks`` preserves master order, so the experience keys read out of it give
    the canonical sequence (IOE before FPT). A slot that drops one or flips the
    order would otherwise assemble a silently-wrong resume with no flag.
    """
    required = [k for k, blk in blocks.items() if blk.kind == "experience"]
    keys = [s.key for s in exp_specs]
    missing = [k for k in required if k not in keys]
    if missing:
        raise AssembleError(
            f"experiences must keep all of {required} (missing {missing}); "
            f"both are always kept")
    ordered = [k for k in keys if k in required]
    if ordered != required:
        raise AssembleError(
            f"experiences must be in master order {required}, got {ordered}")


def _project_end_key(block: Block | None) -> tuple[int, int]:
    """(year, month) of a project's master end-date, for chronological sorting.

    The date range is the heading's last arg ("Sep 2025 -- Oct 2025",
    "May 2026 -- Present"); we read the part after the final ``--``/en-dash. A
    "Present" end sorts above any dated end. An unparseable/absent date sorts
    last so the real error (unknown key) still surfaces in ``_entry``.
    """
    if block is None or not block.heading_args:
        return (-1, -1)
    date_arg = block.heading_args[-1]
    end = re.split(r"\s*(?:--|–|—)\s*", date_arg)[-1].strip()
    if "present" in end.lower():
        return _PRESENT_KEY
    m = re.search(r"([A-Za-z]+)\.?\s+(\d{4})", end)
    if not m:
        return (-1, -1)
    month = _MONTHS.get(m.group(1)[:3].lower(), 0)
    return (int(m.group(2)), month)


def _entry(spec: EntrySpec, blocks: dict[str, Block], want_kind: str) -> str:
    key = spec.key
    if key not in blocks:
        raise AssembleError(f"unknown {want_kind} key: {key!r}")
    block = blocks[key]
    if block.kind != want_kind:
        raise AssembleError(f"{key!r} is a {block.kind}, not a {want_kind}")
    heading = block.heading
    if want_kind == "project":
        if spec.emph:
            heading = _splice_emph(heading, spec.emph)
        _validate_stack(key, heading)
    bullets = _bullets_block(spec.bullets, block)
    return f"    {heading}\n{bullets}"


def _skills_section(rows: list[tuple[str, str]]) -> str:
    if len(rows) > MAX_SKILL_ROWS:
        raise AssembleError(f"{len(rows)} skill rows > max {MAX_SKILL_ROWS}")
    body = ["\\section{Technical Skills}",
            " \\begin{itemize}[leftmargin=0.15in, label={}]",
            "    \\small{\\item{"]
    for cat, content in rows:
        body.append(f"     \\textbf{{{cat}}}{{: {content}}} \\\\")
    body += ["    }}", " \\end{itemize}"]
    return "\n".join(body)


def assemble_to(slots: Slots, out_dir: Path) -> Path:
    """Render a validated ``Slots`` into ``out_dir/resume.tex`` and return the path.

    Pure of company / dataset concerns: the orchestrator points this at a scratch
    dir for in-flight passes and at ``output/<stem>/`` only for the final accepted
    one. Skip-the-frozen-company logic lives in the orchestrator, not here.
    """
    master = MASTER.read_text(encoding="utf-8")
    blocks = tex_parse.parse_master(master)

    doc_start = master.index("\\documentclass")
    exp_marker = master.index("%-----------EXPERIENCE-----------")
    preamble = master[doc_start:exp_marker].rstrip() + "\n"

    _validate_experiences(slots.experiences, blocks)
    # Projects sort by master end-date, most recent first; stable -> a same-date
    # tie keeps slot order (the model's only remaining ordering call).
    sorted_projects = sorted(
        slots.projects, key=lambda p: _project_end_key(blocks.get(p.key)), reverse=True)

    experiences = "\n\n".join(_entry(e, blocks, "experience") for e in slots.experiences)
    projects = "\n\n".join(_entry(p, blocks, "project") for p in sorted_projects)
    skills = _skills_section(slots.skills)

    parts = [
        preamble,
        "%-----------EXPERIENCE-----------",
        "\\section{Experience}",
        "  \\resumeSubHeadingListStart",
        "",
        experiences,
        "",
        "  \\resumeSubHeadingListEnd",
        "",
        "%-----------PROJECTS-----------",
        "\\section{Projects}",
        "  \\resumeSubHeadingListStart",
        "",
        projects,
        "",
        "  \\resumeSubHeadingListEnd",
        "",
        "%-----------TECHNICAL SKILLS-----------",
        skills,
        "",
        "%-------------------------------------------",
        "\\end{document}",
        "",
    ]
    resume_tex = "\n".join(parts)

    out_dir.mkdir(parents=True, exist_ok=True)
    tex_path = out_dir / RESUME_TEX
    tex_path.write_text(resume_tex, encoding="utf-8")
    return tex_path


def assemble_dir(work_dir: Path) -> Path:
    """Read ``work_dir/resume.slots.json`` and assemble ``work_dir/resume.tex``."""
    return assemble_to(load_slots_from(work_dir / SLOTS_NAME), work_dir)


def assemble(company: str) -> Path:
    """Assemble ``output/<company>/resume.tex`` from its slot file (CLI/back-compat)."""
    return assemble_dir(OUTPUT / company)


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble resume.tex from a slot file.")
    ap.add_argument("company", help="company stem under output/")
    args = ap.parse_args()
    try:
        path = assemble(args.company)
    except (AssembleError, SlotsError) as e:
        print(f"assemble_resume: {e}", file=sys.stderr)
        return 1
    print(f"assembled {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
