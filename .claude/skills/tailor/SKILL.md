---
name: tailor
description: Tailor Khoa's master resume into a packed 1-page company-specific resume (and optionally a cover letter) from a .txt job description. Use for "/tailor", "tailor the new JDs", "tailor for <company>", "redo the <company> resume".
---

# Resume Tailor

Turn each `.txt` job description in `jobDescription/` into a **full** 1-page resume by
SELECTING from one master pool and LIGHTLY rewording for the JD's keywords. Facts are
locked; wording barely moves.

## Golden rules
1. **Select, don't rewrite.** Pick whole projects and keep their bullets faithful — swap in
   exact JD keywords or lightly rephrase, nothing more. Never heavy-rewrite or shorten a bullet.
2. **Pack the page.** Output is strictly 1 page, filled to **0.95–1.0**. Empty space at the
   bottom is the failure to avoid.
3. **Honesty is absolute.** Every number/date/tech/company traces 1:1 to source. The project
   pool is closed — never invent projects. See `references/honesty-rules.md`.

## Commands
- `/tailor` — process every `jobDescription/*.txt` with no matching `output/<stem>/` yet (idempotent).
- `/tailor --cover` — same, plus a cover letter for each (off by default; see `references/cover-letter.md`).

A note left **inside** a JD `.txt` (e.g. "emphasize backend") is guidance for that job — follow it.
To redo a company, delete its `output/<company>/` and re-run. (A company already captured to
`dataset/<company>/` is locked: the assembler refuses to regenerate it, so its benchmark pair is safe.)

## The pool (source of truth: `assets/master_resume.tex`)
Every project and the two experiences live there as `% @key:` blocks. That file is the **only**
source of truth for which projects exist, their bullets, and their dates — this doc never restates
them (they drift). Read the `@key` blocks each run. Both experiences are always kept, IOE then FPT.

## Pipeline (per JD)
1. **Analyze the JD** — role_type, ranked keywords, must-haves, anti-signals.
2. **Select projects** — judge each `@key` block against the JD's ranked keywords; keep the top
   3 that fill the page. Keep a project's bullets together; don't cherry-pick one down
   to a single bullet. Both experiences always in.
3. **Write `output/<company>/resume.slots.json`** — the slot file (schema below). You do **not**
   hand-write the `.tex`; the assembler builds it (a direct `.tex` edit is overwritten next assemble).
4. **Honesty audit** — apply `references/honesty-rules.md` to your draft **before** saving.
5. **Save the slot** → a hook auto-runs the chain (assemble → build PDF → fit check → the two
   deterministic honesty checks) and returns one combined report. **You never invoke these yourself.**
6. **React to the report** by editing the slot and re-saving (cap ~3 passes) until it reads
   `OK` + `honesty: clean` — see the table below.
7. **Cover letter** — only with `--cover`. Fill `<<Company>>` + `<<WHY_COMPANY>>`; body is fixed.
   See `references/cover-letter.md`.
8. **Report** — print the per-JD summary block (below). No `reasoning.md` is written.
9. **Start the live watcher** (once, after the *final* JD reads `OK` + `honesty: clean`) — launch
   it in the **background**; never ask the user to start it. See "Local setup & the live watcher".

## Slot schema (`output/<company>/resume.slots.json`)
```json
{
  "company": "Apple",
  "experiences": [
    {"key": "ioe", "bullets": [{"id": 1}, {"id": 2}, {"text": "lightly reworded bullet ..."}]},
    {"key": "fpt", "bullets": [{"id": 1}, {"id": 2}]}
  ],
  "projects": [
    {"key": "local_lens", "emph": "TypeScript, React, AWS", "bullets": [{"id": 1}, {"id": 2}]},
    {"key": "pr_pilot", "bullets": [{"id": 1}, {"id": 3}]}
  ],
  "skills": [["Languages", "Python, TypeScript, C++, SQL"], ["AI/ML", "PyTorch, Claude API"]]
}
```
- **`key`** — the `% @key:` of a block in `master_resume.tex` (`ioe`, `fpt`, project keys).
- **`{"id": n}`** — pull `\resumeItem` **#n** of that block **verbatim** (1-based, master order).
  Prefer ids: byte-identical bullets are honesty-safe by construction.
- **`{"text": "..."}`** — a light reword: swap a verb / splice in an exact JD keyword, same length.
  The assembler **rejects** a `text` that runs more than **4 words longer** than its source bullet.
  When unsure a fact survives a reword, use the verbatim id.
- **`emph`** (projects only) — replaces the heading's tech-stack `\emph{}` with the **3 most
  JD-relevant** techs (hard cap 3; assembler errors on 4+). Omit to keep the master default.
- **`skills`** — up to **5** `[category, content]` rows, rebuilt per JD from `references/keywords.md`.
  Each row must fit one rendered line; escape `&` as `\\&`. **Pack each row full** — add every
  JD-relevant ALLOWED keyword that still fits the one line (ATS rewards more verbatim matches), and
  pad sparse rows with adjacent honest keywords from the same category. A half-empty skill row is a
  wasted line: keep adding until the next term would WRAP, then stop. Never repeat a keyword across
  rows, and never pull from FORBIDDEN.

**Ordering is automatic** — you don't sort. Experiences are forced to IOE→FPT; projects are sorted
by their master end-date, most recent first. The only ordering you control: when two projects share
an end-date the assembler keeps your slot order, so list the more JD-relevant first. Dates are
**never** in the slot — always taken verbatim from the master.

## React to the fit + honesty report
The report is one line when clean; when not, it shows only the problematic bullets/rows.
- **`UNDERFULL`** (<0.95) — add a whole JD-relevant project, or one more faithful pool bullet.
  **Never pad a bullet** (the assembler rejects a reword >4 words past its source). Once all bullets
  + both experiences + 5 skill rows are in and it's still under, accept and stop.
- **`SPILLOVER`** / a **`FLAG`** bullet — its last wrapped line is ≤4 words; lightly reword so it
  fills. Never cut a number fact. `SKIP` = low-confidence match, not a target.
- **`OVERFULL`** / **`MULTIPAGE`** — drop the lowest-JD-scoring project. Never drop education,
  header, or either experience.
- **`WRAP`** on a skill row — prune its lowest-signal entries until it's one line.
- **`structure: WARN`** — the slot has a project count other than 3; add or drop a project so
  exactly 3 ship. Advisory (won't block), but always fix it — 3 projects is the rule.
- **`honesty: FLAGS [...]`** — fix each (a stray untraceable number). The
  rest of the honesty audit is yours from `honesty-rules.md` — catch it before you save.
- **`OK`** + `honesty: clean` — done.

## Local setup & the live watcher
- **Setup (once):** `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
- **Watcher (live PDF + human-final snapshots) — auto-started, don't ask the user to run it.**
  As the final step of a run (pipeline step 9), just run it **in the foreground** (it
  self-detaches — do NOT background it):
  `.venv/bin/python "$CLAUDE_PROJECT_DIR/.claude/skills/tailor/scripts/watch.py"`. It rebuilds the
  PDF live and snapshots `dataset/<co>/*.final.tex` on each human edit. The command **always
  returns instantly** with a one-line verdict — it double-forks a detached daemon (logs to
  `.watch.log`) when none is running, or prints `already running (pid N)` when one is. It is a
  **singleton** (`.watch.pid` at the repo root), so launching it every run is safe and idempotent;
  a fast clean exit is success, NOT a watcher that died — never try to "restart" or debug it.
- **AI-baseline capture (Stop hook):** in `.claude/settings.local.json`, so the AI's first version
  is snapshotted to `dataset/<co>/resume.ai.tex` when each tailor turn ends:
  ```json
  { "hooks": { "Stop": [ { "hooks": [ { "type": "command",
    "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/skills/tailor/scripts/capture_baseline.py\"" } ] } ] } }
  ```

## Per-JD summary (print to terminal)
```
<company>:
  projects: <P1>, <P2>, <P3>      (most recent first)
  fill: 0.9x   verdict: OK | UNDERFULL(accepted) | ...
  honesty flags: <triggers caught + fixed> | none
  uncovered must-haves: <JD requirements with no honest home> | none
```
The `uncovered must-haves` line is the one you must always surface — it's what changes whether Khoa
hits "submit".
