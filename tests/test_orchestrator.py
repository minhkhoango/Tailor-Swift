#!/usr/bin/env python3
# pyright: reportPrivateUsage=false, reportMissingParameterType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownLambdaType=false, reportAttributeAccessIssue=false
"""Tier-1 fast tests: the orchestrator's control flow, hermetic and pure.

No network, no LaTeX. Two injected seams exercise ``run()``/``tailor_one()``/``why()``
in isolation: a programmable ``FakeLLM`` (a queue of canned ``Slots``/``Why``) and a
``FakeChain`` (a queue of canned ``Report``s that also writes the scratch artifacts a
real chain would, so the ship path is real). The metered-API guard in the root
``conftest.py`` ensures none of this can touch Anthropic.

The keystone is :func:`test_aborts_and_keeps_scratch_when_honesty_never_clears`:
honesty is the absolute gate, so a resume that never clears it must NOT ship.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import tailor
from tailor import run, tailor_one, why
from tailor.core import capture
from tailor.core.slots import Slots as CoreSlots, pretty_slots_json, to_data
from tailor.core.chain import Report
from tailor.llm import EmitResult, Slots, Why
from tailor.log import RunLogger


# --------------------------------------------------------------------------- #
# Fakes + helpers
# --------------------------------------------------------------------------- #
_USAGE = {"in_tok": 1, "out_tok": 2, "cache_read_tok": 0, "cache_creation_tok": 0}


def make_slots(company: str = "acme", uncovered: list[str] | None = None) -> Slots:
    return Slots(company=company, experiences=[], projects=[], skills=[],
                 uncovered=uncovered or [])


def make_report(stem: str = "acme", verdict: str = "OK",
                honesty: list[str] | None = None, fill: float | None = 0.97,
                text: str = "REPORT") -> Report:
    return Report(stem=stem, verdict=verdict, fill=fill, honesty_flags=honesty or [],
                  structure_warn=False, text=text)


class FakeSession:
    """A single JD conversation: pops the next canned Slots per emit().

    Returns a full :class:`EmitResult` (slots + verbatim I/O) like the real session,
    so the orchestrator's prompt/response logging is exercised by the fast suite too.
    """

    def __init__(self, slots_list: list[Slots]) -> None:
        self._q = list(slots_list)
        self.emits: list[str] = []
        self._first = True

    def emit(self, user_text: str) -> EmitResult:
        self.emits.append(user_text)
        slots = self._q.pop(0)
        system = "FAKE-SYSTEM-PREFIX" if self._first else None
        self._first = False
        return EmitResult(slots, dict(_USAGE), user_text,
                          slots.model_dump_json(), system)


class FakeLLM:
    """Hands out a fresh FakeSession per session() call; canned Why per why()."""

    def __init__(self, session_lists: list[list[Slots]], why_obj: Why | None = None) -> None:
        self._sessions = [FakeSession(s) for s in session_lists]
        self._idx = 0
        self.made: list[FakeSession] = []
        self._why_obj = why_obj
        self.why_calls: list[tuple[str, str, str]] = []

    def session(self) -> FakeSession:
        s = self._sessions[self._idx]
        self._idx += 1
        self.made.append(s)
        return s

    def why(self, stem: str, jd_text: str, url_hint: str) -> tuple[Why, dict[str, int]]:
        self.why_calls.append((stem, jd_text, url_hint))
        assert self._why_obj is not None
        return self._why_obj, dict(_USAGE)


class FakeChain:
    """Returns canned Reports; writes the scratch files a real chain would ship."""

    def __init__(self, reports: list[Report], write_files: bool = True) -> None:
        self._q = list(reports)
        self.calls: list[tuple[str, CoreSlots, Path]] = []
        self._write = write_files

    def __call__(self, stem: str, slots: CoreSlots, work_dir: Path) -> Report:
        self.calls.append((stem, slots, Path(work_dir)))
        wd = Path(work_dir)
        if self._write:
            wd.mkdir(parents=True, exist_ok=True)
            (wd / "resume.slots.json").write_text(
                pretty_slots_json(to_data(slots)), encoding="utf-8")
            (wd / "resume.tex").write_text("% tex", encoding="utf-8")
            (wd / "Khoa_Ngo_resume.pdf").write_bytes(b"%PDF fake")
        return self._q.pop(0)


def redirect_paths(monkeypatch: pytest.MonkeyPatch, tmp: Path
                   ) -> tuple[Path, Path, Path, Path]:
    """Point every repo-layout global the orchestrator touches at a temp tree."""
    out, scr, ds, jd = (tmp / "output", tmp / ".tailor_cache",
                        tmp / "dataset", tmp / "jobDescription")
    for d in (out, scr, ds, jd):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tailor, "OUTPUT", out)
    monkeypatch.setattr(tailor, "SCRATCH", scr)
    monkeypatch.setattr(tailor, "JOBDESC", jd)
    monkeypatch.setattr(capture, "DATASET", ds)
    monkeypatch.setattr(capture, "JOBDESC", jd)
    return out, scr, ds, jd


def read_events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# --------------------------------------------------------------------------- #
# The capped fix-up loop
# --------------------------------------------------------------------------- #
def test_loop_converges_then_ships(monkeypatch, tmp_path):
    out, scr, ds, _ = redirect_paths(monkeypatch, tmp_path)
    llm = FakeLLM([[make_slots(), make_slots(uncovered=["k8s"])]])
    chain = FakeChain([make_report(verdict="UNDERFULL"), make_report(verdict="OK")])
    log = RunLogger(tmp_path / "log.jsonl")

    report = tailor_one("acme", "JD TEXT", llm, chain, log)
    log.close()

    assert report.passes == 2
    assert report.ok
    assert report.uncovered == ["k8s"]
    # 2nd emit is fed the 1st pass's report text (the fix-up turn).
    assert llm.made[0].emits == ["JD TEXT", "REPORT"]
    # Final accepted artifacts shipped; AI baseline captured; scratch cleaned.
    assert (out / "acme" / "resume.slots.json").exists()
    assert (ds / "acme" / "resume.ai.slots.json").exists()
    assert not (scr / "acme").exists()


def test_cap3_accepts_underfull(monkeypatch, tmp_path):
    out, _, _, _ = redirect_paths(monkeypatch, tmp_path)
    llm = FakeLLM([[make_slots(), make_slots(), make_slots()]])
    chain = FakeChain([make_report(verdict="UNDERFULL")] * 3)
    log = RunLogger(tmp_path / "log.jsonl")

    report = tailor_one("acme", "JD", llm, chain, log)
    log.close()

    assert report.passes == tailor.MAX_PASSES   # hit the cap (never reached OK)
    assert not report.ok
    assert report.shippable            # UNDERFULL still ships
    assert (out / "acme" / "resume.slots.json").exists()


def test_aborts_and_keeps_scratch_when_honesty_never_clears(monkeypatch, tmp_path):
    """KEYSTONE: honesty is absolute -- never ship a dishonest resume."""
    out, scr, ds, _ = redirect_paths(monkeypatch, tmp_path)
    llm = FakeLLM([[make_slots(), make_slots(), make_slots()]])
    dirty = [make_report(verdict="OK", honesty=["numbers not traceable: 42"])] * 3
    chain = FakeChain(dirty)
    log_path = tmp_path / "log.jsonl"
    log = RunLogger(log_path)

    report = tailor_one("acme", "JD", llm, chain, log)
    log.close()

    assert report.passes == tailor.MAX_PASSES
    assert not report.shippable
    assert not (out / "acme").exists()          # nothing shipped
    assert not (ds / "acme").exists()           # no baseline snapshot
    assert (scr / "acme").exists()              # scratch KEPT for post-mortem
    aborts = [e for e in read_events(log_path) if e["event"] == "abort"]
    assert aborts and aborts[0]["reason"] == "honesty-unclean"


def test_compile_error_aborts(monkeypatch, tmp_path):
    out, scr, _, _ = redirect_paths(monkeypatch, tmp_path)
    llm = FakeLLM([[make_slots(), make_slots(), make_slots()]])
    chain = FakeChain([make_report(verdict="ERROR", fill=None, text="compile failed")] * 3)
    log_path = tmp_path / "log.jsonl"
    log = RunLogger(log_path)

    report = tailor_one("acme", "JD", llm, chain, log)
    log.close()

    assert not report.shippable
    assert not (out / "acme").exists()
    assert (scr / "acme").exists()
    aborts = [e for e in read_events(log_path) if e["event"] == "abort"]
    assert aborts and aborts[0]["reason"] == "error"


# --------------------------------------------------------------------------- #
# Batch run(): skip-existing
# --------------------------------------------------------------------------- #
def test_run_skips_already_done(monkeypatch, tmp_path):
    out, _, _, jd = redirect_paths(monkeypatch, tmp_path)
    (out / "Done").mkdir()
    (out / "Done" / "resume.slots.json").write_text("{}", encoding="utf-8")
    p_done = jd / "Done.txt"; p_done.write_text("jd1", encoding="utf-8")
    p_new = jd / "New.txt"; p_new.write_text("jd2", encoding="utf-8")

    llm = FakeLLM([[make_slots(company="New")]])
    chain = FakeChain([make_report(stem="New", verdict="OK")])
    log_path = tmp_path / "log.jsonl"
    log = RunLogger(log_path)

    reports = run([p_done, p_new], force=False, llm=llm, chain=chain, log=log)
    log.close()

    assert [r.stem for r in reports] == ["New"]
    events = read_events(log_path)
    assert any(e["event"] == "skip" and e.get("reason") == "already-done" for e in events)


def test_run_force_redoes_done(monkeypatch, tmp_path):
    out, _, _, jd = redirect_paths(monkeypatch, tmp_path)
    (out / "Done").mkdir()
    (out / "Done" / "resume.slots.json").write_text("{}", encoding="utf-8")
    p_done = jd / "Done.txt"; p_done.write_text("jd1", encoding="utf-8")

    llm = FakeLLM([[make_slots(company="Done")]])
    chain = FakeChain([make_report(stem="Done", verdict="OK")])
    log = RunLogger(tmp_path / "log.jsonl")

    reports = run([p_done], force=True, llm=llm, chain=chain, log=log)
    log.close()

    assert [r.stem for r in reports] == ["Done"]


# --------------------------------------------------------------------------- #
# Batch run(): concurrency, order, failure isolation
# --------------------------------------------------------------------------- #
class _ConcSession:
    """Records peak concurrency via a shared barrier, then ships canned OK slots.

    Every JD's emit() blocks on one barrier sized to the whole batch: it can only
    release when ALL JDs have reached emit at once, so the test deadlocks (and
    fails on the barrier timeout) unless the orchestrator truly ran them in
    parallel. The stem named ``Boom`` raises *after* the barrier, proving a single
    JD's blow-up is isolated without stalling the others.
    """

    def __init__(self, barrier: Any, peak: dict[str, int], lock: Any) -> None:
        self._barrier, self._peak, self._lock = barrier, peak, lock

    def emit(self, user_text: str) -> EmitResult:
        stem = user_text.split("-", 1)[1]
        with self._lock:
            self._peak["active"] += 1
            self._peak["max"] = max(self._peak["max"], self._peak["active"])
        self._barrier.wait(timeout=10)            # all JDs must arrive together
        with self._lock:
            self._peak["active"] -= 1
        if stem == "Boom":
            raise RuntimeError("kaboom")
        return EmitResult(make_slots(company=stem), dict(_USAGE), user_text,
                          "{}", "SYS")


class _ConcLLM:
    def __init__(self, barrier: Any, peak: dict[str, int], lock: Any) -> None:
        self._args = (barrier, peak, lock)

    def session(self) -> _ConcSession:
        return _ConcSession(*self._args)           # fresh per JD, like the real client

    def why(self, stem: str, jd_text: str, url_hint: str) -> tuple[Why, dict[str, int]]:
        raise AssertionError("run() must not call why()")


def _conc_chain(stem: str, slots: CoreSlots, work_dir: Path) -> Report:
    wd = Path(work_dir)
    wd.mkdir(parents=True, exist_ok=True)
    (wd / "resume.slots.json").write_text(pretty_slots_json(to_data(slots)), encoding="utf-8")
    (wd / "resume.tex").write_text("% tex", encoding="utf-8")
    (wd / "Khoa_Ngo_resume.pdf").write_bytes(b"%PDF fake")
    return make_report(stem=stem, verdict="OK")


def test_run_is_parallel_order_isolated(monkeypatch, tmp_path):
    """Five JDs run at once; order is preserved; the one crash is isolated."""
    import threading

    out, _, _, jd = redirect_paths(monkeypatch, tmp_path)
    names = ["A", "B", "Boom", "D", "E"]
    paths = [jd / f"{n}.txt" for n in names]
    for p, n in zip(paths, names):
        p.write_text(f"jd-{n}", encoding="utf-8")

    barrier = threading.Barrier(len(names))
    peak = {"active": 0, "max": 0}
    llm = _ConcLLM(barrier, peak, threading.Lock())
    log_path = tmp_path / "log.jsonl"
    log = RunLogger(log_path)

    reports = run(paths, force=True, llm=llm, chain=_conc_chain, log=log)
    log.close()

    assert [r.stem for r in reports] == names      # input order, not finish order
    assert peak["max"] == len(names)               # all five were in flight together
    boom = next(r for r in reports if r.stem == "Boom")
    assert not boom.shippable and boom.verdict == "ERROR"
    assert {r.stem for r in reports if r.shippable} == {"A", "B", "D", "E"}
    for n in ("A", "B", "D", "E"):                  # the survivors shipped
        assert (out / n / "resume.slots.json").exists()
    assert not (out / "Boom").exists()             # the crash shipped nothing
    errs = [e for e in read_events(log_path) if e["event"] == "error"]
    assert errs and errs[0]["stem"] == "Boom" and "RuntimeError" in errs[0]["error"]


def test_logger_thread_safe_lines_stay_whole(tmp_path):
    """Concurrent event() calls never interleave: every line is one valid JSON object."""
    import threading

    path = tmp_path / "t.jsonl"
    log = RunLogger(path)

    def hammer(i: int) -> None:
        for j in range(50):
            log.event("llm_call", stem=f"s{i}", **{"pass": j}, out_tok=i * 100 + j,
                      cache_read_tok=0)

    threads = [threading.Thread(target=hammer, args=(i,)) for i in range(15)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    log.close()

    recs = read_events(path)                        # json.loads each line -> raises if torn
    assert len(recs) == 15 * 50
    assert all(r["event"] == "llm_call" for r in recs)


# --------------------------------------------------------------------------- #
# CLI argv parse
# --------------------------------------------------------------------------- #
def _patch_cli(monkeypatch):
    from tailor import __main__ as m
    seen: dict[str, Any] = {}
    monkeypatch.setattr(m, "discover_jds", lambda: [Path("x.txt")])
    monkeypatch.setattr(m, "run",
                        lambda jds, force: seen.update(verb="run", jds=jds, force=force) or [])
    monkeypatch.setattr(m, "why",
                        lambda globs, force: seen.update(verb="why", globs=globs, force=force) or [])
    return m, seen


def test_cli_batch_default(monkeypatch):
    m, seen = _patch_cli(monkeypatch)
    assert m.main([]) == 0
    assert seen["verb"] == "run" and seen["force"] is False


def test_cli_batch_force_flag(monkeypatch):
    m, seen = _patch_cli(monkeypatch)
    assert m.main(["--force"]) == 0
    assert seen["verb"] == "run" and seen["force"] is True


def test_cli_why_globs(monkeypatch):
    m, seen = _patch_cli(monkeypatch)
    assert m.main(["why", "Apple*"]) == 0
    assert seen["verb"] == "why" and seen["globs"] == ["Apple*"] and seen["force"] is False


def test_cli_force_why_keyword(monkeypatch):
    m, seen = _patch_cli(monkeypatch)
    assert m.main(["force", "why", "A*", "B*"]) == 0
    assert seen["verb"] == "why" and seen["globs"] == ["A*", "B*"] and seen["force"] is True


def test_cli_why_needs_globs(monkeypatch):
    m, _ = _patch_cli(monkeypatch)
    assert m.main(["why"]) == 2


def test_cli_unrecognized(monkeypatch):
    m, _ = _patch_cli(monkeypatch)
    assert m.main(["bogus"]) == 2


# --------------------------------------------------------------------------- #
# why-company gates
# --------------------------------------------------------------------------- #
def _why_obj(todo: bool = False) -> Why:
    if todo:
        return Why(company="Acme", url_used="u", impressive_numbers=[],
                   notable_specifics=[], why_company="[TODO: Khoa - why this company]")
    return Why(company="Acme", url_used="https://acme.com",
               impressive_numbers=["74,000+ businesses"], notable_specifics=["YC S21"],
               why_company="Acme's 74,000+ businesses match my scale work.")


def test_why_skips_when_resume_and_why_exist(monkeypatch, tmp_path):
    out, _, _, jd = redirect_paths(monkeypatch, tmp_path)
    (jd / "Acme_SWE.txt").write_text("JD", encoding="utf-8")
    co = out / "Acme_SWE"; co.mkdir()
    (co / "resume.slots.json").write_text("{}", encoding="utf-8")
    (co / "why_company.md").write_text("existing", encoding="utf-8")

    llm = FakeLLM([], why_obj=_why_obj())
    log = RunLogger(tmp_path / "log.jsonl")
    written = why(["Acme_SWE"], force=False, llm=llm, chain=FakeChain([]), log=log)
    log.close()

    assert written == []
    assert llm.why_calls == []                       # no generation
    assert (co / "why_company.md").read_text(encoding="utf-8") == "existing"


def test_why_tailors_first_when_resume_missing(monkeypatch, tmp_path):
    out, _, _, jd = redirect_paths(monkeypatch, tmp_path)
    (jd / "Acme_SWE.txt").write_text("JD", encoding="utf-8")

    llm = FakeLLM([[make_slots(company="Acme_SWE")]], why_obj=_why_obj())
    chain = FakeChain([make_report(stem="Acme_SWE", verdict="OK")])
    log = RunLogger(tmp_path / "log.jsonl")
    written = why(["Acme_SWE"], force=False, llm=llm, chain=chain, log=log)
    log.close()

    assert llm.why_calls                              # why generated
    assert (out / "Acme_SWE" / "resume.slots.json").exists()   # tailored first
    assert written and written[0].name == "why_company.md"


def test_why_force_regenerates(monkeypatch, tmp_path):
    out, _, _, jd = redirect_paths(monkeypatch, tmp_path)
    (jd / "Acme_SWE.txt").write_text("JD", encoding="utf-8")
    co = out / "Acme_SWE"; co.mkdir()
    (co / "resume.slots.json").write_text("{}", encoding="utf-8")
    (co / "why_company.md").write_text("stale", encoding="utf-8")

    llm = FakeLLM([[make_slots(company="Acme_SWE")]], why_obj=_why_obj())
    chain = FakeChain([make_report(stem="Acme_SWE", verdict="OK")])
    log = RunLogger(tmp_path / "log.jsonl")
    written = why(["Acme_SWE"], force=True, llm=llm, chain=chain, log=log)
    log.close()

    assert llm.why_calls
    assert written and "Acme's 74,000+" in written[0].read_text(encoding="utf-8")


def test_why_todo_placeholder_when_facts_empty(monkeypatch, tmp_path):
    out, _, _, jd = redirect_paths(monkeypatch, tmp_path)
    (jd / "Acme_SWE.txt").write_text("JD", encoding="utf-8")
    co = out / "Acme_SWE"; co.mkdir()
    (co / "resume.slots.json").write_text("{}", encoding="utf-8")

    llm = FakeLLM([], why_obj=_why_obj(todo=True))
    log_path = tmp_path / "log.jsonl"
    log = RunLogger(log_path)
    written = why(["Acme_SWE"], force=False, llm=llm, chain=FakeChain([]), log=log)
    log.close()

    assert written and "[TODO" in written[0].read_text(encoding="utf-8")
    ww = [e for e in read_events(log_path) if e["event"] == "why_write"]
    assert ww and ww[0]["todo"] is True


# --------------------------------------------------------------------------- #
# digest builder
# --------------------------------------------------------------------------- #
def _digest_block(digest: str, key: str) -> list[str]:
    lines = digest.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith(f"@{key} "))
    section = [lines[start]]
    for ln in lines[start + 1:]:
        if ln.startswith("@"):
            break
        section.append(ln)
    return section


def test_digest_bullets_numbered_to_match_ids():
    import re as _re
    from tailor.digest import build_digest
    from _helpers import BLOCKS

    digest = build_digest()
    for key in ("ioe", "fpt", "local_lens"):
        section = _digest_block(digest, key)
        nums = [int(m.group(1)) for ln in section
                if (m := _re.match(r"\s+(\d+)\.\s", ln))]
        assert nums == list(range(1, len(BLOCKS[key].bullets) + 1)), key


def test_digest_has_clean_headings_no_latex():
    from tailor.digest import build_digest
    digest = build_digest()
    assert "EXPERIENCES" in digest and "PROJECTS" in digest
    assert "\\resumeItem" not in digest
    assert "{,}" not in digest                       # numbers de-LaTeX'd


# --------------------------------------------------------------------------- #
# JSONL logger
# --------------------------------------------------------------------------- #
def test_logger_one_json_object_per_line(tmp_path):
    path = tmp_path / "t.jsonl"
    log = RunLogger(path)
    log.event("run_start", argv=["a.txt"], jd_count=1)
    log.event("jd_done", stem="acme", passes=2, verdict="OK", honesty="clean",
              uncovered="none")
    log.event("run_done", jd_count=1, failures=0)
    log.close()

    recs = read_events(path)
    assert len(recs) == 3
    assert all("ts" in r and "event" in r for r in recs)
    jd_done = next(r for r in recs if r["event"] == "jd_done")
    assert jd_done["verdict"] == "OK" and jd_done["passes"] == 2
    run_done = next(r for r in recs if r["event"] == "run_done")
    assert run_done["failures"] == 0


# --------------------------------------------------------------------------- #
# Skill-category contract: only the four page categories are legal
# --------------------------------------------------------------------------- #
def test_skillrow_rejects_invented_categories():
    """The model's structured-output schema MACHINE-ENFORCES the four categories,
    so the whole class of invented domain buckets is impossible, not just frowned on."""
    from pydantic import ValidationError
    from tailor.llm import SkillRow

    for good in ("Languages", "Frameworks", "Developer Tools", "Libraries"):
        assert SkillRow(category=good, content="x").category == good
    for bad in ("Domain", "AI / ML", "Finance / Quant", "Software Engineering",
                "Hardware & Digital Logic", "Tools"):
        with pytest.raises(ValidationError):
            SkillRow(category=bad, content="x")  # type: ignore[arg-type]


def test_coerce_skill_category_normalizes_legacy_on_disk_rows():
    """Recorded slot files predating the enum still load: ``slots_from_data`` folds
    any legacy/invented category onto one of the four (label-only -- honesty is
    unaffected) instead of raising."""
    from tailor.core.slots import SlotsData
    from tailor.llm import coerce_skill_category, slots_from_data

    assert coerce_skill_category("developer tools") == "Developer Tools"
    assert coerce_skill_category("Programming Languages") == "Languages"
    assert coerce_skill_category("ML Libraries") == "Libraries"
    assert coerce_skill_category("Finance / Quant") == "Developer Tools"   # catch-all

    legacy: SlotsData = {
        "company": "acme", "experiences": [], "projects": [],
        "skills": [["Languages", "Python"], ["Finance / Quant", "Time Series"]],
        "uncovered": []}
    slots = slots_from_data(legacy)   # must not raise
    assert [r.category for r in slots.skills] == ["Languages", "Developer Tools"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
