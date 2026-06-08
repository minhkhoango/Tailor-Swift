# Tailoring guide

The full per-JD pipeline. `SKILL.md` is the summary; this is the detail. Source of truth
for content is `assets/master_resume.tex`. Keyword palette is `references/keywords.md`.
Honesty audit is `references/honesty-rules.md`.

## The project pool (closed set of 5)

| Project | Dates | Lead bullet is about |
|---|---|---|
| Local Lens | Dec 2025 – Present | Chrome OCR extension, 290+ installs |
| LinkedIn Outreach | May 2026 – Present | Claude Code outreach skill, –60% drafting time |
| P4-stack | Oct 2025 – Dec 2025 | Stacked-diff CLI for Perforce |
| PR Pilot | Sep 2025 – Oct 2025 | GitHub Action PR review via Gemini |
| Autoly | May 2025 – Jul 2025 | 8-step form-digitizing web app |

Plus two experiences, **both always kept**: Interested Opportunity Engine (Nov 2025) and
FPT Telecom (May–Jul 2025). The pool is closed — **never invent a project**. If a JD demands a
domain none of these covers (e.g. heavy FPGA), say so in the run summary's `uncovered must-haves`.

## Step 1 — JD analysis

Read `jobDescription/<company>.txt` and form (internally):
```
role_type:     SWE | ML | Data | DevOps | Frontend | mixed
top_keywords:  [ranked by JD frequency + emphasis]
must_haves:    [requirements that gate the application]
nice_to_haves: [desirable but optional]
anti_signals:  [things the JD warns away from, if any]
```

## Step 2 — Select projects (project-granular)

- Score each of the 5 pool projects by JD-keyword matches in its `% [tag]` lines and bullet text.
- Keep the **top few that fill the page — usually 3**. The fit checker (Step 6) decides how many
  actually fit; start with your best 3 and let the loop add/drop.
- **Tiebreak:** prefer the project with the stronger numbers (installs, latency, users, accuracy).
- **Selection is project-granular:** when a project is in, keep its bullets together. You may
  add or drop a single marginal bullet only to hit the fill target — don't cherry-pick a project
  down to one bullet.

### Ordering (strict chronological, most recent first)
- Sort by **end date**; an ongoing "Present" beats any past end date.
- Local Lens and LinkedIn Outreach are both "Present" — break that tie by JD relevance
  (more JD-relevant first).
- Experiences: **IOE above FPT** (Nov 2025 vs May–Jul 2025), always both present.

## Step 3 — Compose `output/<company>/resume.tex`

Copy these **verbatim** from `assets/master_resume.tex`:
- Preamble + custom commands + `\begin{document}`.
- Heading (name + contacts).
- Education — including "GPA: 3.9/4.0, Honors Program" (real) and the ICPC "1st in Division 2" bullet.

Then embed the chosen content:

**Experiences (both, IOE first).** Keep bullets faithful; light keyword reword only.
- IOE: Khoa owned the **gateway**, not the pre-existing Mastra agent — never claim the agent.
- FPT: never reinstate the 86%→93% XGBoost jump (a teammate's work).

**Projects (chronological).** For each:
- The **lead bullet** (first `\resumeItem` in that project's master block) always leads and is
  always kept; a light JD-vocabulary reword is fine. Order the rest relevance-first.
- **PR Pilot** has a long-form and a short-form cold-email bullet — use **one**, never both
  (long form for entrepreneurship/user-research JDs, short form for ATS-keyword JDs).
- **Tech-stack `\emph{}` line:** reorder JD-relevant tech first, prune irrelevant items, and you
  may add a tech that actually appears in a kept bullet (e.g. add `AWS` when a kept Local Lens
  bullet mentions S3 + CloudFront).
- **No bold or other in-bullet emphasis.** Hierarchy stays at section/project level.

**What "light reword" means.** Swap a verb to the JD's verb; reframe in JD vocabulary when the
underlying mechanic still holds (`Random Forest` → `classification model` if the JD says
"classification"); insert an exact JD keyword where it fits. **Not** allowed: lengthening
a bullet without matching a keyword or adding meaning, restructuring it heavily, or changing 
any number/date/tech/company. When unsure a fact survives a reword, keep the original wording.

## Step 4 — Technical Skills (rebuild from `references/keywords.md`)

- Drop any skill the JD has no signal for.
- Reorder JD-relevant skills first.
- Rename / add categories to fit the JD (e.g. `Hardware`, `Backend`, `Data`, `Frontend & Browser`,
  rename `AI/ML` → `ML & Modeling`). Default 4 are not sacred.
- Add aggressively but only from the ALLOWED ledger, and only when the JD signals it. Insert
  **exact** JD keyword strings where defensible (ATS rewards verbatim matches).
- **Up to 5 category rows.** Each `\textbf{Category}{: ...}` must fit on **one** rendered line
  (~95–105 characters of content after the label). If a row wraps, prune its lowest-signal entries.

## Step 5 — Honesty audit

Run `references/honesty-rules.md` against your draft **before** saving. Fix every trigger and note
the catches in the run summary.

## Step 6 — Save, then react to the automatic fit check

Writing `output/<company>/resume.tex` fires a `PostToolUse` hook that recompiles the PDF and runs
`scripts/check_resume_fit.py`, returning a fit report as context. **You do not invoke the checker.**
Read the report's `verdict` + `fullness` and act, re-saving to re-trigger the check (cap ~3 passes,
then report the final state):

- **`UNDERFULL`** (fullness < 0.95) — add a whole JD-relevant project, or one more faithful pool
  bullet to a chosen project. Prefer a real pool bullet over padding. If all bullets for the chosen
  projects + both experiences + 5 skill rows are already in and it's *still* < 0.95, that is
  **acceptable** — stop and note it.
- **`SPILLOVER`** / a bullet tagged **`FLAG`** — its last wrapped line is ≤4 words. Lightly reword
  that bullet so the last line carries more words (a **≤4-word** dangling line *must* be fixed).
  Never delete a fact to fix wrap. `SKIP`-tagged bullets are low-confidence matches, not targets.
- **`OVERFULL`** (fullness > 1.0) / **`MULTIPAGE`** — drop the lowest-JD-scoring project (then the
  lowest bullet of the lowest project). Never drop education, header, or either experience.
- **`OK`** — done.

## Step 7 — Per-JD summary

Print the ~5-line block from `SKILL.md`. No `reasoning.md` file is written.

## Quick reference: verbatim vs. per-JD

| Section | Per-JD action |
|---|---|
| Preamble, `\begin{document}`, heading | Verbatim from master |
| Education (incl. Honors Program + ICPC) | Verbatim from master |
| Experience (IOE, FPT — both, IOE first) | Keep both; light keyword reword only |
| Projects (usually 3, chronological) | Select whole projects; light reword; pull from master |
| Technical Skills | Rebuild from keywords.md (≤5 rows) |
| `\end{document}` | Verbatim |
