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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Protocol, TypeVar

from .core.capture import capture_ai_baseline, is_frozen
from .core.chain import Report, run_chain
from .core.paths import JOBDESC, OUTPUT, RESUME_JOBNAME, SCRATCH, SLOTS_NAME
from .core.slots import Slots, to_data
from .llm import EmitResult, Why, from_model
from .log import RunLogger, new_logger

MAX_PASSES = 2

# Hard ceiling on JDs tailored at once. Work is I/O-bound (model HTTP + the
# pdflatex subprocess both release the GIL), so threads -- not processes -- give
# real concurrency. Each JD is independent: its own SlotSession, its own scratch
# dir, its own output/<stem>/ and dataset/<stem>/, so a 15-wide fan-out never
# shares mutable state. The one cross-thread resource, the run logger, is locked.
MAX_WORKERS = 15

_T = TypeVar("_T")
_R = TypeVar("_R")


def _pool_map(items: list[_T], work: Callable[[_T], _R]) -> list[_R]:
    """Run ``work(item)`` over ``items`` on up to ``MAX_WORKERS`` threads, returning
    results in the original input order (not completion order).

    ``work`` MUST NOT raise: each caller wraps its real work in a try/except that
    turns a single JD's blow-up into a logged failure result, so one bad JD never
    sinks the other fourteen in flight (the pool keeps draining). The worker count
    is capped at both ``MAX_WORKERS`` and ``len(items)`` so a 3-JD batch spawns 3
    threads, not 15.
    """
    if not items:
        return []
    results: dict[int, _R] = {}
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(items))) as pool:
        futures = {pool.submit(work, item): i for i, item in enumerate(items)}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return [results[i] for i in range(len(items))]

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


def _tailor_path(path: Path, llm: LLM, chain: Chain, log: RunLogger) -> Report:
    """Tailor one JD file, isolating any blow-up so the pool keeps draining.

    The thread worker for :func:`run`. A crash in one JD (network drop, a model
    error, a pdflatex failure that escapes the chain) is caught here, logged as a
    loud ``error`` event, and turned into a non-shippable ``ERROR`` ``Report`` --
    so it counts as a batch failure but never cancels the other in-flight JDs.
    """
    stem = path.stem
    try:
        return tailor_one(stem, path.read_text(encoding="utf-8"), llm, chain, log)
    except Exception as exc:  # noqa: BLE001 - isolate: one JD must not sink the batch
        log.event("error", stem=stem, error=f"{type(exc).__name__}: {exc}")
        return Report(stem, "ERROR", None, [], False, text=f"crashed: {exc}")


def run(jd_paths: list[Path], force: bool, llm: LLM | None = None,
        chain: Chain | None = None, log: RunLogger | None = None) -> list[Report]:
    """Tailor every JD in ``jd_paths`` (skipping ones already done unless ``force``).

    JDs run concurrently -- up to :data:`MAX_WORKERS` at once -- since each is an
    independent, I/O-bound chain. The skip-existing scan runs serially first (it is
    a cheap stat, no API), so only the JDs that actually need work are fanned out;
    the returned reports stay in ``jd_paths`` order regardless of finish order.

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
    todo: list[Path] = []
    for path in jd_paths:
        if not force and _already_done(path.stem):
            log.event("skip", stem=path.stem, reason="already-done")
        else:
            todo.append(path)

    failures = 0
    try:
        reports = _pool_map(todo, lambda p: _tailor_path(p, llm, chain, log))
        failures = sum(1 for r in reports if not r.shippable)
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


def _why_one(path: Path, force: bool, llm: LLM, chain: Chain,
             log: RunLogger) -> Path | None:
    """Tailor-if-missing then write one ``why_company.md`` (the thread worker for
    :func:`why`). Returns the written path, ``None`` if the why already existed
    (idempotent skip) or the stem crashed -- a blow-up is caught and logged so one
    bad company never sinks the rest of the fan-out.
    """
    stem = path.stem
    try:
        jd_text = path.read_text(encoding="utf-8")
        if force or not _already_done(stem):
            tailor_one(stem, jd_text, llm, chain, log)
        why_path = OUTPUT / stem / "why_company.md"
        if why_path.exists() and not force:
            log.event("skip", stem=stem, reason="why exists")
            return None
        blurb, usage = llm.why(stem, jd_text, _url_hint(stem))
        log.event("why_search", stem=stem, url_used=blurb.url_used,
                  facts=blurb.impressive_numbers + blurb.notable_specifics, **usage)
        written = _write_why(stem, blurb)
        log.event("why_write", stem=stem, path=str(written),
                  todo=blurb.why_company.startswith("[TODO"))
        return written
    except Exception as exc:  # noqa: BLE001 - isolate: one company must not sink the batch
        log.event("error", stem=stem, error=f"{type(exc).__name__}: {exc}")
        return None


def why(globs: list[str], force: bool, llm: LLM | None = None,
        chain: Chain | None = None, log: RunLogger | None = None) -> list[Path]:
    """Generate ``output/<stem>/why_company.md`` for each matched JD (idempotent).

    Per stem: tailor the resume first if it is missing, then generate the why
    blurb unless it already exists (``force`` overrides both gates). Matched JDs
    run concurrently, up to :data:`MAX_WORKERS` at once -- each stem is independent
    (its own session, scratch dir, and ``why_company.md``).
    """
    own_log = log is None
    log = log or new_logger("why")
    chain = chain or run_chain
    if llm is None:
        from .llm import LLMClient
        llm = LLMClient()

    try:
        results = _pool_map(match_jds(globs),
                            lambda p: _why_one(p, force, llm, chain, log))
        return [p for p in results if p is not None]
    finally:
        if own_log:
            log.close()
