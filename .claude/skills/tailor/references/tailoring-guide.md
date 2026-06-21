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

- Judge each pool project against the JD's ranked keywords (compare its bullets + stack against
  `top_keywords`/`must_haves` from Step 1). The pick is yours.
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

## Step 3 — Write `output/<company>/resume.slots.json` (not the `.tex`)

You **do not** hand-write the resume `.tex`. You write a small slot file; `scripts/assemble_resume.py`
copies the preamble/heading/Education verbatim from `assets/master_resume.tex`, pulls the bullets
you reference, and emits `output/<company>/resume.tex` for you. **Edit the slot, not the tex** —
a direct `.tex` edit is overwritten on the next assemble.

### Slot schema
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
- **`key`** — the `% @key:` of a block in `master_resume.tex` (`ioe`, `fpt`, `local_lens`,
  `linkedin_outreach`, `p4_stack`, `pr_pilot`, `autoly`).
- **`{"id": n}`** — pull `\resumeItem` **#n** of that block **verbatim** (1-based, master order).
  Prefer ids: byte-identical bullets are honesty-safe by construction.
- **`{"text": "..."}`** — a lightly reworded bullet (see "light reword" below). Use only when an
  id won't carry the exact JD keyword you need.
- **`emph`** (projects only) — replaces the heading's first `\emph{}` (the tech-stack line).
  Keep the **3 most JD-relevant** items, most-relevant first; drop the rest (a tech that appears
  in a kept bullet is a good pick). **Hard cap: 3 items** — the assembler errors on 4+, whether
  from your `emph` or a master default. Omit `emph` to keep the master default (all are ≤3).
  Dates are **never** in the slot — always taken verbatim.
- **`"force": true`** (top-level, optional) — only for a deliberate **re-tailor** of a company that
  already has an AI baseline in `dataset/<co>/`. Without it the assembler refuses, so it can't
  silently overwrite hand-edits; with it, the prior pair is archived to `dataset/<co>/.prev-<ts>/`.

**Experiences (both, IOE first):** keep both. IOE — Khoa owned the **gateway**, not the
pre-existing Mastra agent. FPT — never reinstate the 86%→93% XGBoost jump (a teammate's).

**Projects (chronological):** the **lead bullet** (id 1) always leads and is always kept.
**PR Pilot** has a long-form (id 2) and short-form (id 3) cold-email bullet — list **one**, never
both (long for entrepreneurship/user-research JDs, short for ATS-keyword JDs; the linter flags
both). **No bold / in-bullet emphasis.**

**What "light reword" means** (for `{"text": ...}`). Swap a verb to the JD's verb; reframe in JD
vocabulary when the underlying mechanic still holds (`Random Forest` → `classification model` if
the JD says "classification"); insert an exact JD keyword where it fits. **Not** allowed:
lengthening without adding meaning, restructuring heavily, or changing any number/date/tech/company.
A reword stays at roughly its source length — the assembler **rejects** a `text` that runs more
than **4 words longer** than the master bullet it rewords (that's filler padding, not a reword).
When unsure a fact survives a reword, use the verbatim id instead.

## Step 4 — Technical Skills (the `skills` rows in the slot)

The `"skills"` array is a list of `[category, content]` rows, rebuilt per JD from
`references/keywords.md`:
- Drop any skill the JD has no signal for; reorder JD-relevant skills first.
- Rename / add categories to fit the JD (e.g. `Hardware`, `Backend`, `Data`, `Frontend & Browser`,
  rename `AI/ML` → `ML & Modeling`). Default 4 are not sacred.
- Add aggressively but only from the ALLOWED ledger, and only when the JD signals it. Insert
  **exact** JD keyword strings where defensible (ATS rewards verbatim matches).
- **Up to 5 rows** (the assembler errors above 5). Each row must fit on **one** rendered line
  (~95–105 characters after the label). If the fit check tags a row `WRAP`, prune its lowest-signal
  entries. Escape `&` as `\\&` in JSON (e.g. `"Frameworks \\& Libraries"`).

## Step 5 — Honesty audit

Run `references/honesty-rules.md` against your draft **before** saving. Fix every trigger and note
the catches in the run summary.

## Step 6 — Save the slot, then react to the automatic fit + honesty check

Writing `output/<company>/resume.slots.json` fires a `PostToolUse` hook that runs the whole chain
for you: `assemble_resume.py` (→ `resume.tex`) → `build_resume.py` (→ PDF) →
`scripts/check_resume_fit.py` (fit + skill-row WRAP) → `scripts/lint_honesty.py` (deterministic
honesty flags). It returns the combined report as context. **You do not invoke any of these.**
Read the report's `verdict` + `fullness` + `honesty:` line and act by **editing the slot file**
and re-saving it (cap ~3 passes, then report the final state):

- **`UNDERFULL`** (fullness < 0.95) — add a whole JD-relevant project, or one more faithful pool
  bullet to a chosen project. **Never lengthen a bullet with filler to grow its height** — the
  assembler rejects a `text` reword that runs >4 words past its source. The only honest way to fill
  the page is *more pool content*, never *padded content*. If all bullets for the chosen projects +
  both experiences + 5 skill rows are already in and it's *still* < 0.95, that is **acceptable** —
  stop and note it.
- **`SPILLOVER`** / a bullet tagged **`FLAG`** — its last wrapped line is ≤4 words. Lightly reword
  that bullet so the last line carries more words (a **≤4-word** dangling line *must* be fixed).
  Never delete a fact to fix wrap. `SKIP`-tagged bullets are low-confidence matches, not targets.
- **`OVERFULL`** (fullness > 1.0) / **`MULTIPAGE`** — drop the lowest-JD-scoring project (then the
  lowest bullet of the lowest project). Never drop education, header, or either experience.
- **`WRAP`** on a skill row — trim that row's lowest-signal entries until it's one line.
- **`honesty: FLAGS [...]`** — fix each one (it's advisory but it's catching a real slip: a
  forbidden token, an untraceable number, both PR-Pilot bullets, or "agentic" with no JD support).
- **`OK`** + `honesty: clean` — done.

## Step 7 — Per-JD summary

Print the ~5-line block from `SKILL.md`. No `reasoning.md` file is written.

## Quick reference: verbatim vs. per-JD (all driven by the slot file)

| Section | How the assembler handles it / what you put in the slot |
|---|---|
| Preamble, `\begin{document}`, heading | Verbatim from master (automatic; not in the slot) |
| Education (incl. Honors Program + ICPC) | Verbatim from master (automatic; not in the slot) |
| Experience (IOE, FPT — both, IOE first) | `experiences`: both keys; bullets by `id` (verbatim) or `text` (light reword) |
| Projects (usually 3, chronological) | `projects`: whole projects by key; `emph` for the stack line; bullets by `id`/`text` |
| Technical Skills | `skills`: up to 5 `[category, content]` rows, rebuilt from keywords.md |
| `\end{document}` | Verbatim (automatic) |
