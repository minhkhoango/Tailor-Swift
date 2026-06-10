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
out-of-range id, >5 skill rows) abort with a clear message and a nonzero exit.

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

REPO_ROOT = Path(__file__).resolve().parents[4]
SKILL_DIR = Path(__file__).resolve().parents[1]
MASTER = SKILL_DIR / "assets" / "master_resume.tex"
OUTPUT = REPO_ROOT / "output"
DATASET = REPO_ROOT / "dataset"

MAX_SKILL_ROWS = 5


class AssembleError(Exception):
    """Raised for any unrecoverable slot/master mismatch."""


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
    if want_kind == "project" and spec.get("emph"):
        heading = _splice_emph(heading, str(spec["emph"]))
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
