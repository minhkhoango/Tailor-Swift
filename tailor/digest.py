#!/usr/bin/env python3
"""Render the cached POOL digest from master_resume.tex.

``master_resume.tex`` stays the single source of truth; this builds a clean,
token-light view of it for the model -- each ``@key`` block with its heading and
its bullets numbered ``1..n`` exactly as the ``{"id": n}`` slot reference expects.
No preamble, no ``\\resumeItem`` noise. Derived at runtime via the shared
``tex_parse`` parser -- never hardcode block text (CONTEXT.md).

The digest is byte-stable across JDs, so it sits in the prompt-cached prefix; it
re-warms automatically only when the master changes.
"""

from __future__ import annotations

import re

from .core import tex_parse
from .core.paths import MASTER

_CTRL = re.compile(r"\\[A-Za-z]+\*?")
# A \section{Technical Skills} row: \textbf{Category}{: term, term, ...} \\
_SKILL_ROW = re.compile(r"\\textbf\{([^}]*)\}\{:\s*(.*?)\}\s*\\\\")


def _clean(raw: str) -> str:
    """LaTeX -> readable plain text for the digest (href shown-text kept)."""
    s = tex_parse.replace_href(raw)
    s = s.replace("{,}", "")                 # 4{,}000 -> 4000
    for a, b in (("\\%", "%"), ("\\$", "$"), ("\\&", "&"), ("\\#", "#"), ("~", " ")):
        s = s.replace(a, b)
    s = s.replace("$|$", "|")
    s = _CTRL.sub("", s)                       # drop remaining control sequences
    s = s.replace("{", "").replace("}", "").replace("$", "")
    return re.sub(r"\s+", " ", s).strip()


def _heading_summary(block: tex_parse.Block) -> str:
    """A one-line readable heading: title | subtitle | dates (best effort)."""
    args = [_clean(a) for a in block.heading_args if _clean(a)]
    return "  |  ".join(args)


def build_digest() -> str:
    """The full pool digest + keyword ledger, both derived from master_resume.tex.

    Each ``@key`` block renders as its readable heading plus the numbered bullets
    the ``{"id": n}`` slot reference expects. The ledger (ALLOWED / FORBIDDEN) is
    appended -- its core ALLOWED palette mirrored from the master's ``\\section{
    Technical Skills}`` rows, the rest sliced from the ``% KEYWORD LEDGER`` block.
    """
    master_tex = MASTER.read_text(encoding="utf-8")
    blocks = tex_parse.parse_master(master_tex)
    experiences = [b for b in blocks.values() if b.kind == "experience"]
    projects = [b for b in blocks.values() if b.kind == "project"]

    lines: list[str] = ["# POOL (master_resume.tex) — select @key blocks; bullets are 1-indexed"]
    for label, group in (("EXPERIENCES (both always kept, IOE then FPT)", experiences),
                         ("PROJECTS (pick ~3 that fill the page)", projects)):
        lines.append("")
        lines.append(f"## {label}")
        for blk in group:
            lines.append("")
            lines.append(f"@{blk.key}  [{blk.kind}]  {_heading_summary(blk)}")
            for i, bullet in enumerate(blk.bullets, start=1):
                lines.append(f"  {i}. {_clean(bullet)}")
    return "\n".join(lines) + "\n" + keyword_ledger(master_tex)


def _ledger_lines(master_tex: str) -> list[str]:
    """The ``% KEYWORD LEDGER`` comment body, leading ``% `` stripped, as text lines.

    Captures from the ``% KEYWORD LEDGER`` title line (exclusive) to the next
    ``%===`` banner. Returns [] if the master has no ledger block.
    """
    out: list[str] = []
    capturing = False
    for ln in master_tex.splitlines():
        if not capturing:
            # Match the title line exactly ("% KEYWORD LEDGER"), not a pointer
            # comment elsewhere that merely names the block.
            if re.match(r"^\s*%\s*KEYWORD LEDGER\s*$", ln):
                capturing = True
            continue
        if re.match(r"^\s*%=", ln):              # closing banner -> done
            break
        m = re.match(r"^\s*%\s?(.*)$", ln)
        if m is None:                             # non-comment -> done
            break
        out.append(m.group(1).rstrip())
    return out


def keyword_ledger(master_tex: str) -> str:
    """The ledger rendered for the prompt prefix: ALLOWED palette + FORBIDDEN guidance.

    The core ALLOWED palette is mirrored from the master's ``\\section{Technical
    Skills}`` rows (``\\textbf{Category}{: terms}``). The model never sees that LaTeX
    section, so this is its only copy -- and the master keeps ONE source of the
    vocabulary (no duplicate ledger lines). The mirrored palette is spliced in just
    before the remaining ``% KEYWORD LEDGER`` lines (Baseline / Hardware / Soft /
    FORBIDDEN), giving the model one merged ALLOWED/FORBIDDEN view.
    """
    palette: list[str] = []
    for m in _SKILL_ROW.finditer(master_tex):
        terms = re.sub(r"\s+", " ", m.group(2)).strip()
        palette.append(f"ALLOWED {m.group(1).strip()}: {terms}")
    body = _ledger_lines(master_tex)
    insert_at = next((i for i, ln in enumerate(body)
                      if ln.strip().startswith(("ALLOWED", "Soft", "FORBIDDEN"))),
                     len(body))
    merged = body[:insert_at] + palette + body[insert_at:]
    return ("# KEYWORD LEDGER (ALLOWED / FORBIDDEN — from master_resume.tex)\n"
            + "\n".join(merged) + "\n")


def forbidden_terms(master_tex: str) -> list[str]:
    """Flat list of FORBIDDEN tech terms from the ledger (advisory whole-word scan).

    Reads only the ``FORBIDDEN ... tech ...`` line so scale/buzzword guidance does
    not become whole-word advisory noise. Replaces the old keywords.md reader.
    """
    terms: list[str] = []
    for ln in _ledger_lines(master_tex):
        s = ln.strip()
        if not (s.upper().startswith("FORBIDDEN") and "tech" in s.lower()):
            continue
        body = s.split(":", 1)[1] if ":" in s else s
        for tok in re.split(r"[,.]", body):
            tok = tok.strip()
            if len(tok) >= 2:
                terms.append(tok)
    return terms
