#!/usr/bin/env python3
"""Assemble output/<company>/resume.tex from a slot file + the master pool.

The LLM writes a small ``output/<company>/resume.slots.json`` (which projects /
experiences, which bullets by id, reworded bullets, the skills rows). This
script does the mechanical, deterministic part: it copies the preamble + heading
+ Education verbatim from ``assets/master_resume.tex``, then emits the chosen
experiences and projects (headings verbatim by ``@key``; bullets pulled
byte-identical by id, or emitted from the slot's ``text``), then rebuilds the
Technical Skills section from the slot rows.

Verbatim-by-id bullets are honesty-safe by construction. Errors (unknown key,
out-of-range id, >5 skill rows, a project stack with >3 items, or a `text`
reword padded materially longer than its source bullet) abort with a clear
message and a nonzero exit.

Usage:
    python3 assemble_resume.py <company> [--force]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import tex_util
from tex_util import Block, match_braces
from paths import DATASET, MASTER, OUTPUT, REPO_ROOT

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


class AssembleError(Exception):
    """Raised for any unrecoverable slot/master mismatch."""


def _reword_tokens(body: str) -> list[str]:
    """Lowercased word tokens of a bullet body, for length/overlap comparison."""
    s = tex_util.replace_href(body)
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


def _bullet_tex(spec: dict[str, Any], block: Block) -> str:
    """Render one bullet spec to a `\\resumeItem{...}` line body."""
    if "id" in spec:
        i = int(spec["id"])
        if not (1 <= i <= len(block.bullets)):
            raise AssembleError(
                f"{block.key}: bullet id {i} out of range (1..{len(block.bullets)})")
        body = block.bullets[i - 1].strip()
    elif "text" in spec:
        body = str(spec["text"]).strip()
        toks = _reword_tokens(body)
        ratio, master_len = _closest_master_bullet(toks, block)
        if ratio >= REWORD_MATCH_MIN and len(toks) - master_len > MAX_REWORD_EXTRA_WORDS:
            raise AssembleError(
                f"{block.key}: reworded bullet pads its source by "
                f"{len(toks) - master_len} words ({len(toks)} vs master {master_len}); "
                f"a reword may add at most {MAX_REWORD_EXTRA_WORDS}. Don't lengthen a "
                f"bullet to fill the page -- use the verbatim id, trim the reword, or "
                f"add a whole pool bullet/project instead.")
    else:
        raise AssembleError(f"{block.key}: each bullet needs an 'id' or 'text' key")
    return f"        \\resumeItem{{{body}}}"


def _bullets_block(specs: list[dict[str, Any]], block: Block) -> str:
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


def _validate_stack(key: str, heading: str) -> None:
    """A project's tech-stack \\emph{} line may list at most MAX_PROJECT_STACK items."""
    inner = _emph_inner(heading)
    if inner is None:
        return
    items = [p.strip() for p in inner.split(",") if p.strip()]
    if len(items) > MAX_PROJECT_STACK:
        raise AssembleError(
            f"{key}: tech stack has {len(items)} items "
            f"({', '.join(items)}); keep the {MAX_PROJECT_STACK} most JD-relevant "
            f"and set 'emph' in the slot accordingly.")


def _validate_experiences(exp_specs: list[dict[str, Any]], blocks: dict[str, Block]) -> None:
    """Enforce the hard invariant: every master experience is kept, in master order.

    ``blocks`` preserves master order, so the experience keys read out of it give
    the canonical sequence (IOE before FPT). A slot that drops one or flips the
    order would otherwise assemble a silently-wrong resume with no flag.
    """
    required = [k for k, blk in blocks.items() if blk.kind == "experience"]
    keys = [s.get("key") for s in exp_specs]
    missing = [k for k in required if k not in keys]
    if missing:
        raise AssembleError(
            f"experiences must keep all of {required} (missing {missing}); "
            f"both are always kept")
    ordered = [k for k in keys if k in required]
    if ordered != required:
        raise AssembleError(
            f"experiences must be in master order {required}, got {ordered}")


def _entry(spec: dict[str, Any], blocks: dict[str, Block], want_kind: str) -> str:
    key = spec.get("key")
    if key not in blocks:
        raise AssembleError(f"unknown {want_kind} key: {key!r}")
    block = blocks[key]
    if block.kind != want_kind:
        raise AssembleError(f"{key!r} is a {block.kind}, not a {want_kind}")
    heading = block.heading
    if want_kind == "project":
        if spec.get("emph"):
            heading = _splice_emph(heading, str(spec["emph"]))
        _validate_stack(key, heading)
    bullets = _bullets_block(list(spec.get("bullets", [])), block)
    return f"    {heading}\n{bullets}"


def _skills_section(rows: list[list[str]]) -> str:
    if len(rows) > MAX_SKILL_ROWS:
        raise AssembleError(f"{len(rows)} skill rows > max {MAX_SKILL_ROWS}")
    body = ["\\section{Technical Skills}",
            " \\begin{itemize}[leftmargin=0.15in, label={}]",
            "    \\small{\\item{"]
    for row in rows:
        if len(row) != 2:
            raise AssembleError(f"skill row must be [category, content]: {row!r}")
        cat, content = row
        body.append(f"     \\textbf{{{cat}}}{{: {content}}} \\\\")
    body += ["    }}", " \\end{itemize}"]
    return "\n".join(body)


def assemble(company: str, force: bool = False) -> Path:
    out_dir = OUTPUT / company
    slots_path = out_dir / "resume.slots.json"
    if not slots_path.exists():
        raise AssembleError(f"missing slot file: {slots_path}")

    baseline = DATASET / company / "resume.ai.tex"
    if baseline.exists() and not force:
        raise AssembleError(
            f"AI baseline already exists ({baseline.relative_to(REPO_ROOT)}); "
            f"refusing to clobber human edits. Re-run with --force to regenerate.")

    slots: dict[str, Any] = json.loads(slots_path.read_text(encoding="utf-8"))
    master = MASTER.read_text(encoding="utf-8")
    blocks = tex_util.parse_master(master)

    doc_start = master.index("\\documentclass")
    exp_marker = master.index("%-----------EXPERIENCE-----------")
    preamble = master[doc_start:exp_marker].rstrip() + "\n"

    exp_specs = list(slots.get("experiences", []))
    _validate_experiences(exp_specs, blocks)
    experiences = "\n\n".join(_entry(e, blocks, "experience") for e in exp_specs)
    projects = "\n\n".join(_entry(p, blocks, "project")
                           for p in slots.get("projects", []))
    skills = _skills_section([list(r) for r in slots.get("skills", [])])

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
    (out_dir / "resume.tex").write_text(resume_tex, encoding="utf-8")

    # Phase signal for Feature 1 (Stop-hook baseline) + watch.py.
    lock = out_dir / ".ai_phase.lock"
    if not lock.exists():
        lock.write_text(json.dumps({"company": company, "ts": time.time(),
                                    "force": force}), encoding="utf-8")
    return out_dir / "resume.tex"


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble resume.tex from a slot file.")
    ap.add_argument("company", help="company stem under output/")
    ap.add_argument("--force", action="store_true",
                    help="regenerate even if an AI baseline already exists")
    args = ap.parse_args()
    try:
        path = assemble(args.company, args.force)
    except (AssembleError, json.JSONDecodeError) as e:
        print(f"assemble_resume: {e}", file=sys.stderr)
        return 1
    print(f"assembled {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
