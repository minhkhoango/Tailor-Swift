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
output/<company>/resume.tex           you write this (1 page)
output/<company>/cover_letter.tex     only with --cover
.claude/skills/tailor/
  assets/master_resume.tex            THE source of truth — every project + every bullet
  assets/cover_letter.tex             Jake-style cover-letter template
  assets/cover_letter_voice.md        cover-letter voice anchor
  references/tailoring-guide.md        full per-JD pipeline — READ THIS before composing
  references/honesty-rules.md          the audit you run before saving
  references/keywords.md               ALLOWED / FORBIDDEN keyword ledger (by category)
  references/cover-letter.md           cover-letter pipeline (only for --cover)
  scripts/check_resume_fit.py          deterministic fit checker (fires automatically on save)
```

## Pipeline (per JD)
Full detail in `references/tailoring-guide.md`. In short:

1. **Analyze the JD** — role_type, ranked keywords, must-haves, anti-signals.
2. **Select projects** — score the 5 pool projects; keep the top few (usually 3) that fill the
   page, in **chronological order, most recent first**. Both experiences are always kept, IOE
   above FPT. Selection is project-granular: keep a chosen project's bullets together.
3. **Compose `output/<company>/resume.tex`** — copy preamble/heading/education verbatim from
   `master_resume.tex`; embed the chosen experiences + projects with bullets kept faithful
   (light keyword reword only); rebuild Technical Skills from `references/keywords.md`
   (drop/rename/add categories, up to **5** rows, each one rendered line).
4. **Honesty audit** — run `references/honesty-rules.md` before saving; fix every trigger.
5. **Save → auto fit-check.** Writing `resume.tex` fires a hook that recompiles the PDF and runs
   the fit checker, returning a fit report as context. **You never run the checker yourself.**
6. **React to the fit report** until it reads `OK`:
   - `UNDERFULL` (<0.95) — add a whole JD-relevant project, or one more faithful pool bullet to a
     chosen project. Once all bullets + 5 skill rows are in and it's still under, accept it and stop.
   - `SPILLOVER` / orphan `FLAG` — lightly reword the flagged bullet so its last line isn't ≤4
     words (*must* be fixed). Never cut a number fact to do it.
   - `OVERFULL` / `MULTIPAGE` — drop the lowest-JD-scoring project. Never drop education, header,
     or either experience.
7. **Cover letter** — only with `--cover`. See `references/cover-letter.md`.
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
