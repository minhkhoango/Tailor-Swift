#!/usr/bin/env python3
"""Shared LaTeX parsing primitives for the /tailor scripts.

Single home for the tex parsing reused by the assembler, the save-hook honesty
check, and the fit checker -- so there is exactly one brace matcher, one comment
stripper, and one master-block parser. Pure stdlib.

Public surface:
    match_braces(s, i)        -> (inner, index_after_close)
    strip_tex_comments(tex)   -> tex with unescaped %-comments removed
    replace_href(raw)         -> \\href{url}{shown} collapsed to `shown`
    resume_items(tex)         -> [inner body of each \\resumeItem{...}], in order
    extract_skill_rows(tex)   -> [(category, content)] from Technical Skills
    numbers_in(text)          -> Counter of numeric literals (honesty rule 1)
    parse_master(master_tex)  -> {key: Block} keyed by `% @key:` comments
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


# --------------------------------------------------------------------------- #
# Brace / comment primitives
# --------------------------------------------------------------------------- #
def match_braces(s: str, open_index: int) -> tuple[str, int]:
    """Given s[open_index] == '{', return (inner_text, index_after_close).

    Counts brace depth, ignoring escaped \\{ and \\}.
    """
    assert s[open_index] == "{"
    depth = 0
    i = open_index
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":  # skip escaped next char (covers \{ \} \% \$ ...)
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[open_index + 1:i], i + 1
        i += 1
    return s[open_index + 1:], n  # unbalanced; return rest


def strip_tex_comments(tex: str) -> str:
    """Drop everything from an unescaped % to end of line, line by line."""
    out: list[str] = []
    for line in tex.splitlines():
        bs = 0
        cut: int | None = None
        for idx, ch in enumerate(line):
            if ch == "\\":
                bs += 1
                continue
            if ch == "%" and bs % 2 == 0:
                cut = idx
                break
            bs = 0
        out.append(line if cut is None else line[:cut])
    return "\n".join(out)


def replace_href(raw: str) -> str:
    """Replace \\href{url}{shown} with just `shown` (the rendered text)."""
    out = raw
    while True:
        m = re.search(r"\\href\s*\{", out)
        if not m:
            break
        url_open = m.end() - 1
        _, after_url = match_braces(out, url_open)
        j = after_url
        while j < len(out) and out[j].isspace():
            j += 1
        if j < len(out) and out[j] == "{":
            shown, after_shown = match_braces(out, j)
        else:
            shown, after_shown = "", after_url
        out = out[:m.start()] + shown + out[after_shown:]
    return out


# --------------------------------------------------------------------------- #
# Body extraction
# --------------------------------------------------------------------------- #
_RESUME_ITEM_RE = re.compile(r"\\resumeItem(?![A-Za-z])\s*\{")


def resume_items(tex: str) -> list[str]:
    """Return the brace-balanced body of each body \\resumeItem{...}, in order.

    Slices \\begin{document}..\\end{document} when present (drops \\newcommand
    defs), strips comments, then brace-matches each \\resumeItem occurrence.
    """
    begin = tex.find("\\begin{document}")
    end = tex.find("\\end{document}")
    body = tex[begin:end] if (begin != -1 and end != -1 and end > begin) else tex
    body = strip_tex_comments(body)

    items: list[str] = []
    pos = 0
    while True:
        m = _RESUME_ITEM_RE.search(body, pos)
        if not m:
            break
        brace_idx = m.end() - 1
        inner, after = match_braces(body, brace_idx)
        items.append(inner)
        pos = after
    return items


def extract_skill_rows(tex: str) -> list[tuple[str, str]]:
    """Return [(category, content)] pairs from the Technical Skills section.

    Parses each ``\\textbf{Category}{: content}`` pair (comments stripped). The
    leading ``: `` of the content is removed. Empty list if no skills section.
    """
    start = tex.find("\\section{Technical Skills}")
    if start == -1:
        return []
    rest = tex[start + len("\\section{Technical Skills}"):]
    nxt = rest.find("\\section{")
    end = rest.find("\\end{document}")
    cut = min(x for x in (nxt, end, len(rest)) if x != -1)
    block = strip_tex_comments(rest[:cut])

    rows: list[tuple[str, str]] = []
    pos = 0
    pat = re.compile(r"\\textbf\s*\{")
    while True:
        m = pat.search(block, pos)
        if not m:
            break
        cat, after = match_braces(block, m.end() - 1)
        j = after
        while j < len(block) and block[j].isspace():
            j += 1
        if j < len(block) and block[j] == "{":
            content, after = match_braces(block, j)
            content = content.lstrip()
            if content.startswith(":"):
                content = content[1:].lstrip()
            rows.append((cat.strip(), content.strip()))
        pos = after
    return rows


# --------------------------------------------------------------------------- #
# Numbers (honesty rule 1)
# --------------------------------------------------------------------------- #
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def numbers_in(text: str) -> Counter[str]:
    """Multiset of numeric literals in `text`, normalized for honest comparison.

    Strips comments, collapses ``4{,}000`` -> ``4000``, removes ``\\%``/``\\$``,
    and turns ``--`` ranges and ``/`` separators into breaks so ``1--14`` yields
    {1, 14} and ``10/10`` yields {10, 10}. Decimals are kept (``99.9``).
    """
    s = strip_tex_comments(text)
    s = s.replace("{,}", "")               # 4{,}000 -> 4000
    for tok in ("\\%", "\\$", "\\&", "\\#"):
        s = s.replace(tok, " ")
    s = s.replace("---", " ").replace("--", " ").replace("/", " ")
    return Counter(_NUM_RE.findall(s))


# --------------------------------------------------------------------------- #
# Master-block parser (keyed by `% @key:`)
# --------------------------------------------------------------------------- #
@dataclass
class Block:
    key: str
    kind: str                 # "experience" | "project"
    heading: str              # the \resumeSubheading / \resumeProjectHeading verbatim
    heading_args: list[str]   # brace-matched inner of each heading arg
    bullets: list[str]        # raw \resumeItem bodies, in master order (1-based to caller)


_KEY_RE = re.compile(r"^\s*%\s*@key:\s*(\S+)\s*$", re.MULTILINE)
_HEADING_CMDS = (("\\resumeSubheading", 4, "experience"),
                 ("\\resumeProjectHeading", 2, "project"))


def _extract_command(text: str, cmd: str, n_args: int) -> tuple[str, list[str]] | None:
    """Find `cmd` and brace-match its n_args groups -> (full_command, [args])."""
    m = re.compile(re.escape(cmd) + r"(?![A-Za-z])\s*\{").search(text)
    if not m:
        return None
    start = m.start()
    pos = m.end() - 1  # at first '{'
    args: list[str] = []
    after = pos
    for _ in range(n_args):
        if pos >= len(text) or text[pos] != "{":
            break
        inner, after = match_braces(text, pos)
        args.append(inner)
        j = after
        while j < len(text) and text[j].isspace():
            j += 1
        pos = j
    return text[start:after], args


def parse_master(master_tex: str) -> dict[str, Block]:
    """Parse master_resume.tex into {key: Block} using the `% @key:` contract.

    Each block spans from its ``% @key: <name>`` marker to the next such marker
    (or EOF) -- the marker itself is the block delimiter, so the master needs no
    per-block banner. Within that region we extract the single heading command and
    the ordered \\resumeItem bullets; the trailing Technical Skills / KEYWORD
    LEDGER frame carries neither heading nor bullets, so the final region bound is
    safe even though it runs to EOF.
    """
    keys = list(_KEY_RE.finditer(master_tex))
    blocks: dict[str, Block] = {}
    for idx, km in enumerate(keys):
        key = km.group(1)
        region_start = km.end()
        region_end = keys[idx + 1].start() if idx + 1 < len(keys) else len(master_tex)
        region = master_tex[region_start:region_end]

        clean = strip_tex_comments(region)
        heading = ""
        heading_args: list[str] = []
        kind = ""
        for cmd, n_args, k in _HEADING_CMDS:
            got = _extract_command(clean, cmd, n_args)
            if got:
                heading, heading_args = got
                kind = k
                break
        if not kind:
            continue

        blocks[key] = Block(key, kind, heading, heading_args, resume_items(clean))
    return blocks
