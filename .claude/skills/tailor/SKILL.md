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
- `/tailor <prefix> [...]` — process the named JD(s); case-insensitive prefix, overwrites existing output.
- `/tailor --cover <prefix>` — also write a cover letter (off by default).
- `/tailor --force` — reprocess all JDs.

## Files
```
jobDescription/<company>.txt          input JD
output/<company>/resume.slots.json    YOU WRITE THIS — the slot file (which bullets, by id)
output/<company>/resume.tex           assembled for you from the slots (don't hand-edit)
output/<company>/cover_letter.tex     only with --cover (fixed body + <<WHY_COMPANY>>)
dataset/<company>/                     git-tracked training pairs (resume.ai.tex / resume.final.tex)
.claude/skills/tailor/
  assets/master_resume.tex            THE source of truth — keyed (@key) blocks + every bullet
  assets/cover_letter.tex             cover-letter template — body fixed, only <<WHY_COMPANY>> varies
  references/tailoring-guide.md        full per-JD pipeline — READ THIS before composing
  references/honesty-rules.md          the audit (the mechanical half runs as lint_honesty.py)
  references/keywords.md               ALLOWED / FORBIDDEN keyword ledger (by category)
  references/cover-letter.md           cover-letter pipeline (only for --cover)
  scripts/assemble_resume.py           slots + master -> resume.tex (fires automatically on save)
  scripts/check_resume_fit.py          deterministic fit + skill-row-wrap checker (auto on save)
  scripts/lint_honesty.py              deterministic FORBIDDEN/number/either-or linter (auto on save)
  scripts/score_projects.py            advisory JD-keyword overlap ranker (run at selection time)
watch.py                               run once: live PDF rebuild + dataset/*.final.tex on save
```

## One-time local setup
- **Watcher (live PDF + human-final snapshots):** start it once and leave it running —
  `.venv/bin/python watch.py` (after `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`).
- **AI-baseline capture (Stop hook):** add this to `.claude/settings.local.json` so the AI's first
  version is snapshotted to `dataset/<co>/resume.ai.tex` when each tailor turn ends:
  ```json
  { "hooks": { "Stop": [ { "hooks": [ { "type": "command",
    "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/skills/tailor/scripts/capture_baseline.py\"" } ] } ] } }
  ```

## Pipeline (per JD)
Full detail in `references/tailoring-guide.md`. In short:

1. **Analyze the JD** — role_type, ranked keywords, must-haves, anti-signals.
2. **Select projects** — run `scripts/score_projects.py <company>` for an advisory ranked overlap
   table; keep the top few (usually 3) that fill the page, **chronological, most recent first**.
   Both experiences always kept, IOE above FPT. Selection is project-granular.
3. **Write `output/<company>/resume.slots.json`** — the slot file: which experiences/projects by
   `@key`, which bullets by `id` (verbatim) or `text` (light reword — never >4 words longer than
   its source), `emph` for project stack lines (the **3 most JD-relevant** techs; assembler caps
   at 3), and the `skills` rows (up to 5) rebuilt from `references/keywords.md`. You do **not**
   hand-write the `.tex` — the assembler builds it. Schema in `references/tailoring-guide.md`.
4. **Honesty audit** — the mechanical rules run as `lint_honesty.py` (below); you still apply the
   judgment rules in `references/honesty-rules.md` (category relabeling, IOE/FPT attribution).
5. **Save → auto assemble + fit + honesty.** Writing `resume.slots.json` fires a hook that runs
   `assemble_resume.py` → `build_resume.py` → `check_resume_fit.py` → `lint_honesty.py` and returns
   the combined report. **You never run these yourself.** (A direct `resume.tex` edit is overwritten
   on the next assemble — edit the slot.)
6. **React to the report by editing the slot** until it reads `OK` + `honesty: clean`:
   - `UNDERFULL` (<0.95) — add a whole JD-relevant project, or one more faithful pool bullet id.
     **Never pad a bullet with filler to gain height** (the assembler rejects a reword >4 words
     past its source). Once all bullets + 5 skill rows are in and it's still under, accept and stop.
   - `SPILLOVER` / orphan `FLAG` — replace the flagged bullet id with a lightly-reworded `text` so
     its last line isn't ≤4 words (*must* be fixed). Never cut a number fact.
   - `OVERFULL` / `MULTIPAGE` — drop the lowest-JD-scoring project. Never drop education, header,
     or either experience. A skill row tagged `WRAP` — prune its lowest-signal entries.
   - `honesty: FLAGS [...]` — fix each (forbidden token, untraceable number, both PR-Pilot bullets,
     unsupported "agentic").
7. **Cover letter** — only with `--cover`. Fill `<<Company>>` + the `<<WHY_COMPANY>>` slot; the
   body is fixed. See `references/cover-letter.md`.
8. **Report** — one ~5-line block per JD (below). No `reasoning.md` is written anymore.

## Per-JD summary (print to terminal)
```
<company>:
  projects: <P1>, <P2>, <P3>      (chronological, most recent first)
  fill: 0.9x   verdict: OK | UNDERFULL(accepted) | ...
  honesty flags: <triggers caught + fixed> | none
  uncovered must-haves: <JD requirements with no honest home> | none
```
The `uncovered must-haves` line is the one you must always surface — it's what changes whether Khoa hits "submit".
