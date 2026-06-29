#!/usr/bin/env python3
"""The tailor orchestrator: a thin program over the deterministic core.

Replaces the Claude Code agent that used to drive /tailor. ``run()`` holds all
batch logic (glob, skip-existing, the per-JD capped fix-up loop, ship/abort); the
CLI and any future cron both call it -- no duplicated fan-out, no stdout parsing.
Tests call ``run()`` / ``tailor_one()`` with two injected seams -- a fake ``llm``
(a queue of canned ``Slots``/``Why``) and a fake ``chain`` (canned ``Report``s) --
so the control flow is tested without network or pdflatex.

The loop assembles/compiles each pass in an in-repo scratch dir
(``.tailor_cache/<stem>/``); only the final accepted pass lands in
``output/<stem>/``. Honesty is the hard gate: if it never clears within the cap,
nothing ships -- the JD aborts, the scratch dir is kept for post-mortem, and the
abort is logged loudly.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Protocol

from .core.capture import capture_ai_baseline, is_frozen
from .core.chain import Report, run_chain
from .core.paths import JOBDESC, OUTPUT, RESUME_JOBNAME, SCRATCH, SLOTS_NAME
from .core.slots import Slots, to_data
from .llm import EmitResult, Why, from_model
from .log import RunLogger, new_logger

MAX_PASSES = 2

# A chain is anything with run_chain's shape; tests pass a fake returning Reports.
# It receives a canonical (core) Slots -- the orchestrator converts pydantic once.
Chain = Callable[[str, Slots, Path], Report]


class Session(Protocol):
    def emit(self, user_text: str) -> EmitResult: ...


class LLM(Protocol):
    def session(self) -> Session: ...
    def why(self, stem: str, jd_text: str, url_hint: str) -> tuple[Why, dict[str, int]]: ...


# --------------------------------------------------------------------------- #
# Per-JD tailoring (the capped fix-up loop)
# --------------------------------------------------------------------------- #
def _log_pass(log: RunLogger, stem: str, n: int,
              emit: EmitResult, report: Report) -> None:
    """Log one pass: the prompt sent + response received (verbatim), then the token
    usage, fit verdict, and honesty result. ``llm_prompt``/``llm_response`` carry the
    full text; their console echo is a short char count so the terminal stays clean."""
    prompt_fields: dict[str, object] = {"chars": len(emit.prompt_sent),
                                        "text": emit.prompt_sent}
    if emit.system is not None:           # cached prefix: logged once, on pass 1
        prompt_fields["system"] = emit.system
    log.event("llm_prompt", stem=stem, **{"pass": n}, **prompt_fields)
    log.event("llm_response", stem=stem, **{"pass": n},
              chars=len(emit.response_received), text=emit.response_received)
    log.event("llm_call", stem=stem, **{"pass": n}, **emit.usage)
    log.event("fit", stem=stem, **{"pass": n}, fill=report.fill,
              verdict=report.verdict, flags=report.flags)
    log.event("honesty", stem=stem, **{"pass": n},
              flags=report.honesty_flags or "clean")


def tailor_one(stem: str, jd_text: str, llm: LLM, chain: Chain, log: RunLogger,
               max_passes: int = MAX_PASSES) -> Report:
    """Tailor one JD: emit slots -> chain -> react, up to ``max_passes``; ship or abort.

    Returns the final ``Report`` (with ``passes``/``uncovered`` filled). Ships the
    final accepted slots+PDF to ``output/<stem>/`` and snapshots the AI baseline
    only when the result is honest; otherwise aborts and keeps the scratch dir.
    """
    log.event("jd_start", stem=stem)
    scratch = SCRATCH / stem
    shutil.rmtree(scratch, ignore_errors=True)
    session = llm.session()

    emit = session.emit(jd_text)
    core = from_model(emit.slots)
    report = chain(stem, core, scratch)
    passes = 1
    _log_pass(log, stem, passes, emit, report)

    while not report.ok and passes < max_passes:
        emit = session.emit(report.text)
        core = from_model(emit.slots)
        report = chain(stem, core, scratch)
        passes += 1
        _log_pass(log, stem, passes, emit, report)

    report.passes = passes
    report.uncovered = list(core.uncovered)

    if report.shippable:
        _ship(stem, core, scratch, log)
        shutil.rmtree(scratch, ignore_errors=True)
    else:
        reason = ("honesty-unclean" if report.honesty_flags else report.verdict.lower())
        log.event("abort", stem=stem, reason=reason, flags=report.honesty_flags)

    log.event("jd_done", stem=stem, passes=passes, verdict=report.verdict,
              honesty="clean" if not report.honesty_flags else "FLAGS",
              uncovered=report.uncovered or "none")
    return report


def _ship(stem: str, slots: Slots, scratch: Path, log: RunLogger) -> None:
    """Copy the final accepted artifacts to output/, then snapshot the AI baseline."""
    out_dir = OUTPUT / stem
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in (SLOTS_NAME, "resume.tex", f"{RESUME_JOBNAME}.pdf"):
        src = scratch / name
        if src.exists():
            shutil.copy2(src, out_dir / name)
    if is_frozen(stem):
        log.event("skip", stem=stem, reason="frozen (dataset baseline kept)")
    else:
        capture_ai_baseline(stem, to_data(slots))


# --------------------------------------------------------------------------- #
# Batch
# --------------------------------------------------------------------------- #
def discover_jds() -> list[Path]:
    """Every ``jobDescription/*.txt`` (sorted)."""
    return sorted(JOBDESC.glob("*.txt")) if JOBDESC.is_dir() else []


def _already_done(stem: str) -> bool:
    return (OUTPUT / stem / SLOTS_NAME).exists()


def run(jd_paths: list[Path], force: bool, llm: LLM | None = None,
        chain: Chain | None = None, log: RunLogger | None = None) -> list[Report]:
    """Tailor every JD in ``jd_paths`` (skipping ones already done unless ``force``).

    The real ``llm`` is constructed lazily only when not injected, so the fast test
    suite -- which always injects a fake -- never touches the metered API.
    """
    own_log = log is None
    log = log or new_logger()
    chain = chain or run_chain
    if llm is None:
        from .llm import LLMClient
        llm = LLMClient()

    log.event("run_start", argv=[p.name for p in jd_paths], jd_count=len(jd_paths))
    reports: list[Report] = []
    failures = 0
    try:
        for path in jd_paths:
            stem = path.stem
            if not force and _already_done(stem):
                log.event("skip", stem=stem, reason="already-done")
                continue
            report = tailor_one(stem, path.read_text(encoding="utf-8"), llm, chain, log)
            reports.append(report)
            if not report.shippable:
                failures += 1
    finally:
        log.event("run_done", jd_count=len(jd_paths), failures=failures)
        if own_log:
            log.close()
    return reports


# --------------------------------------------------------------------------- #
# Why-company (apply-time, idempotent)
# --------------------------------------------------------------------------- #
def _url_hint(stem: str) -> str:
    company = stem.split("_")[0]
    return f"https://www.{company.lower()}.com"


def _write_why(stem: str, why: Why) -> Path:
    out = OUTPUT / stem / "why_company.md"
    facts = "\n".join(f"%   - {f}" for f in (why.impressive_numbers + why.notable_specifics))
    header = (f"<!-- why_company for {stem}\n"
              f"     url_used: {why.url_used}\n"
              f"     facts:\n{facts or '%   (none found)'}\n-->\n\n")
    out.write_text(header + why.why_company + "\n", encoding="utf-8")
    return out


def match_jds(globs: list[str]) -> list[Path]:
    """Resolve why-company globs against ``jobDescription/`` (one entry per stem)."""
    found: dict[str, Path] = {}
    for g in globs:
        pats = [g] if g.endswith(".txt") else [g + ".txt", g + "*.txt"]
        for pat in pats:
            for p in sorted(JOBDESC.glob(pat)):
                found[p.stem] = p
    return list(found.values())


def why(globs: list[str], force: bool, llm: LLM | None = None,
        chain: Chain | None = None, log: RunLogger | None = None) -> list[Path]:
    """Generate ``output/<stem>/why_company.md`` for each matched JD (idempotent).

    Per stem: tailor the resume first if it is missing, then generate the why
    blurb unless it already exists (``force`` overrides both gates).
    """
    own_log = log is None
    log = log or new_logger("why")
    chain = chain or run_chain
    if llm is None:
        from .llm import LLMClient
        llm = LLMClient()

    written: list[Path] = []
    try:
        for path in match_jds(globs):
            stem = path.stem
            jd_text = path.read_text(encoding="utf-8")
            if force or not _already_done(stem):
                tailor_one(stem, jd_text, llm, chain, log)
            why_path = OUTPUT / stem / "why_company.md"
            if why_path.exists() and not force:
                log.event("skip", stem=stem, reason="why exists")
                continue
            blurb, usage = llm.why(stem, jd_text, _url_hint(stem))
            log.event("why_search", stem=stem, url_used=blurb.url_used,
                      facts=blurb.impressive_numbers + blurb.notable_specifics, **usage)
            written.append(_write_why(stem, blurb))
            log.event("why_write", stem=stem, path=str(written[-1]),
                      todo=blurb.why_company.startswith("[TODO"))
    finally:
        if own_log:
            log.close()
    return written
