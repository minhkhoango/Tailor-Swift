# CONTEXT — Tailor Swift

Orientation for this repo: the domain language, the core invariants, and how the
pieces fit. Read this before changing the pipeline. Code structure and dates live in
git and the source files; this file is the *why* and the *vocabulary*, the parts that
drift if restated as comments.

## What this is

One **master resume** of all of Khoa's real experience. For each job, the tool **selects**
the most relevant pieces, *lightly* rewords them to match the job's keywords, and packs
them into exactly one full page — a compiled, ATS-friendly PDF.

It runs as a **plain Python program** (`python -m tailor`) that calls the Anthropic API
directly 1–3 times per JD. Everything after the model's selection step is deterministic:
assemble → compile → fit-check → honesty-check.

## The one rule everything serves

**Wording barely moves; facts never move.** Every number, date, technology, and company
on an output page traces 1:1 back to the master resume (or the project's own repo).
Nothing is invented. This is not a style preference — it is the load-bearing invariant.
The selection is a *projection* of a closed pool, never a generative rewrite.

When two values conflict, honesty wins over fullness, and fullness wins over keyword
match. Never sacrifice a fact to fill the page or to hit a JD keyword.

## Ubiquitous language

- **Master resume / the pool** — `assets/master_resume.tex`. The single source of truth.
  Every project and the two experiences live there as `% @key:` blocks. The pool is
  **closed**: there are exactly the projects that exist; you never invent one. This is the
  only file that says which projects exist, their bullets, and their dates — nothing else
  restates them.
- **`@key` block** — one selectable unit in the master (`ioe`, `fpt`, a project key). Has a
  verbatim heading and an ordered list of `\resumeItem` bullets.
- **Experience** — the two jobs (IOE then FPT). **Always both kept**, always in that order.
  FPT was **quant-finance work** (a Random-Forest trading model on Vietnamese equities) —
  *not* telecom; never frame it as "FPT Telecom data work."
- **Project** — a selectable `@key` block. Usually ~3 are chosen per JD to fill the page.
- **Slot file** — `output/<stem>/resume.slots.json`. The LLM's *only* deliverable: which
  blocks, which bullets, light rewords, the skills rows. The `.tex` is generated from it — a
  direct `.tex` edit is overwritten on the next assemble.
- **Digest** — the token-light, plain-text view of the pool the model actually reads,
  rendered at runtime from `master_resume.tex` via `tex_parse` (`tailor/digest.py`). Each
  `@key` block with its heading and bullets numbered `1..n` — exactly the numbering a
  `{"id": n}` slot reference points at. Never hardcode block text; it derives from the master,
  so it re-warms the prompt cache automatically when the master changes.
- **Bullet reference** — inside a slot, `{"id": n}` pulls `\resumeItem` #n verbatim
  (honesty-safe by construction); `{"text": "..."}` is a light reword (rejected if it runs
  >4 words longer than its source bullet).
- **`emph`** — a project's heading tech-stack, replaced with the 3 most JD-relevant techs
  (hard cap 3).
- **Fullness / fill** — how far down the one page the content reaches. Target **0.95–1.0**.
  Empty space at the bottom is the failure to avoid.
- **Spillover / orphan** — a bullet whose last rendered line carries ≤4 words (a dangling
  tail). Lightly reword to fill; never cut a fact.
- **Scratch dir** — `.tailor_cache/<stem>/`. Where each in-flight pass is assembled and
  compiled. Only the *final accepted* pass is copied to `output/<stem>/`. Deleted on success;
  **kept on abort** for post-mortem. The live watcher ignores it, so it never races.
- **AI-baseline slot** — `dataset/<stem>/resume.ai.slots.json`, the AI's first shipped slots,
  snapshotted (frozen) the first time a non-frozen company ships. Paired with
  `resume.final.slots.json` (your later hand-edits, captured by the watcher) it is the
  slot-level benchmark pair for prompt tuning. A frozen company is never re-snapshotted.
- **why_company.md** — `output/<stem>/why_company.md`, the short honest "why this company"
  blurb you paste into an application's "why us" box. Generated **apply-time** by
  `tailor why <glob>` (one web-search call, verifiable numbers only), not in the batch run.
  It is the *only* "why" artifact — there is no cover letter.
- **Test fixture / subject** — `tests/fixtures/<subject>/`, a self-labeling test case that
  mirrors the real `output/<stem>/` layout: a `resume.slots.json` (and optionally a
  `resume.tex`) plus an `expected.json` carrying that subject's labels. The suite *discovers*
  subjects by globbing this dir, so adding a case is adding a folder — never a Python edit.
  fit-check labels are **verdict-level or ranges** (PDF geometry drifts with pdflatex/fonts);
  assemble labels are **exact golden-`.tex`** (pure text). Distinct from `dataset/` (frozen
  benchmark pairs) and `assets/` (the pool); fixtures are disposable test inputs.
- **Honesty check** — the one *deterministic* audit the chain runs: number-traceability
  (every output number traces to a *selected* block). Everything else is the model's checklist —
  the global golden rules folded into `SYSTEM_PROMPT`; it is not restated in code or in per-block
  master notes.
- **Uncovered must-have** — a JD requirement no honest pool block can cover. It is surfaced
  (the slot's `uncovered` list), never papered over. This is what changes whether Khoa hits
  "submit".

## The pipeline

```
scrape-jobs ──▶ jobDescription/<stem>.txt ──▶ python -m tailor ──▶ output/<stem>/Khoa_Ngo_resume.pdf
  (feeder)            (input)                  (the program)            (deliverable)
```

Per JD, the program holds one stateful model conversation (the cached prefix — system prompt
+ digest, the digest carrying the keyword ledger + ALLOWED skill palette from the
master — stays prompt-cached across JDs and turns):

1. **Analyze + select** — one model turn returns a `Slots` object (structured output,
   schema-enforced): both experiences, ~3 projects, bullets by id or light reword, skills
   rows, and any `uncovered` must-haves. Ordering is *not* the model's job (code owns it).
2. **Run the chain** — code assembles → compiles → fit-checks → honesty-checks in the scratch
   dir and builds one combined report.
3. **React** — the report is fed back as the next user turn; the model returns revised slots.
   Loop up to **2 passes** until `OK` + `honesty: clean`.
4. **Ship or abort** — an accepted resume (incl. an accepted `UNDERFULL`) ships to
   `output/<stem>/` and snapshots the AI baseline. If honesty never clears within the cap,
   **nothing ships**: the JD aborts, the scratch dir is kept, the abort is logged loudly.

Why-company is a **separate, apply-time verb** (`tailor why <glob>`), idempotent: it tailors
the resume first if missing, then writes `why_company.md` unless it already exists (`force`
overrides both gates).

## The deterministic chain (owned by code, not the model)

Driven in-process by the orchestrator (`tailor/core/chain.py:run_chain`) — not a PostToolUse
hook anymore. The orchestrator hands it a slot dict + a working dir:

**assemble → compile → fit-check → honesty-check → one combined report.**

- **Assemble** (`tailor/core/assemble_resume.py`) — owns the mechanical build *only* (the slot
  schema now lives in `core/slots.py` — see below): copy preamble/heading/Education verbatim,
  emit chosen blocks (bullets byte-identical by id or from `text`), rebuild Technical Skills from
  slot rows. It takes a canonical `Slots` and writes the `.tex` — one door, `assemble(slots,
  out_dir)`. **Ordering is owned here, not by the model**: experiences forced to IOE→FPT;
  projects sorted by master end-date (most recent first, "Present" beats any date); stable sort
  keeps slot order on a date tie. Each validation is a pure checker (`check_reword`,
  `stack_items`, …) so the inspect harness can tabulate every problem at once instead of raising
  on the first.
- **Compile** (`tailor/core/pdf_compile.py`) — pdflatex, two passes for resumes.
- **Fit-check** (`tailor/core/check_resume_fit.py`) — reads rendered word-boxes via pdfplumber
  to measure fullness and detect spillover. It only *detects*; it never edits the `.tex`. Runs
  in-process under the venv (no subprocess).
- **Honesty-check** — the deterministic number-traceability audit, in-process.
- **Structure advisory** — a tailored resume always carries exactly three projects; any other
  count yields a non-blocking `structure: WARN` line (`EXPECTED_PROJECTS` in `chain.py`). It
  does *not* flip `ok` — the fit verdict stays the real gate — but it is always surfaced so the
  model packs/prunes to three.

The report verdicts the model reacts to: `UNDERFULL` / `OVERFULL` / `MULTIPAGE` / `SPILLOVER`
/ `FLAG` / `WRAP` (skills row) / `honesty: FLAGS [...]` / `structure: WARN` / `ERROR` / `OK`.

## Logging

One JSONL stream per run, `logs/tailor-<timestamp>.jsonl` — one JSON object per action, with a
short human echo derived from the same event so live and on-disk never drift. Cron-era
analytics need no separate ledger: `jq 'select(.event=="jd_done" and .verdict!="OK")'` answers
"what failed".

## Key boundaries / invariants

- **The model writes one structure, code does the rest.** The `Slots` object is the entire LLM
  surface. Assembly, ordering, compilation, measurement, and the deterministic honesty check
  are all code. This split is deliberate — it keeps the honest facts mechanically guaranteed.
- **`core/slots.py` is the single home for the Slot concern.** The whole Slot lifecycle lives in
  one pydantic-free module: the canonical `@dataclass Slots` (with `EntrySpec`/`BulletSpec`), the
  on-disk `SlotsData`/`BlockData`/`BulletData` TypedDicts, `SlotsError`, `parse_slots`,
  `from_json` (load a slot file), `to_data` (back to the on-disk dict, key order preserved), and
  the `compact_slots_json`/`pretty_slots_json` renderers. Nothing else parses or serializes a
  slot. The canonical form is the **dataclass**; the on-disk dict is just its serialized shape.
- **`paths.py` is the single home for repo layout.** Relocate the package and only that file
  changes. No other module re-derives the root.
- **`tex_parse.py` is the single home for LaTeX parsing** (one brace matcher, one comment
  stripper, one master-block parser). Don't reimplement parsing elsewhere — `digest.py` and
  the assembler both go through it.
- **`llm.py` is the only module that talks to the model.** It owns the *pydantic* `Slots`/`Why`
  wire schemas (what `messages.parse` enforces), the `SYSTEM_PROMPT` brain, the cached prefix,
  and the one web-search `why` call. The pydantic `Slots` is the wire form only: `from_model`
  (in `llm.py`) adapts it into the canonical `core/slots.py` dataclass right after parsing, so
  the dependency points **core ← llm** and `core/` stays pydantic-free.
- **The keyword ledger has one home** — `assets/master_resume.tex`: the `% KEYWORD LEDGER`
  comment block plus the `\section{Technical Skills}` rows the digest mirrors as the ALLOWED
  palette (edit a skill in ONE place — the Technical Skills row). The digest surfaces it into the
  cached prefix at runtime; global honesty rules are folded into `SYSTEM_PROMPT`. `references/`
  is gone, and so are the per-block `% HONESTY:` notes — honesty rides the deterministic
  number-trace check plus the golden rules; nothing restates the lists in code.
- **Dataset pairs are frozen.** Once a company has a `dataset/<stem>/resume.ai.slots.json`, the
  AI baseline is never overwritten, so the AI-vs-human benchmark pair stays intact. (The
  benchmark format changed from `.tex` to `.slots.json` — see Why notes.)

## Why notes (the non-obvious decisions)

- **Driver: Claude Code agent → direct API.** `/tailor` used to run as a Claude Code skill,
  with the harness as the loop driver and a PostToolUse hook firing the chain. It now runs as a
  thin self-contained program calling the Anthropic API directly. Trade: sunk Pro-quota
  convenience for a metered but self-contained program that a cron can drive and that runs with
  no harness in the middle. The deterministic core was kept untouched; only the driver changed.
- **Benchmark pair format: `.tex` → `.slots.json`.** The benchmark pair used to be
  `resume.ai.tex` / `resume.final.tex`. It is now `resume.ai.slots.json` /
  `resume.final.slots.json`: the slot file is the LLM's actual deliverable (tiny, and it diffs
  cleanly against a human-edited slot for prompt tuning) where the `.tex` was bulky generated
  output. Old `.tex` pairs stay as-is (historical); new pairs use the slot format.

## Where things live

```
assets/master_resume.tex       THE pool + \section{Technical Skills} + % KEYWORD LEDGER (the
                               digest mirrors skills as the ALLOWED palette; no references/, no
                               per-block honesty notes)
jobDescription/<stem>.txt       JD input (from /scrape-jobs or dropped in by hand; gitignored)
output/<stem>/                  per-stem: resume.slots.json → resume.tex → resume.pdf (+ why_company.md)
dataset/<stem>/                 frozen AI-baseline + human-final slot benchmark pairs
.tailor_cache/<stem>/           scratch for in-flight passes (gitignored; kept on abort)
logs/tailor-<ts>.jsonl          per-run JSONL event log (gitignored)
tailor/                         the program: __main__ (CLI), __init__ (orchestrator), llm, digest, log
tailor/core/                    the deterministic core: slots (the Slot concern: schema/parse/
                                serialize), assemble, check_resume_fit, pdf_compile, tex_parse,
                                paths, chain, capture, watch
.claude/skills/scrape-jobs/     the JD feeder (Playwright + simplify JSON APIs)
build_resume.py                 standalone user tool: rebuild resume PDFs by hand (no package import)
tests/                          pytest suite (tier-1 hermetic, tier-2 fixtures, tier-3 inspect)
tests/fixtures/<subject>/       self-labeling test cases; test_fixtures.py discovers + stages them
tests/inspect_inputs/<stem>/    permanent inputs for the tier-3 inspect dump
```

## Conventions

- Python in **pylance strict** typing. Prefer **fewer files with big, testable functions**
  over many tiny single-purpose files — the existing module split reflects this (each module
  owns a whole concern end to end).
- Bullet style: tech on the heading line, "(Github)" links, one-line bullets, keep the
  specific numbers for the interview.
- Secret: `ANTHROPIC_API_KEY` from the env (README documents it; a cron needs it in its env).
- Big changes go on a **git worktree**.
