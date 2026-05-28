---
name: tailor
description: Tailor Khoa's master resume into 1-page company-specific resumes (and optionally a cover letter) from .txt job descriptions. Use when the user runs /tailor (with or without company names) or says "tailor the new JDs", "tailor for <company>". Reads jobDescription/*.txt, runs a structured JD analysis, picks 3 projects from a fixed pool, heavy-rewrites bullets in JD vocabulary with facts locked, rebuilds the skills section, compiles with pdflatex, verifies single-page output, and writes a cover letter only when the JD asks for one. Never invents facts.
---

# Resume Tailor

A personal resume-tailoring tool. Turns each `.txt` job description in `jobDescription/` into a 1-page tailored resume — and, when the JD asks for one, a matching cover letter. Strict honesty rules: every metric, date, and tech name must trace to source files. Heavy rewriting of wording is allowed; invention is not.

## Commands

- `/tailor` — process every `.txt` in `jobDescription/` that does NOT yet have a matching `example_output/<stem>/` directory. Idempotent: re-running skips already-built companies.
- `/tailor <company> [<company2> ...]` — process only the named JD file(s), overwriting any existing output.
- `/tailor --force` — process all JDs, overwriting any existing outputs.

Triggers on natural-language phrases too: "tailor the new JDs", "tailor for nvidia", "redo the salesforce resume".
/CLAU
## Workspace layout

```
Resume/
  jobDescription/
    <company>.txt              # input JDs
  source/
    one_page_general.tex       # master resume (preamble + content)
    bullet_pool.tex            # enriched per-project bullets + ALLOWED/FORBIDDEN keyword list
  cover_source/
    cover_letter_template.md   # cover-letter voice anchor (use only if JD asks for one)
  example_output/
    <company>/
      resume.tex               # tailored output (you write this)
      Khoa_Ngo_resume.pdf      # compiled, verified 1 page
      cover_letter.md          # optional, only when JD requests
```

## Project pool (closed set of 5)

| Order | Project | Date | Bullets in |
|---|---|---|---|
| 1 (tie) | Local Lens | Dec 2025 -- Present | bullet_pool.tex |
| 1 (tie) | LinkedIn Outreach | May 2026 -- Present | bullet_pool.tex |
| 3 | P4-stack | Oct 2025 -- Dec 2025 | bullet_pool.tex |
| 4 | PR Pilot | Sep 2025 -- Oct 2025 | bullet_pool.tex |
| 5 | Autoly | May 2025 -- Jul 2025 | bullet_pool.tex |

Pool is closed. **Do not invent new projects.** If a JD strongly demands a domain none of these covers (e.g., hardware/FPGA), flag it in the per-JD report under "unaddressed JD signals" so Khoa can decide.

---

## Per-JD pipeline

For each JD to process, do the following IN ORDER.

### Step 1 — JD analysis (structured)

Read `jobDescription/<company>.txt` and produce this internal structure:

```
role_type:       SWE | ML | Data | DevOps | Frontend | mixed
top_keywords:    [list, ranked by JD frequency + emphasis]
must_haves:      [list — requirements that gate the application]
nice_to_haves:   [list — desirable but optional]
anti_signals:    [list — things the JD warns away from, if any]
cover_letter_required: true | false
```

`cover_letter_required` is `true` only when the JD explicitly asks: phrases like "cover letter required", "please include a cover letter", "tell us why", "include a 'why us' statement". Default `false`.

Surface this analysis verbatim in the per-JD report (Step 11) so Khoa can audit your reasoning.

### Step 2 — Project selection (exactly 3)

Score each of the 5 pool projects against the JD analysis. Counting JD-keyword matches in tech-stack tags and bullet content is the primary signal. Pick the top 3.

**Tiebreak**: when two projects score similarly, **prefer the project with stronger numbers** (installs, latency, accuracy, user counts). Recency / tech diversity are secondary.

**No archetype defaults.** Trust the JD analysis each time. (The old rules like "keep Local Lens unless purely backend" are removed.)

### Step 3 — Project ordering across the section

Strict chronological, most recent first. Use end date; ongoing "Present" beats any past end date.

Local Lens vs. LinkedIn Outreach are both "Present" — tiebreak by JD relevance (more JD-relevant first, then the other).

### Step 4 — Project body composition (heavy rewrite, facts locked)

For each chosen project:

**a. Pick bullets from the pool.** Read `bullet_pool.tex` for that project. Pick 1–4 bullets that most directly map to JD keywords. **Variable bullet count is allowed** — a project might show 2 strong bullets; another might show 4.

**b. Reorder bullets relevance-first.** The most JD-relevant bullet leads.

**c. Heavy-rewrite each kept bullet.** You may:
- Swap verbs ("automates" → "orchestrates" if JD uses "orchestration").
- Reframe in JD vocabulary ("Random Forest" → "classification model" if JD says "classification"; "OCR pipeline" → "CV inference pipeline" if JD says "computer vision"). Honest as long as the underlying mechanic holds.
- Restructure the sentence shape.
- Insert **EXACT keyword matches** from the JD wherever defensible — ATS systems are dumb and reward verbatim string matches.

**Style is locked**: `action verb + what it is + measurable result + rest`. Every bullet follows this shape.

**Fact lock**: every number, percentage, date, install count, accuracy figure, latency, tech name, company name must trace 1:1 to a source `.tex` file. No new numbers. No new tech names not present in the project's repo or interview.

**d. Tech-stack `\emph{...}` line.** Reorder JD-relevant tech first. Prune irrelevant items. Add a tech that appears inside a kept bullet if it strengthens the line (e.g., add `AWS` to Local Lens's stack line for a cloud JD because a bullet mentions S3 + CloudFront).

**e. No bold or other in-bullet emphasis.** Keep visual hierarchy at the section/project level only.

### Step 5 — Experience body composition

Same heavy-rewrite-facts-locked rules as projects. **Both IOE and FPT Telecom always kept** — never drop either.

For IOE: bullets must not claim credit for the Mastra agent itself (it pre-existed). Khoa owned the **gateway**, not the agent.

For FPT Telecom: the bullet pool intentionally **does not include** the 86%→93% XGBoost claim (that was the other intern's work). Do not reinstate it under any framing.

### Step 6 — Education

Verbatim. Don't touch the coursework line. The ICPC bullet now includes "1st in Division 2" — keep it.

### Step 7 — Technical Skills (heavy rebuild)

Start from the master skills block (lines 189–198 of `one_page_general.tex`). Then:

**a. Drop irrelevant skills.** If the JD has no signal touching a skill, remove it. (E.g., drop `PaddleOCR` for a pure backend infra JD.)

**b. Rename or replace categories per JD.** The default 4 (Languages, AI/ML, Frameworks & Libraries, Developer Tools) are not sacred. For a distributed-systems JD, add a "Distributed Systems" or "Backend" category. For a frontend JD, add "Frontend & Browser". For an ML JD, rename "AI/ML" to "ML & Modeling".

**c. Add aggressively from defensible sources.** Mine bullets + JD generously. Honestly defensible additions include:
- "Machine Learning", "Deep Learning", "Neural Networks" (Coursera DL Specialization + CS50 AI completed; XGBoost / Random Forest / PyTorch in work).
- "REST APIs", "OOP", "Git workflows", "Type Hints", "Error Handling", "Retry Logic".
- "Docker", "Containerization", "CI/CD", "DevOps" (PR Pilot's Docker + GitHub Actions).
- "WebGPU", "WASM", "Manifest V3", "Browser Extensions", "Service Workers", "Web Workers" (Local Lens).
- "Information Retrieval", "NLP", "LLM", "Prompt Engineering", "AI Agent" (LinkedIn Outreach + PR Pilot).
- "Real-time Systems", "Audio Processing", "Telephony", "WebSocket", "Streaming" (IOE / Mastra Voice Gateway).
- "SQL", "SQLite" (Autoly — SQLite + sqlite3 + auth).
- "Bash", "Shell Scripting" (PR Pilot's entrypoint.sh + Makefiles).
- "JavaScript", "HTML/CSS" (Local Lens UI — distinct from TypeScript).
- "Pandas", "NumPy", "Matplotlib", "Seaborn", "Jupyter" (FPT data work).
- "Svelte" (metriclens), "Node.js" (Local Lens testing), "FPGA" (college).

**d. EXACT JD keyword matches.** If the JD says "data analysis" verbatim, list "Data Analysis". If it says "ranking systems", you can list "Ranked Retrieval" (defensible via LinkedIn Outreach) — but **not** "Ranking Systems" if the underlying work isn't a ranking system.

**e. One line per category — hard limit.** Each `\textbf{Category}{: ...}` line must fit on a single rendered line. At 11pt with this template's font, the text column holds roughly 95–105 characters of content after the category label. If a line wraps, **prune the lowest-JD-signal entries until it fits.** Don't trade page count for skill density.

### Step 8 — Honesty audit (runs BEFORE writing)

Reject your own draft if any of these appear:

1. A number, percentage, date, or tech name without a trace to a source `.tex` file or to the LinkedIn-Outreach repo material.
2. **"RAG"** anywhere. LinkedIn Outreach uses rank/tier-based retrieval with no embeddings — calling it RAG is misleading.
3. **"XGBoost ... 93%"** in any form. That was the teammate's work.
4. **"Honors"** or **"Honors Program"**.
5. **"Large-scale"**, **"production-grade"**, **"high-throughput"**. None of Khoa's work operates at that scale.
6. **Generic resume buzzwords**: spearheaded, leveraged, owned, world-class, 10x, best-in-class, synergize.
7. **"$5,000"** for the FPT capital validation — must be "$4,000".
8. **Tech Khoa hasn't touched**: Java, Kubernetes, Rust, Go, .NET, Angular, Vue, Solana, Spring (only if a defensible source emerges).
9. **"Agentic"** unless the JD itself uses the term. If JD uses it, you may use it.

If the audit fails: fix and re-audit. Surface every triggered rule in the per-JD report under "honesty audit corrections".

### Step 9 — Write the `.tex` file

Create `example_output/<company>/` (use `mkdir -p`). Write the composed file to `example_output/<company>/resume.tex`. The file must:

- Copy `one_page_general.tex` lines 1–120 (preamble + heading) verbatim.
- Copy the EDUCATION section (lines 122–135) verbatim, with the source-side updated ICPC bullet (already includes "1st in Division 2").
- Embed the heavy-rewritten EXPERIENCE section.
- Embed the heavy-rewritten PROJECTS section (3 projects).
- Embed the rebuilt TECHNICAL SKILLS section.
- End with `\end{document}` and a trailing newline.

### Step 9b — Write `experience.txt` (plain-text mirror of EXPERIENCE)

Khoa often pastes the experience section into job-application forms. Alongside `resume.tex`, write `example_output/<company>/experience.txt` derived from the same composed EXPERIENCE section. Do this **before** Step 10 — that way the file lands even if pdflatex later fails.

Format (matches `experience.txt.example` at the repo root):

For each `\resumeSubheading` block, in source order:

1. **Company line**: the third brace argument of `\resumeSubheading` (the company string), with any trailing parenthetical qualifier stripped — drop ` (Early-Stage)`, ` (Remote)`, etc. Examples: `Interested Opportunity Engine (Early-Stage)` → `Interested Opportunity Engine`; `FPT Telecom` → `FPT Telecom`.
2. **One blank line.**
3. **Bullets**: one line per `\resumeItem{...}`, prefixed with `•` (U+2022, no space after the bullet). Unescape LaTeX: `\%` → `%`, `\$` → `$`, `\&` → `&`, `\#` → `#`, `\_` → `_`. Otherwise take the contents verbatim — do **not** include `\resumeItem`, braces, job titles, dates, or locations.
4. **Two blank lines** before the next entry.

End the file with a single trailing newline. Overwrite on re-run (same idempotency as `resume.tex`).

### Step 10 — Compile and 1-page verify

Check `pdflatex` is available:

```bash
command -v pdflatex || echo "pdflatex MISSING — install: sudo apt update && sudo apt install -y texlive-latex-recommended texlive-fonts-recommended texlive-latex-extra"
```

If missing, stop and ask Khoa to install.

Compile:

```bash
cd example_output/<company> && pdflatex -interaction=nonstopmode -jobname=Khoa_Ngo_resume resume.tex
```

Check page count:

```bash
pdfinfo example_output/<company>/Khoa_Ngo_resume.pdf | grep '^Pages:'
```

If `Pages: 1` — run the **tight-line polish** below, then clean: `rm -f example_output/<company>/Khoa_Ngo_resume.{aux,log,out,fls,fdb_latexmk}`.

**Tight-line polish (only when `Pages: 1`):**

Open the compiled PDF (or inspect the `.log` overfull/underfull markers) and scan every project/experience bullet. If a bullet wraps such that the last line of that bullet contains **4 or fewer words**, attempt to trim:

- **Trim filler only.** Drop connective words ("that", "which", "in order to", "various", "really", "simply"), redundant articles, and weak qualifiers. Tighten verb phrases ("was responsible for designing" → "designed").
- **Preserve every verbatim JD keyword** that the bullet was tailored to hit — those are the whole point of customization. If trimming a word would remove a JD keyword string, do not trim that word.
- **Preserve every locked fact**: numbers, percentages, dates, tech names, company names — same rules as the Step 8 honesty audit.
- After trimming, recompile and re-check. If the spillover survives, **leave the bullet as-is** — do not reword aggressively, do not swap bullets from the pool, do not drop the bullet. A 4-word spillover is better than a fact mutation or a coverage loss.
- Max 2 trim attempts per bullet. Then move on.

Surface every trim in the per-JD report (Step 12) under the `tight-line trims:` line.

If `Pages: 2+` — prune loop, max 3 iterations:

- **Iteration 1**: drop the JD-lowest-scoring bullet from the JD-lowest-scoring project. Recompile.
- **Iteration 2**: drop the entire JD-lowest-scoring project (leaving 2). Recompile. Re-verify the remaining 2 are still chronological, most recent first.
- **Iteration 3**: drop the JD-lowest-scoring bullet from the now-lowest-scoring project. Recompile.
- After 3 failed iterations: stop, report the overflow, leave the `.tex` for Khoa.

Never drop Education, Header, or either Experience entry during pruning.

### Step 11 — Cover letter (conditional)

If Step 1 set `cover_letter_required: true`:

1. Read `cover_source/cover_letter_template.md` as voice anchor. The template has the self-deprecating, specific, narrative tone to preserve. **Do not import its honesty errors** — the template was already corrected, but stay alert.
2. Compose ~250 words across 3 short paragraphs:
   - **Opening**: 1-line identity + hook. Template's pattern is "I'm applying for the [role] internship. I'm a junior CompE at FSU (3.9 GPA, ICPC Gold '24, 1st in Div 2 NA South), but the things I actually want to tell you about are below."
   - **Body**: ONE project paragraph, mapped to the JD. Pick the project with the strongest JD fit (often P1 from the resume). Tell its story in voice, not in resume-bullet shape.
   - **Closing**: "Why this company". Apply the template's own rule: *if you can't write this honestly, cut the paragraph entirely — a missing "why us" reads better than a generic one.* If Khoa hasn't given you a specific reason to want this company, write a placeholder line and flag it in the report for Khoa to fill in.
3. Sign as "Khoa Ngo".
4. Run the same honesty audit (Step 8). Same rules apply: no XGBoost-93% credit, no Honors, no $5,000, no large-scale, no RAG, no buzzwords.
5. Write to `example_output/<company>/cover_letter.md`.

If `cover_letter_required: false`: skip Step 11 entirely. Note in the report: `cover_letter: not required`.

### Step 12 — Per-JD report

Print one block per JD:

```
<company>:
  JD analysis:
    role_type: <...>
    top_keywords: <...>
    must_haves: <...>
    anti_signals: <...>
    cover_letter_required: <bool>
  projects: <P1>, <P2>, <P3>   (chronological, most recent first)
  project bullet selections (per project): <which pool bullets were used + why>
  bullets dropped during pruning: <list> | none
  tight-line trims: <bullet → words removed> | none
  tech-stack \emph{} changes (per project): <reorders / prunes / additions>
  experience reframes:
    IOE: <list of wording changes>
    FPT Telecom: <list of wording changes>
  skills added (with justification): <list>
  skills dropped (with reason): <list>
  skills considered but skipped: <list with reason — usually "no source evidence">
  honesty audit corrections: <triggers caught and fixed> | none
  JD coverage:
    addressed: <keyword → location>
    unaddressed: <JD keywords with no defensible home in the resume>
  page count: 1
  pdf: example_output/<company>/Khoa_Ngo_resume.pdf
  experience_txt: example_output/<company>/experience.txt
  cover_letter: example_output/<company>/cover_letter.md | not required
```

### Step 13 — Final summary

After all JDs are processed, list one line per JD with its status. Flag any JDs that overflowed past 3 prune attempts and any with non-empty "unaddressed" coverage gaps.

---

## Honesty rules (read these every run)

1. **No invented metrics.** Every number traces 1:1 to a source `.tex` file or to the project's repo.
2. **No invented technologies.** Every tech name on the page exists in source.
3. **No invented dates or companies.** Copy date ranges verbatim.
4. **No relabeling the project's category.** Random Forest classifier is not a "ranking model" just because the JD says ranking. Reframing in JD vocabulary stops at honest reframings.
5. **No implying scale you didn't operate at.** 290 installs is not "large-scale".
6. **No "RAG"** for LinkedIn Outreach. Use "ranked retrieval" / "tier-based few-shot retrieval" / "information retrieval".
9. **No generic buzzwords**: spearheaded, leveraged, owned, world-class, 10x, best-in-class, synergize.
10. **Default to less, not more.** When uncertain whether a fact survives a rewording, keep the original wording.
11. **Skills additions: when in doubt, skip and note in the report.**

---

## Quick reference: what's verbatim vs. what changes per JD

| Section | Per-JD action |
|---|---|
| Preamble (lines 1–105 of one_page_general.tex) | Verbatim |
| `\begin{document}` | Verbatim |
| Heading (Khoa Ngo + contacts) | Verbatim |
| Education (incl. ICPC bullet) | Verbatim from source |
| Experience (both entries, always kept) | Heavy rewrite per Step 5 |
| Projects (3, chronological) | Heavy rewrite per Step 4; pull bullets from `bullet_pool.tex` |
| Technical Skills | Heavy rebuild per Step 7 |
| `\end{document}` | Verbatim |
| `experience.txt` | Plain-text mirror of EXPERIENCE section, written alongside `resume.tex` per Step 9b |
| Cover letter | Only if Step 1's `cover_letter_required` is true |

---

## VSCode integration (already configured)

`.vscode/settings.json` in this repo has LaTeX Workshop set to rebuild `Khoa_Ngo_resume.pdf` on every save of any `.tex` in the workspace. Once `/tailor` writes a `resume.tex`, Khoa can edit it directly and ctrl+s refreshes the PDF — no need to re-run `/tailor` for tweaks.
