#!/usr/bin/env python3
"""Anthropic client + the model's whole contract: schemas, system prompt, calls.

This is the only module that talks to the model. It owns:

  * the structured-output schemas the model must return (:class:`Slots`,
    :class:`Why`) -- machine-enforced via ``messages.parse`` so a malformed slot
    is impossible (the model retries on mismatch),
  * :data:`SYSTEM_PROMPT` -- the brain lifted from the old SKILL.md (golden rules,
    slot schema, the fit/honesty reaction table, what a JD keyword is). It is a
    plain string (the schema example has ``{}`` braces, so NOT an f-string),
  * the cached prefix (system prompt + pool digest + honesty-rules + keywords),
    byte-stable across JDs so it prompt-caches (verify ``cache_read > 0``),
  * the stateful multi-turn tailor loop (:class:`SlotSession`) and the one
    web-search :meth:`LLMClient.why` call.

The honesty rules have one home (``references/honesty-rules.md``); the prompt
carries it at runtime -- no third copy here.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from .core.paths import HONESTY_RULES, KEYWORDS
from .digest import build_digest

MODEL = "claude-opus-4-8"               # project memory: /tailor runs Opus 4.8
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search"}


# --------------------------------------------------------------------------- #
# Structured-output schemas (the model's enforced contract)
# --------------------------------------------------------------------------- #
class IdBullet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int


class TextBullet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


Bullet = IdBullet | TextBullet


class SlotBlock(BaseModel):
    """One chosen experience or project: master ``key`` + bullet picks.

    ``emph`` (projects only) overrides the heading tech-stack; the assembler caps
    it at 3 techs.
    """
    model_config = ConfigDict(extra="forbid")
    key: str
    bullets: list[Bullet]
    emph: str | None = None


class SkillRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str
    content: str


class Slots(BaseModel):
    """The full slot deliverable. Mirrors the assembler's slot-file schema, plus
    ``uncovered`` (the must-haves with no honest home -- surfaced, never papered)."""
    model_config = ConfigDict(extra="forbid")
    company: str
    experiences: list[SlotBlock]       # ioe then fpt (assembler re-orders anyway)
    projects: list[SlotBlock]
    skills: list[SkillRow]             # up to 5 rows
    uncovered: list[str] = []


class Why(BaseModel):
    """The why-company structured output (pasted into an application's 'why us' box)."""
    model_config = ConfigDict(extra="forbid")
    company: str
    url_used: str
    impressive_numbers: list[str]      # each must carry a verifiable number
    notable_specifics: list[str]
    why_company: str                   # the 2-3 sentence paragraph (or TODO placeholder)


def slots_to_data(slots: Slots) -> dict[str, Any]:
    """Pydantic ``Slots`` -> the plain dict the deterministic core consumes.

    Bullet objects serialize to exactly ``{"id": n}`` or ``{"text": "..."}`` -- the
    closed-pool / verbatim contract the assembler validates. ``company`` and
    ``uncovered`` ride along; the assembler ignores them.
    """
    def block(b: SlotBlock) -> dict[str, Any]:
        d: dict[str, Any] = {"key": b.key, "bullets": [x.model_dump() for x in b.bullets]}
        if b.emph:
            d["emph"] = b.emph
        return d
    return {
        "company": slots.company,
        "experiences": [block(b) for b in slots.experiences],
        "projects": [block(b) for b in slots.projects],
        "skills": [[r.category, r.content] for r in slots.skills],
        "uncovered": list(slots.uncovered),
    }


# --------------------------------------------------------------------------- #
# The system prompt (brain, trimmed from SKILL.md). Plain string -- has {} braces.
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = """\
You tailor Khoa's master resume into a packed, honest, 1-page company-specific
resume by SELECTING from one closed pool and LIGHTLY rewording for the job's
keywords. Facts are locked; wording barely moves.

## Golden rules
1. SELECT, don't rewrite. Pick whole projects and keep their bullets faithful --
   swap in an exact JD keyword or lightly rephrase, nothing more. Never
   heavy-rewrite or shorten a bullet.
2. PACK THE PAGE. The output is strictly 1 page, filled to 0.95-1.0. Empty space
   at the bottom is the failure to avoid.
3. HONESTY IS ABSOLUTE. Every number/date/tech/company traces 1:1 to a SELECTED
   master block. The pool is closed -- never invent a project. When honesty and
   fullness conflict, honesty wins; when fullness and keyword-match conflict,
   fullness wins.

## What you return (structured output -- enforced)
A `Slots` object:
- `company`: the company stem.
- `experiences`: BOTH experiences, ioe then fpt (order is re-sorted by code anyway,
  but list them this way). Each block: `key` + `bullets`.
- `projects`: pick the ~3 projects that best fill the page for this JD.
- A bullet is EITHER `{"id": n}` -- pull master `\\resumeItem` #n verbatim (1-based,
  the numbering in the POOL digest) -- OR `{"text": "..."}` a light reword. Prefer
  ids: byte-identical bullets are honesty-safe. A `text` reword may add at most ~4
  words over its source; when unsure a fact survives, use the id.
- `emph` (projects only): the 3 most JD-relevant techs for that project's heading
  (hard cap 3). Omit to keep the master default.
- `skills`: up to 5 `{category, content}` rows rebuilt per JD. Pack each row full
  with JD-relevant ALLOWED keywords until the next term would wrap; never repeat a
  keyword across rows; never pull from FORBIDDEN.
- `uncovered`: JD must-haves no honest pool block can cover. List them -- this is
  what changes whether Khoa hits "submit". Never invent a project to cover one.

## What a JD keyword is (mirror honestly)
A term the JD signals (repetition is the signal) that is honest for Khoa: (a) a
tech term in keywords ALLOWED, (b) a universal baseline tool (Office, Git, Linux,
etc.), or (c) a domain term a real pool block supports, surfaced by reframing that
block's TRUE bullet. A frequently-repeated domain term the pool does NOT support is
an `uncovered` must-have, never a mirrored keyword.

## React to the fit + honesty report
After you return slots, code assembles -> compiles -> measures fit -> runs the
number-traceability honesty check, and returns one report as the next user turn.
React by returning a revised `Slots`:
- UNDERFULL (<0.95): add a whole JD-relevant project, or one more faithful pool
  bullet. Never pad a bullet (a reword >4 words past source is rejected). Once all
  bullets + both experiences + 5 skill rows are in and it is still under, that is
  acceptable -- return the same slots to accept.
- SPILLOVER / a FLAG bullet: its last wrapped line is short; lightly reword so it
  fills. Never cut a number fact.
- OVERFULL / MULTIPAGE: drop the lowest-JD-scoring project.
- WRAP on a skill row: prune its lowest-signal entries to one line.
- structure: WARN: the slot has a project count other than 3 -- add or drop one.
- honesty: FLAGS [...]: a number on the page does not trace to a selected master
  block. Fix it (you likely reworded in a stray number, or selected the wrong
  block). honesty MUST end clean.
- ERROR: assemble/compile failed -- read the message and fix the offending slot.
- OK + honesty: clean: you are done; return the same slots.

The POOL digest, honesty rules, and keyword ledger follow.
"""


def system_blocks() -> list[dict[str, Any]]:
    """The cached prefix: prompt + digest + honesty-rules + keywords.

    Byte-stable across JDs -> prompt-cached. ``cache_control`` on the LAST block
    caches the whole system prefix (prefix match); it re-warms automatically when
    the master/rules/keywords change. The per-JD text goes in the user turn, never
    here, so it never invalidates the cache.
    """
    parts = [
        SYSTEM_PROMPT,
        build_digest(),
        "# HONESTY RULES (honesty-rules.md)\n" + HONESTY_RULES.read_text(encoding="utf-8"),
        "# KEYWORD LEDGER (keywords.md)\n" + KEYWORDS.read_text(encoding="utf-8"),
    ]
    blocks: list[dict[str, Any]] = [{"type": "text", "text": p} for p in parts]
    blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


# --------------------------------------------------------------------------- #
# Why-company prompts
# --------------------------------------------------------------------------- #
WHY_SYSTEM = """\
You research a company and write a short, honest "why this company" blurb in
Khoa's voice -- the kind pasted into an application's "why us" box.

Use the web_search tool to find IMPRESSIVE CONCRETE FACTS: specificity PLUS a
verifiable number ("the 74,000+ businesses already on Stash", never "your
impressive customer base"). Then write a 2-3 sentence paragraph naming >=1 fact by
its ACTUAL value and tying it to a relevant Khoa highlight.

NEVER fabricate. If the web turns up nothing usable, set why_company to exactly
"[TODO: Khoa - why this company]" and leave the fact lists empty.

End your reply with ONLY a JSON object (no prose, no code fence) of this shape:
{"company": "...", "url_used": "...", "impressive_numbers": ["..."],
 "notable_specifics": ["..."], "why_company": "..."}
"""

WHY_USER = """\
Company stem: {stem}
Likely site: {url_hint}

Job description (for context on what Khoa is applying to):
{jd}

Research this company and return the JSON object.
"""


def _usage(usage: Any) -> dict[str, int]:
    return {
        "in_tok": int(getattr(usage, "input_tokens", 0) or 0),
        "out_tok": int(getattr(usage, "output_tokens", 0) or 0),
        "cache_read_tok": int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        "cache_creation_tok": int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
    }


def _final_text(resp: Any) -> str:
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def _parse_why(text: str, stem: str, url_hint: str) -> Why:
    """Tolerantly pull the JSON object out of the model's final text -> Why.

    On any failure, returns a TODO placeholder so the orchestrator flags it rather
    than shipping a fabricated blurb.
    """
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return Why.model_validate_json(m.group(0))
        except Exception:  # noqa: BLE001 - any malformed payload -> TODO placeholder
            pass
    return Why(company=stem, url_used=url_hint, impressive_numbers=[],
               notable_specifics=[], why_company="[TODO: Khoa - why this company]")


# --------------------------------------------------------------------------- #
# Client + session
# --------------------------------------------------------------------------- #
class SlotSession:
    """One stateful slot conversation for a single JD (the cap-3 fix-up loop).

    The stable prefix stays cached every turn; the model keeps its own reasoning
    continuity (its prior turns, incl. thinking blocks, are echoed back unchanged).
    """

    def __init__(self, client: Any, system: list[dict[str, Any]]) -> None:
        self._client = client
        self._system = system
        self._messages: list[dict[str, Any]] = []

    def emit(self, user_text: str) -> tuple[Slots, dict[str, int]]:
        """Append a user turn (the JD, or a report), return the model's revised Slots."""
        self._messages.append({"role": "user", "content": user_text})
        resp = self._client.messages.parse(
            model=MODEL,
            max_tokens=8000,
            system=self._system,
            thinking={"type": "adaptive"},
            messages=self._messages,
            output_format=Slots,
        )
        self._messages.append({"role": "assistant", "content": resp.content})
        return resp.parsed_output, _usage(resp.usage)


class LLMClient:
    """Wraps the Anthropic SDK + the cached prefix. One per run; reused across JDs."""

    def __init__(self) -> None:
        import anthropic  # imported lazily so the fast test suite never constructs it
        # Typed Any to match SlotSession: the SDK's server-tool / message TypedDicts
        # don't cover web_search_20260209, and the loop already reads usage/content
        # defensively via getattr -- so a plain-dict call site is the pragmatic shape.
        self._client: Any = anthropic.Anthropic()
        self._system = system_blocks()

    def session(self) -> SlotSession:
        return SlotSession(self._client, self._system)

    def why(self, stem: str, jd_text: str, url_hint: str) -> tuple[Why, dict[str, int]]:
        """One web-search call (the model searches iteratively inside it) -> Why."""
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": WHY_USER.format(stem=stem, url_hint=url_hint, jd=jd_text)}
        ]
        total = {"in_tok": 0, "out_tok": 0, "cache_read_tok": 0, "cache_creation_tok": 0}
        resp: Any = None
        for _ in range(6):  # web_search may pause_turn; resume until it finishes
            resp = self._client.messages.create(
                model=MODEL,
                max_tokens=4000,
                system=WHY_SYSTEM,
                thinking={"type": "adaptive"},
                tools=[WEB_SEARCH_TOOL],
                messages=messages,
            )
            for k, v in _usage(resp.usage).items():
                total[k] += v
            if resp.stop_reason != "pause_turn":
                break
            messages.append({"role": "assistant", "content": resp.content})
        return _parse_why(_final_text(resp), stem, url_hint), total
