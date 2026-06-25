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
    """The full pool digest: every experience then project, bullets numbered 1..n."""
    blocks = tex_parse.parse_master(MASTER.read_text(encoding="utf-8"))
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
    return "\n".join(lines) + "\n"
