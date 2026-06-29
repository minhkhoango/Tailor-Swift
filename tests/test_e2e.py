#!/usr/bin/env python3
# pyright: reportPrivateUsage=false, reportUnusedImport=false
"""Tier-3 end-to-end: drive the WHOLE user flow, the way `python -m tailor` does.

Unlike the unit tiers (which test one function) this replays a recorded slot file
through the REAL orchestrator -- ``run() -> tailor_one() -> emit -> chain (assemble
-> pdflatex -> fit -> honesty) -> ship -> log`` -- into a throwaway repo, then
asserts on the shipped artifacts and the JSONL run log exactly as a user would see
them. The only seam is a :class:`ReplayLLM` that yields a fixture's recorded slots
in place of a live model call, so the run is deterministic and free; everything
downstream is the production code path.

Two kinds of run live here:

* ``test_replay_e2e_*`` (default, hermetic): every fixture subject that carries a
  ``job_description.txt`` is replayed and must ship a 1-page, honest PDF, with the
  full prompt/response logged. dataset/ is gitignored, so these inputs are the
  *tracked* snapshots under tests/fixtures/ (see scratchpad/gen_fixtures.py).
* ``test_live_smoke`` (``@pytest.mark.live``, hand-run): calls the REAL Anthropic
  API once. Self-skips without ``ANTHROPIC_API_KEY``; the network guard in the root
  conftest steps aside only for this marker.

Add ``--io`` to any run to dump each subject's full SENT / RECEIVED / FIT / HONESTY
/ SHIPPED blocks to the terminal.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, cast

import pytest

import _helpers  # noqa: F401  (puts the repo root on sys.path)
from _helpers import has_pdflatex, has_pdfplumber

import tailor
from tailor import run
from tailor.core import capture
from tailor.core.check_resume_fit import extract_pages
from tailor.core.paths import RESUME_JOBNAME
from tailor.core.slots import SlotsData
from tailor.llm import EmitResult, Slots, slots_from_data
from tailor.log import RunLogger

FIXTURES = Path(__file__).resolve().parent / "fixtures"
_USAGE = {"in_tok": 11, "out_tok": 22, "cache_read_tok": 0, "cache_creation_tok": 0}
_HAVE_PDF = has_pdflatex() and has_pdfplumber()


def e2e_subjects() -> list[tuple[str, Path]]:
    """Fixture dirs carrying BOTH a slot file and a JD -- the full-flow inputs."""
    if not FIXTURES.is_dir():
        return []
    return [(d.name, d) for d in sorted(FIXTURES.iterdir())
            if (d / "resume.slots.json").is_file() and (d / "job_description.txt").is_file()]


_E2E = e2e_subjects()


# --------------------------------------------------------------------------- #
# The replay seam: a recorded slot file standing in for one live model turn
# --------------------------------------------------------------------------- #
class ReplaySession:
    """Yields one recorded ``Slots`` as the model's output for every emit() turn.

    The recording is the slots that actually shipped, so its fit verdict is stable:
    re-emitting them on a react turn cannot improve it, and the orchestrator ships
    them once the pass cap is hit -- exactly the real accept-after-cap behavior.
    ``emit`` returns the same :class:`EmitResult` shape the real session does, so the
    prompt/response logging path is exercised verbatim (system prefix on turn 1).
    """

    def __init__(self, slots: Slots) -> None:
        self._slots = slots
        self._first = True

    def emit(self, user_text: str) -> EmitResult:
        system = ("REPLAY-SYSTEM-PREFIX (recorded slots; no live model called)"
                  if self._first else None)
        self._first = False
        return EmitResult(self._slots, dict(_USAGE), user_text,
                          self._slots.model_dump_json(indent=2), system)


class ReplayLLM:
    """Hands out a fresh ReplaySession per JD; ``why`` is not part of this e2e."""

    def __init__(self, slots: Slots) -> None:
        self._slots = slots

    def session(self) -> ReplaySession:
        return ReplaySession(self._slots)

    def why(self, stem: str, jd_text: str, url_hint: str) -> Any:
        raise AssertionError("why() is not exercised by the tailor replay e2e")


def _redirect_paths(monkeypatch: pytest.MonkeyPatch, tmp: Path) -> tuple[Path, Path]:
    """Point every repo-layout global the flow writes through at a temp tree.

    MASTER (the closed pool) is intentionally left real -- assembling against the
    actual master is part of what the e2e verifies.
    """
    out, scr, ds, jd = (tmp / "output", tmp / ".tailor_cache",
                        tmp / "dataset", tmp / "jobDescription")
    for d in (out, scr, ds, jd):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tailor, "OUTPUT", out)
    monkeypatch.setattr(tailor, "SCRATCH", scr)
    monkeypatch.setattr(tailor, "JOBDESC", jd)
    monkeypatch.setattr(capture, "DATASET", ds)
    monkeypatch.setattr(capture, "JOBDESC", jd)
    return out, jd


def _events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines()]


# --------------------------------------------------------------------------- #
# Hermetic replay e2e (one parametrized case per fixture-with-JD)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not _HAVE_PDF, reason="e2e needs pdflatex + pdfplumber")
@pytest.mark.parametrize("subject,sdir", _E2E, ids=[s for s, _ in _E2E])
def test_replay_e2e_ships_and_logs(subject: str, sdir: Path,
                                   monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                   io_report: Callable[..., None]) -> None:
    out, jd_dir = _redirect_paths(monkeypatch, tmp_path)
    slots_data = cast(SlotsData, json.loads(
        (sdir / "resume.slots.json").read_text(encoding="utf-8")))
    jd_text = (sdir / "job_description.txt").read_text(encoding="utf-8")
    jd_path = jd_dir / f"{subject}.txt"
    jd_path.write_text(jd_text, encoding="utf-8")

    slots = slots_from_data(slots_data)
    log_path = tmp_path / "log.jsonl"
    log = RunLogger(log_path)
    reports = run([jd_path], force=True, llm=ReplayLLM(slots), log=log)
    log.close()

    assert len(reports) == 1
    report = reports[0]

    # 1) The real user artifacts shipped to output/<stem>/.
    shipped = out / subject
    pdf = shipped / f"{RESUME_JOBNAME}.pdf"
    assert (shipped / "resume.slots.json").exists(), "slots must ship"
    assert (shipped / "resume.tex").exists(), "tex must ship"
    assert pdf.exists(), "PDF must ship"
    assert report.shippable and report.honesty_flags == []
    assert len(extract_pages(pdf)) == 1, "a tailored resume is exactly one page"

    # 2) The run log carries the full LLM I/O + the deterministic pipeline trace.
    events = _events(log_path)
    kinds = {e["event"] for e in events}
    for needed in ("jd_start", "llm_prompt", "llm_response", "llm_call",
                   "fit", "honesty", "jd_done"):
        assert needed in kinds, f"run log missing {needed!r} event"
    prompt_ev = next(e for e in events if e["event"] == "llm_prompt")
    assert prompt_ev["text"] == jd_text, "the JD we sent is logged verbatim"
    assert "system" in prompt_ev, "the cached system prefix is logged once (pass 1)"
    resp_ev = next(e for e in events if e["event"] == "llm_response")
    assert resp_ev["text"] == slots.model_dump_json(indent=2), "the slots reply is logged"

    io_report(
        subject,
        SENT=jd_text,
        RECEIVED=resp_ev["text"],
        FIT=report.text,
        HONESTY=report.honesty_flags or "clean",
        VERDICT=f"{report.verdict}  passes={report.passes}  shippable={report.shippable}",
        SHIPPED=str(pdf),
    )


# --------------------------------------------------------------------------- #
# Live smoke: the real model, hand-run (`pytest -m live`, key required)
# --------------------------------------------------------------------------- #
@pytest.mark.live
def test_live_smoke_real_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                             io_report: Callable[..., None]) -> None:
    """One real Anthropic call through the whole flow -- the truest user simulation.

    Hand-run only: ``ANTHROPIC_API_KEY=… pytest -m live --io``. Self-skips otherwise.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("set ANTHROPIC_API_KEY to run the live smoke")
    if not _HAVE_PDF:
        pytest.skip("live smoke needs pdflatex + pdfplumber")
    if not _E2E:
        pytest.skip("no fixture with a job_description.txt to drive the live run")

    subject, sdir = _E2E[0]
    out, jd_dir = _redirect_paths(monkeypatch, tmp_path)
    jd_text = (sdir / "job_description.txt").read_text(encoding="utf-8")
    jd_path = jd_dir / f"{subject}.txt"
    jd_path.write_text(jd_text, encoding="utf-8")

    log_path = tmp_path / "log.jsonl"
    log = RunLogger(log_path)
    reports = run([jd_path], force=True, log=log)   # llm=None -> the REAL LLMClient
    log.close()

    assert reports and reports[0].shippable, "the live run must ship something"
    events = _events(log_path)
    resp = next((e for e in events if e["event"] == "llm_response"), {"text": "(none)"})
    io_report(
        f"LIVE {subject}",
        SENT=jd_text,
        RECEIVED=resp["text"],
        FIT=reports[0].text,
        HONESTY=reports[0].honesty_flags or "clean",
        SHIPPED=str(out / subject / f"{RESUME_JOBNAME}.pdf"),
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "--io"]))
