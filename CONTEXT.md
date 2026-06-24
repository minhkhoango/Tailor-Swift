# CONTEXT — Tailor Swift

Orientation for this repo: the domain language, the core invariants, and how the
pieces fit. Read this before changing the pipeline. Code structure and dates live in
git and the source files; this file is the *why* and the *vocabulary*, the parts that
drift if restated as comments.

## What this is

One **master resume** of all of Khoa's real experience. For each job, the tool **selects**
the most relevant pieces, *lightly* rewords them to match the job's keywords, and packs
them into exactly one full page — a compiled, ATS-friendly PDF.

The whole thing runs as a [Claude Code](https://claude.com/claude-code) skill (`/tailor`).
Everything after the selection step is deterministic: assemble → compile → fit-check →
honesty-check.

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
- **Project** — a selectable `@key` block. Usually ~3 are chosen per JD to fill the page.
- **Slot file** — `output/<company>/resume.slots.json`. The LLM's *only* handwritten
  artifact: which blocks, which bullets, light rewords, the skills rows. The `.tex` is
  generated from it — a direct `.tex` edit is overwritten on the next assemble.
- **Bullet reference** — inside a slot, `{"id": n}` pulls `\resumeItem` #n verbatim
  (honesty-safe by construction); `{"text": "..."}` is a light reword (rejected if it runs
  >4 words longer than its source bullet).
- **`emph`** — a project's heading tech-stack, replaced with the 3 most JD-relevant techs
  (hard cap 3).
- **Fullness / fill** — how far down the one page the content reaches. Target **0.95–1.0**.
  Empty space at the bottom is the failure to avoid.
- **Spillover / orphan** — a bullet whose last rendered line carries ≤4 words (a dangling
  tail). Lightly reword to fill; never cut a fact.
- **Test fixture / subject** — `tests/fixtures/<subject>/`, a self-labeling test case that
  mirrors the real `output/<company>/` layout: a `resume.slots.json` (and optionally a
  `resume.tex`) plus an `expected.json` carrying that subject's labels. The suite *discovers*
  subjects by globbing this dir, so adding a case is adding a folder — never a Python edit.
  fit-check labels are **verdict-level or ranges** (PDF geometry drifts with pdflatex/fonts);
  assemble labels are **exact golden-`.tex`** (pure text). Distinct from `dataset/` (frozen
  benchmark pairs) and `assets/` (the pool); fixtures are disposable test inputs, not
  deliverables and not benchmarks.
- **Honesty check** — the two *deterministic* audits the hook runs: number-traceability
  (every output number traces to a *selected* block) and the PR-Pilot either/or bullet.
  Everything else in `honesty-rules.md` is the LLM's own pre-save checklist.
- **Uncovered must-have** — a JD requirement no honest pool block can cover. It is surfaced,
  never papered over. This line is what changes whether Khoa hits "submit".

## The pipeline

```
scrape-jobs ──▶ jobDescription/<Company>.txt ──▶ /tailor ──▶ output/<Company>/resume.pdf
  (feeder)            (input)                    (skill)         (deliverable)
```

Per JD, inside `/tailor`:

1. **Analyze** the JD — role_type, ranked keywords, must-haves, anti-signals.
2. **Select** blocks — score each `@key` against the ranked keywords; keep the top few that
   fill the page. Keep a project's bullets together; both experiences always in.
3. **Write the slot file** — never the `.tex` by hand.
4. **Honesty audit** the draft *before* saving (the `honesty-rules.md` checklist).
5. **Save the slot** → a PostToolUse hook auto-runs the deterministic chain and returns one
   combined report. The LLM never invokes the chain itself.
6. **React** to the report by editing the slot and re-saving (~3 passes) until it reads
   `OK` + `honesty: clean`.

## The deterministic chain (owned by code, not the model)

Triggered by saving the slot file. Lives in `scripts/tailor_hook.py`:

**assemble → compile → fit-check → honesty-check → one combined report.**

- **Assemble** (`assemble_resume.py`) — owns both the slot schema *and* the mechanical build:
  copy preamble/heading/Education verbatim, emit chosen blocks (bullets byte-identical by id
  or from `text`), rebuild Technical Skills from slot rows. **Ordering is owned here, not by
  the model**: experiences forced to IOE→FPT; projects sorted by master end-date (most recent
  first, "Present" beats any date); stable sort keeps slot order on a date tie.
- **Compile** (`scripts/pdf_compile.py`) — pdflatex, two passes for resumes.
- **Fit-check** (`check_resume_fit.py`) — reads rendered word-boxes via pdfplumber to measure
  fullness and detect spillover. It only *detects*; it never edits the `.tex`.
- **Honesty-check** — the deterministic number-traceability audit, in-process.
- **Structure advisory** — a tailored resume always carries exactly three projects; any other
  count yields a non-blocking `structure: WARN` line (`EXPECTED_PROJECTS` in `tailor_hook.py`).
  It does *not* flip `ok` — the fit verdict stays the real gate — but it is always surfaced so
  the model packs/prunes to three rather than discovering the mismatch via fullness alone.

The report verdicts the model reacts to: `UNDERFULL` / `OVERFULL` / `MULTIPAGE` /
`SPILLOVER` / `FLAG` / `WRAP` (skills row) / `honesty: FLAGS [...]` / `structure: WARN` / `OK`.

## Key boundaries / invariants

- **The model writes one file, code does the rest.** The slot file is the entire LLM surface.
  Assembly, ordering, compilation, measurement, and the deterministic honesty checks are all
  code. This split is deliberate — it keeps the honest facts mechanically guaranteed.
- **`paths.py` is the single home for repo layout.** Move the skill folder and only that file
  changes. No other script re-derives the root.
- **`tex_parse.py` is the single home for LaTeX parsing** (one brace matcher, one comment
  stripper, one master-block parser). Don't reimplement parsing elsewhere.
- **`tailor_lock.py` owns the `.ai_phase.lock` protocol** — the one signal that an AI tailor turn
  is mid-flight for a company. The assembler marks it; `capture_baseline.py` (Stop hook) and
  `scripts/watch.py` read it. Nobody else touches the lock's file format or staleness window.
- **Dataset pairs are locked.** A company captured to `dataset/<company>/` is frozen — the
  assembler refuses to regenerate it, so its `resume.ai.tex` (AI baseline) / `resume.final.tex`
  (human final) benchmark pair stays intact.

## Where things live

```
assets/master_resume.tex       THE pool — the source of truth (under .claude/skills/tailor/)
jobDescription/<Company>.txt    JD input (from /scrape-jobs or dropped in by hand)
output/<Company>/               per-company: resume.slots.json → resume.tex → resume.pdf
dataset/<Company>/              frozen AI-baseline + human-final benchmark pairs
.claude/skills/tailor/          the self-contained skill: SKILL.md, references/, scripts/, assets/
                                (scripts/ owns the compile core + live watcher too)
.claude/skills/scrape-jobs/     the JD feeder (Playwright + simplify JSON APIs)
build_resume.py                 standalone user tool: rebuild resume PDFs by hand (no skill import)
build_cover_letter.py           standalone user tool: rebuild cover-letter PDFs by hand
tests/                          stdlib unittest suite, one file per script
tests/fixtures/<subject>/       self-labeling test cases (resume.slots.json [+ resume.tex]
                                + expected.json); test_fixtures.py discovers + stages them
```

## Conventions

- Python in **pylance strict** typing. Prefer **fewer files with big, testable functions**
  over many tiny single-purpose files — the existing module split reflects this (each script
  owns a whole concern end to end).
- Bullet style: tech on the heading line, "(Github)" links, one-line bullets, keep the
  specific numbers for the interview.
- Big changes go on a **git worktree**.
