#!/usr/bin/env python3
"""Benchmark: the deterministic /tailor checks vs. an LLM "eyeballing" them.

WHY THIS EXISTS
---------------
Two stages of the /tailor chain -- the 1-page **fit check** (does the resume fill
95-100% of the page without spilling?) and the **honesty lint** (does every number
in the output trace back to the master?) -- could in principle be done by asking an
LLM to look at the rendered PDF / read the two .tex files and judge. We chose to do
them deterministically in Python instead. This script measures what that choice buys:

    * tokens   -- deterministic stages spend 0 LLM *inference* tokens: Python (pdfplumber
                  word-boxes / number tracing), not a model, computes the verdict. Claude
                  then READS a compact pre-computed report back through the PostToolUse
                  hook -- measured here at ~528 tok (fit) / ~20 tok (honesty). The LLM
                  counterfactual instead ingests the raw page image / both .tex files AND
                  reasons over them: thousands of tokens per check, every save. So the
                  honest comparison is "read a finished answer" vs "eyeball raw input and
                  reason" -- NOT 0 vs thousands.
    * latency  -- deterministic stages finish in milliseconds; an LLM round-trip is
                  seconds.
    * accuracy -- the deterministic stages return the SAME verdict every run; the LLM
                  eyeball disagreed with ground truth on every trial (below).

METHOD (hybrid, see README)
---------------------------
* Deterministic side  -- measured live here: render the page, time
  ``check_resume_fit.py`` and ``lint_honesty.lint_resume`` on the sample company,
  read their exact verdicts (the ground truth).
* LLM token cost      -- ESTIMATED analytically (no API key needed): the rendered
  page costs ``(w*h)/750`` image tokens after the 1568px long-edge cap (the Haiku
  4.5 / pre-4.7 vision rule), plus prompt+output; the honesty review costs the two
  .tex files at ~3.5 chars/token, plus prompt+output. ``count_tokens`` would refine
  these; the order of magnitude is the point.
* LLM accuracy/latency -- gathered out-of-band by spawning **Opus 4.8** subagents via
  the Claude Code Agent tool (Opus 4.8 is the model that actually drives /tailor, so it
  is the right counterfactual), each asked to do the same check by eye / by reading.
  Their raw answers + wall-clock are recorded in ``OPUS_*`` below with the date they ran.
  Re-running the subagents is a manual step (they cost tokens and are nondeterministic),
  so they are constants here, not a live call. Haiku 4.5 was also sampled (cheaper, no
  better) and is summarized in ``HAIKU_NOTE`` for reference.

Run:  .venv/bin/python bench/det_vs_llm.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / ".claude" / "skills" / "tailor" / "scripts"
SRC = REPO / "src"
VENV_PY = REPO / ".venv" / "bin" / "python"
SAMPLE_COMPANY = "Nuro_SWE"
SAMPLE_DIR = REPO / "output" / SAMPLE_COMPANY
SAMPLE_PDF = SAMPLE_DIR / "Khoa_Ngo_resume.pdf"
SAMPLE_TEX = SAMPLE_DIR / "resume.tex"
SAMPLE_SLOTS = SAMPLE_DIR / "resume.slots.json"
SAMPLE_FIXTURE = REPO / "bench" / "sample.slots.json"  # committed; output/ is gitignored
PAGE_PNG = REPO / "bench" / "nuro_page-1.png"
RESUME_JOBNAME = "Khoa_Ngo_resume"

for _p in (str(SCRIPTS), str(SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# --- Token-estimate constants ------------------------------------------------ #
IMAGE_TOKENS_DIVISOR = 750.0      # Anthropic vision: tokens ~= (w_px * h_px) / 750
VISION_LONG_EDGE_CAP = 1568       # Haiku 4.5 / pre-4.7 long-edge downscale cap (px)
CHARS_PER_TOKEN = 3.5             # rough English+LaTeX text ratio (count_tokens refines)
FIT_PROMPT_TOKENS = 250           # instruction prompt for the "eyeball the page" ask
FIT_OUTPUT_TOKENS = 150           # the model's short answer
HONESTY_PROMPT_TOKENS = 320       # instruction prompt for the "trace the numbers" ask
HONESTY_OUTPUT_TOKENS = 220
LLM_MODEL = "claude-opus-4-8"     # the model that actually drives /tailor
RUN_TIMESTAMP = "2026-06-22"      # when the subagent trials below were run
FULLNESS_BALLPARK = 0.05          # |est - truth| <= this counts as a "ballpark" fullness hit

# --- Exact subagent prompts (for reproducibility) ---------------------------- #
# To refresh OPUS_*_TRIALS: spawn a Claude Code Agent (model=opus, claude-opus-4-8)
# per trial with one of these prompts + the named artifact attached, record its
# answer and wall-clock, and paste the tuples below. They are constants (not a live
# call) because each costs real tokens and is nondeterministic. See REPORT.md.
FIT_SUBAGENT_PROMPT = (
    "Here is a rendered one-page resume (PNG). Judge its page fit WITHOUT running any "
    "tool or code -- by eye only. Report two numbers: (1) fullness = fraction of the "
    "printable height the content fills, 0.00-1.00; (2) orphans = count of bullets whose "
    "last wrapped line has <= 4 words. Answer as 'fullness=X orphans=N'."
)
HONESTY_SUBAGENT_PROMPT = (
    "Here are two LaTeX files: the master resume pool and one tailored output resume. "
    "WITHOUT running any tool or code, read both and list every numeric literal in the "
    "OUTPUT bullets that does NOT trace back to a number in the master's selected "
    "experience/project blocks. Answer as a set of the untraceable numbers."
)

# --- Opus 4.8 subagent trials (Claude Code Agent tool, model=opus) ----------- #
# Ground truth (deterministic) for the FIT check on the sample: fullness=0.95,
# orphans=0. The deterministic checker hits both exactly on 100% of runs.
@dataclass(frozen=True)
class FitTrial:
    fullness: float
    orphans: int
    duration_ms: float


@dataclass(frozen=True)
class HonestyTrial:
    untraceable: frozenset[int]
    duration_ms: float


OPUS_FIT_TRIALS: list[FitTrial] = [
    FitTrial(0.93, 3, 3996),
    FitTrial(0.92, 3, 7667),
    FitTrial(0.92, 3, 5527),
    FitTrial(0.62, 2, 8863),
    FitTrial(0.93, 3, 6115),
]
# Honesty trials are recorded for token/latency cost only -- they were run against a
# mid-edit master, so their answer set isn't comparable to a fixed ground truth and is
# NOT scored for accuracy here (the determinism + cost argument stands regardless).
OPUS_HONESTY_TRIALS: list[HonestyTrial] = [
    HonestyTrial(frozenset({2, 90}), 13585),
    HonestyTrial(frozenset({2, 90}), 14526),
    HonestyTrial(frozenset({2, 90}), 13849),
]
GROUND_TRUTH_FULLNESS = 0.95
GROUND_TRUTH_ORPHANS = 0
# Haiku 4.5 reference (same tasks, cheaper model): fit fullness 0.92x3 / orphans 2,2,3
# (also 0/3 on orphans), ~2.5s, ~12.8k tok; honesty answers none/none/{86}, ~10s,
# ~21.8k tok. Cheaper per token but no more accurate.
HAIKU_NOTE = "Haiku 4.5 sampled too: same 0-orphan-misses, ~12.8k/21.8k tok, faster but no more accurate."


@dataclass
class StageResult:
    """One deterministic stage's measured cost + the LLM counterfactual."""
    stage: str
    det_latency_s: float
    det_inference_tokens: int      # always 0 -- Python computes the verdict, no model call
    det_report_tokens: int         # what Claude READS back: the compact pre-computed report
    llm_tokens_est: int            # what an LLM eyeball would INSTEAD spend per check
    llm_latency_s_obs: float       # median observed subagent wall-clock
    llm_trials: int
    llm_correct: int               # trials whose answer matched ground truth


def image_tokens(width_px: int, height_px: int) -> int:
    """Anthropic image-token estimate after the long-edge downscale cap."""
    long_edge = max(width_px, height_px)
    scale = min(1.0, VISION_LONG_EDGE_CAP / float(long_edge))
    w, h = width_px * scale, height_px * scale
    return round(w * h / IMAGE_TOKENS_DIVISOR)


def text_tokens(*chars: int) -> int:
    return round(sum(chars) / CHARS_PER_TOKEN)


def median(xs: list[float]) -> float:
    s = sorted(xs)
    return s[len(s) // 2]


def bootstrap_sample() -> None:
    """Regenerate output/<SAMPLE_COMPANY>/ from the committed slot fixture.

    The real output/ dir is gitignored and transient, so the benchmark must be
    able to recreate its own sample to stay reproducible. This copies the fixture
    slots into place, runs the SAME deterministic assemble + pdflatex compile the
    /tailor chain uses, and (re)renders the page PNG. Idempotent: if a compiled
    PDF + tex already exist, it leaves them alone.
    """
    if SAMPLE_PDF.exists() and SAMPLE_TEX.exists():
        return
    import assemble_resume  # noqa: E402  (SCRIPTS on path above)
    import latex_build      # noqa: E402  (SRC on path above)

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLE_SLOTS.write_text(SAMPLE_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    assemble_resume.assemble(SAMPLE_COMPANY, force=True)
    if not latex_build.compile_tex(SAMPLE_TEX, RESUME_JOBNAME, 2):
        raise RuntimeError(f"pdflatex failed assembling the bench sample in {SAMPLE_DIR}")
    if PAGE_PNG.exists():
        PAGE_PNG.unlink()  # force a fresh render to match the rebuilt PDF


def measure_fit(reps: int = 3) -> tuple[float, dict[str, object]]:
    """Time check_resume_fit.py (subprocess, needs .venv pdfplumber); return verdict."""
    py = str(VENV_PY) if VENV_PY.exists() else "python3"
    cmd = [py, str(SCRIPTS / "check_resume_fit.py"), "--json", SAMPLE_COMPANY]
    latencies: list[float] = []
    out = ""
    for _ in range(reps):
        t = time.perf_counter()
        proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
        latencies.append(time.perf_counter() - t)
        out = proc.stdout
    data: dict[str, object] = json.loads(out)
    return median(latencies), data


def measure_honesty(reps: int = 3) -> tuple[float, list[str], str]:
    """Time lint_honesty.lint_resume in-process; return (latency, flags, report_line)."""
    import lint_honesty  # noqa: E402  (path injected above)

    latencies: list[float] = []
    flags: list[str] = []
    for _ in range(reps):
        t = time.perf_counter()
        flags = lint_honesty.lint_resume(SAMPLE_COMPANY)
        latencies.append(time.perf_counter() - t)
    return median(latencies), flags, lint_honesty.report_line(flags, "resume")


def build_report() -> dict[str, object]:
    if not PAGE_PNG.exists() and SAMPLE_PDF.exists():
        subprocess.run(
            ["pdftoppm", "-png", "-r", "150", "-f", "1", "-l", "1",
             str(SAMPLE_PDF), str(REPO / "bench" / "nuro_page")],
            check=True,
        )
    from PIL import Image  # noqa: E402

    w, h = Image.open(PAGE_PNG).size
    fit_img_tokens = image_tokens(w, h)

    fit_latency, fit_verdict = measure_fit()
    honesty_latency, honesty_flags, honesty_line = measure_honesty()

    # What Claude actually READS back through the hook (the pre-computed answer):
    #   fit  -> check_resume_fit.py's human "text" block (per-bullet report)
    #   honesty -> the single report_line
    # This is the honest "deterministic token" cost -- small, but NOT zero.
    fit_report_text = str(fit_verdict.get("text", ""))
    fit_report_tokens = text_tokens(len(fit_report_text))
    honesty_report_tokens = text_tokens(len(honesty_line))

    # master + output sizes drive the honesty-review token estimate
    from paths import MASTER, OUTPUT  # noqa: E402

    master_chars = len(MASTER.read_text(encoding="utf-8"))
    out_chars = len((OUTPUT / SAMPLE_COMPANY / "resume.tex").read_text(encoding="utf-8"))

    fit_llm_tokens = fit_img_tokens + FIT_PROMPT_TOKENS + FIT_OUTPUT_TOKENS
    honesty_llm_tokens = (
        text_tokens(master_chars, out_chars) + HONESTY_PROMPT_TOKENS + HONESTY_OUTPUT_TOKENS
    )

    # Fit accuracy, scored two ways against the deterministic ground truth:
    #   exact    = fullness within +-0.02 AND orphan count right (what the checker nails)
    #   ballpark = fullness merely within +-0.05 (ignores the orphan miss)
    fit_exact = sum(
        1 for t in OPUS_FIT_TRIALS
        if abs(t.fullness - GROUND_TRUTH_FULLNESS) <= 0.02
        and t.orphans == GROUND_TRUTH_ORPHANS
    )
    fit_ballpark = sum(
        1 for t in OPUS_FIT_TRIALS
        if abs(t.fullness - GROUND_TRUTH_FULLNESS) <= FULLNESS_BALLPARK
    )

    fit = StageResult(
        stage="fit_check",
        det_latency_s=round(fit_latency, 3),
        det_inference_tokens=0,
        det_report_tokens=fit_report_tokens,
        llm_tokens_est=fit_llm_tokens,
        llm_latency_s_obs=round(median([t.duration_ms for t in OPUS_FIT_TRIALS]) / 1000, 2),
        llm_trials=len(OPUS_FIT_TRIALS),
        llm_correct=fit_exact,
    )
    honesty = StageResult(
        stage="honesty_lint",
        det_latency_s=round(honesty_latency, 4),
        det_inference_tokens=0,
        det_report_tokens=honesty_report_tokens,
        llm_tokens_est=honesty_llm_tokens,
        llm_latency_s_obs=round(median([t.duration_ms for t in OPUS_HONESTY_TRIALS]) / 1000, 2),
        llm_trials=len(OPUS_HONESTY_TRIALS),
        llm_correct=-1,  # not scored: trials ran against a mid-edit master
    )

    return {
        "sample_company": SAMPLE_COMPANY,
        "llm_model": LLM_MODEL,
        "run_date": RUN_TIMESTAMP,
        "page_png_size": [w, h],
        # --- LIVE, reproducible: cost measured on the freshly bootstrapped sample.
        # Its verdict/fullness reflect today's fixture (verbatim bullets, so a couple
        # may orphan where /tailor would reword); the COST numbers are what matter and
        # are robust to the exact selection.
        "live_sample": {
            "verdict": fit_verdict.get("verdict"),
            "fullness": fit_verdict.get("fullness"),
            "honesty_flags": honesty_flags,
            "fit_report_tokens": fit.det_report_tokens,
            "honesty_report_tokens": honesty.det_report_tokens,
        },
        # --- FROZEN, dated: accuracy can't be re-judged against a moving page, so the
        # subagent trials + the ground truth they were scored against are constants from
        # the RUN_TIMESTAMP run (a structurally-equivalent full one-page resume). Refresh
        # via the documented FIT_SUBAGENT_PROMPT / HONESTY_SUBAGENT_PROMPT.
        "fit_accuracy": {
            "frozen_trial_date": RUN_TIMESTAMP,
            "ground_truth_at_trial": {"fullness": GROUND_TRUTH_FULLNESS,
                                      "orphans": GROUND_TRUTH_ORPHANS},
            "trials": len(OPUS_FIT_TRIALS),
            "exact_matches": fit_exact,             # fullness+-0.02 AND orphans right
            "ballpark_fullness_matches": fit_ballpark,  # fullness within +-0.05 only
            "deterministic_exact_rate": 1.0,        # the checker measures; it is always right
            "llm_exact_rate_user_observed": 0.30,   # Khoa's larger separate sample (~30%)
        },
        "haiku_note": HAIKU_NOTE,
        "stages": [asdict(fit), asdict(honesty)],
        "totals": {
            "det_inference_tokens": 0,
            "det_report_tokens_per_cycle": fit.det_report_tokens + honesty.det_report_tokens,
            "llm_tokens_est_per_cycle": fit.llm_tokens_est + honesty.llm_tokens_est,
            "token_reduction_x": round(
                (fit.llm_tokens_est + honesty.llm_tokens_est)
                / max(1, fit.det_report_tokens + honesty.det_report_tokens), 1),
            "det_checks_latency_s": round(fit.det_latency_s + honesty.det_latency_s, 3),
            "llm_eyeball_latency_s_obs": round(fit.llm_latency_s_obs + honesty.llm_latency_s_obs, 2),
        },
    }


def main() -> int:
    # Self-bootstrap: rebuild the sample from the committed fixture if output/ was
    # cleaned (it is gitignored + transient). Keeps the benchmark reproducible.
    try:
        bootstrap_sample()
    except Exception as e:  # noqa: BLE001 - surface any assemble/compile failure clearly
        print(f"could not bootstrap the bench sample: {e}\n"
              f"check pdflatex + .venv, see bench/REPORT.md 'Reproducing'.", file=sys.stderr)
        return 2
    rep = build_report()
    (REPO / "bench" / "results.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    t = rep["totals"]
    fa = rep["fit_accuracy"]
    assert isinstance(t, dict) and isinstance(fa, dict)
    print(f"sample: {rep['sample_company']}  page {rep['page_png_size']}  vs {rep['llm_model']}")
    print("-" * 76)
    for s in rep["stages"]:  # type: ignore[union-attr]
        assert isinstance(s, dict)
        acc = "not scored" if s["llm_correct"] == -1 else f"{s['llm_correct']}/{s['llm_trials']} exact"
        print(f"{s['stage']:>13}  det {s['det_latency_s']:>6}s / read {s['det_report_tokens']} tok"
              f" (0 inference)   vs LLM ~{s['llm_tokens_est']} tok / {s['llm_latency_s_obs']}s"
              f"   accuracy {acc}")
    print("-" * 76)
    print(f"fit accuracy: deterministic 100% exact (measures word-boxes); "
          f"{rep['llm_model']} {fa['exact_matches']}/{fa['trials']} exact, "
          f"{fa['ballpark_fullness_matches']}/{fa['trials']} ballpark on fullness")
    print(f"per save cycle: deterministic = 0 inference tok, reads {t['det_report_tokens_per_cycle']} "
          f"tok report, {t['det_checks_latency_s']}s   |   LLM eyeball ~= "
          f"{t['llm_tokens_est_per_cycle']} tok, {t['llm_eyeball_latency_s_obs']}s "
          f"(~{t['token_reduction_x']}x more)")
    print("-> bench/results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
