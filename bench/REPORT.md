# Deterministic checks vs. an LLM eyeball — benchmark report

**What this measures.** Two stages of the `/tailor` chain — the **1-page fit check**
(`check_resume_fit.py`) and the **honesty lint** (`lint_honesty.py`) — *could* be done by
asking a model to look at the rendered PDF and read the two `.tex` files and judge. They
are done deterministically in Python instead. This benchmark measures what that buys:
**tokens, latency, accuracy.** All numbers below are produced by `bench/det_vs_llm.py`
and written to `bench/results.json`; this file is the prose around them.

Sample: `Nuro_SWE`, a representative full one-page résumé. Counterfactual model:
**Claude Opus 4.8** (`claude-opus-4-8`) — the model that actually drives `/tailor`, so it
is the right comparison, not a cheaper one.

---

## The honest framing: it is NOT "0 tokens"

An earlier version of the résumé bullets claimed the deterministic checks run "in 0
tokens." That is wrong, and this project's own honesty linter is the reason to fix it.
The precise statement is a **split**:

| | Deterministic stage | LLM eyeball |
|---|---|---|
| **Model inference to compute the verdict** | **0 tokens** — Python (pdfplumber word-boxes / regex number-tracing) computes it; no model call | thousands — the model itself must reason over the input |
| **What Claude then reads back** | a **compact pre-computed verdict** the PostToolUse hook surfaces (`additionalContext`): **~530 tok** fit + **~34 tok** honesty | the model already had to ingest the raw page image (~2,900 tok) / both `.tex` files (~7,000 tok) to produce its answer |

So the deterministic stage spends **0 inference tokens** but is **not free** — Claude reads
a small text report (the per-bullet fit table + the one-line honesty verdict). The honest
comparison is **"read a finished answer" (~564 tok/cycle) vs "eyeball raw input and
reason" (~10,000 tok/cycle)** — roughly an **18× token reduction**, plus the deterministic
answer is exact and instant.

### Exactly what each script hands back to Claude

- **Fit check** (`check_resume_fit.py --json <company>`): the pipeline scrapes the `text`
  field — the human report `format_report()` builds. For the sample that is **1,847 chars
  ≈ 530 tokens**: a `page_count`/`fullness`/`content_band` header, one `[NN] OK/FLAG
  lines=.. last_line_words=..` line **per bullet**, the skill-row lines, and the `verdict`.
  More bullets → a bigger report (it scales with the résumé), but it stays a few hundred
  tokens — far under the ~2,900-token page image.
- **Honesty lint** (`lint_honesty.report_line(...)`): a **single line** —
  `honesty (resume): clean` or `honesty (resume): FLAGS: [...]`. For the sample, **71–119
  chars ≈ 20–34 tokens.**

These are surfaced together by `post_save_build.py` → `tailor_pipeline.assemble_and_check`.

---

## Results (from `bench/results.json`)

Per **save cycle** (one fit check + one honesty lint):

| Metric | Deterministic | LLM eyeball (Opus 4.8) |
|---|---|---|
| Model-inference tokens | **0** | — |
| Tokens Claude reads / spends | **~564** (530 + 34) | **~10,026** (~2,933 + ~7,093) |
| Latency | **~0.26 s** (0.25 + 0.003) | **~20 s** (6.1 + 13.9) |
| Token reduction | — | **~18× more for the LLM** |

Per stage:

| Stage | Det. latency | Det. report read | LLM tokens (est.) | LLM latency (obs.) | Accuracy |
|---|---|---|---|---|---|
| `fit_check` | 0.25 s | ~530 tok | ~2,933 tok | 6.1 s | **det 100% exact; Opus 0/5 exact, 4/5 ballpark fullness** |
| `honesty_lint` | 0.003 s | ~34 tok | ~7,093 tok | 13.9 s | not scored (see caveats) |

**Accuracy headline:** the deterministic fit check returns the **same exact verdict every
run** (it *measures* word-boxes — fullness and orphan counts are facts, not judgments). The
Opus 4.8 eyeball, asked to judge the same page, got it **right ~30% of the time** (Khoa's
larger observed sample; the 5 illustrative trials here landed 0/5 exact — close on
fullness, but it never recovered the orphan count of 0, guessing 2–3). Cheaper models are
no better: Haiku 4.5 made the same orphan misses at ~12.8k/21.8k tok.

---

## Methodology (hybrid)

Two layers, deliberately separated in `results.json` because they have different
reproducibility:

1. **`live_sample` — cost, measured live and reproducible.** `det_vs_llm.py` bootstraps
   the sample, renders the page, times the real `check_resume_fit.py` (subprocess, needs
   `.venv` pdfplumber) and `lint_honesty.lint_resume` (in-process), and measures the exact
   report sizes returned. The LLM token cost is **estimated analytically** (no API key):
   - **Image tokens** = `(w·h)/750` after the 1568px long-edge downscale (Anthropic vision
     rule). The sample page is 1275×1650 → ~2,933 tok with prompt+output.
   - **Text tokens** = `chars / 3.5` over the master + output `.tex`, plus prompt+output →
     ~7,000 tok. (`count_tokens` would refine these; the order of magnitude is the point.)

2. **`fit_accuracy` — accuracy, a frozen dated observation.** You cannot re-judge accuracy
   against a moving page, so the subagent trials and the ground truth they were scored
   against are **constants from the 2026-06-22 run** (`OPUS_FIT_TRIALS`,
   `OPUS_HONESTY_TRIALS`, `GROUND_TRUTH_*`). They were gathered out-of-band by spawning
   **Opus 4.8** subagents via the Claude Code Agent tool, each asked to do the check by eye
   / by reading. The exact prompts are committed as `FIT_SUBAGENT_PROMPT` /
   `HONESTY_SUBAGENT_PROMPT` in `det_vs_llm.py`.

---

## Reproducing

The benchmark is **self-bootstrapping** — the real `output/` dir is gitignored and
transient, so the cost half regenerates its own sample from a committed fixture:

```bash
.venv/bin/python bench/det_vs_llm.py        # rewrites bench/results.json
```

What happens: if `output/Nuro_SWE/` is missing, `bootstrap_sample()` copies
`bench/sample.slots.json` into place and runs the **same** deterministic assemble +
`pdflatex` compile the `/tailor` chain uses, then re-renders the page PNG. Idempotent: an
existing compiled PDF is left alone. Requires `pdflatex` on PATH and the `.venv`
(`pip install -r requirements.txt`).

`bench/sample.slots.json` reconstructs a representative ~1-page selection (both
experiences + four projects, bullets verbatim by id). Because the bullets are verbatim
(not reworded) a couple may orphan where `/tailor` would reword them — so the live sample
reads `SPILLOVER / 0.98` rather than the frozen trial's `OK / 0.95`. **That is expected:**
the cost numbers (latency, report tokens, token estimates) are robust to the exact
selection; only the frozen accuracy block is tied to the historical page.

**To refresh the accuracy trials** (costs real tokens, nondeterministic): spawn a Claude
Code Agent (`model: opus`, `claude-opus-4-8`) per trial with `FIT_SUBAGENT_PROMPT` +
the page PNG, or `HONESTY_SUBAGENT_PROMPT` + the two `.tex` files; record each answer and
wall-clock; paste the tuples into `OPUS_*_TRIALS`; re-run the script.

---

## Caveats / honest limitations

- **LLM token costs are estimated, not metered.** The analytic formulas give the right
  order of magnitude; `count_tokens` (or real API usage) would sharpen them.
- **Honesty accuracy is "not scored."** The Opus honesty trials ran against a mid-edit
  master, so their answer set isn't comparable to a fixed ground truth. The cost and
  latency stand; the determinism argument doesn't depend on scoring them.
- **The fit report scales with the résumé.** ~530 tok is for this 17-bullet sample; a
  shorter résumé returns a smaller report. It never approaches the ~2,900-token page image.
- **`token_reduction_x` uses estimated LLM tokens over measured report tokens.** Treat the
  ~18× as "well over an order of magnitude," not a metered ratio.
- **The accuracy headline is ~30% (Khoa's larger sample).** The 5 trials here are
  illustrative supporting data (0/5 exact), not the basis of the 30% figure.

---

## Where these numbers appear on the résumé

The `Tailor Swift` entry in `master_resume.tex` (key `tailor_swift`) cites:

- *"Fit-checker reads PDF word-boxes in 0.3s, no model vision vs a ~2,900-token eyeball"* —
  0.25 s measured; ~2,933 tok image estimate; "no model vision" = 0 inference tokens.
- *"Honesty linter traces every output number to the master in 3ms, vs a ~7,000-token LLM
  read"* — 0.003 s measured; ~7,093 tok text estimate.
- *"Deterministic checks stay exact on 100% of runs; an Opus 4.8 eyeball managed only
  ~30%"* — `deterministic_exact_rate: 1.0` vs `llm_exact_rate_user_observed: 0.30`.
- *"A 0.8s save hook chains assemble, compile, fit-check and honesty-lint; 45 resumes
  shipped"* — full-chain rebuild ~0.8 s (the two checks are 0.26 s of that).
- *"Backed by a 98-test pytest suite…"* — `pytest -q` → 98 passed.
