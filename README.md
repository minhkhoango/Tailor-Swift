# Tailor

A personal resume-tailoring toolkit that turns a job description into a **packed one-page,
ATS-friendly resume** (and, on request, a matching cover letter) — while keeping every fact
locked to source.

## How it works

1. Drop a job description into `jobDescription/<Company>.txt` — by hand, or auto-scrape a
   filtered [simplify.jobs](https://simplify.jobs) list with **`/scrape-jobs`**, which writes
   verbatim Requirements + Responsibilities per company (see `.claude/skills/scrape-jobs/`).
2. Run the **`/tailor`** agent skill (in [Claude Code](https://claude.com/claude-code)). It reads
   the JD, **selects** the most relevant projects from one master resume, **lightly rewords** them
   for the JD's keywords (never a heavy rewrite, never shorter), rebuilds the skills section, and
   writes `output/<Company>/resume.tex`.
3. Saving that `.tex` fires a **save-hook** that compiles the PDF and runs a deterministic
   fit checker; Claude packs the page to 95–100% based on its report.
4. With `--cover`, it also writes `output/<Company>/cover_letter.tex` (Jake-style LaTeX,
   closing personalized via light web research).

The core rule: **wording barely moves, facts never move.** Every number, date, and technology
traces 1:1 back to source. The honesty audit lives in `.claude/skills/tailor/references/`.

## Layout

```
jobDescription/                  input JDs, <Company>.txt
output/<Company>/                generated, one folder per company
  resume.tex                     tailored resume source (1 page)
  Khoa_Ngo_resume.pdf            compiled, verified one page
  cover_letter.tex               only when --cover was used
  Khoa_Ngo_cover_letter.pdf
build_resume.py                  compile output/*/resume.tex -> PDF
build_cover_letter.py            compile output/*/cover_letter.tex -> PDF
requirements.txt                 pip deps (pdfplumber) for the fit checker
pyrightconfig.json               Pyright strict mode for the .py scripts
.claude/skills/tailor/
  SKILL.md                       the /tailor skill (commands + pipeline overview)
  assets/master_resume.tex       THE source of truth — every project + every bullet
  assets/cover_letter.tex        Jake-style cover-letter template
  assets/cover_letter_voice.md   cover-letter voice anchor
  references/                    tailoring-guide, honesty-rules, keywords, cover-letter
  scripts/check_resume_fit.py    deterministic page-fullness + orphan-line checker
  scripts/post_save_build.py     PostToolUse hook: compile + fit-check on save
```

## Usage

Inside Claude Code:

- `/tailor` — process every JD in `jobDescription/` without output yet.
- `/tailor <prefix>` — (re)process specific JD(s); case-insensitive prefix match.
- `/tailor --cover <prefix>` — also write a cover letter.
- `/tailor --force` — reprocess everything.

To recompile PDFs after manual `.tex` edits (no argument = all; argument is a case-insensitive
**prefix**, so `A` builds every company starting with "A"):

```bash
python3 build_resume.py            # all resumes
python3 build_resume.py Stash      # just Stash
python3 build_cover_letter.py A    # every cover letter for companies starting with "A"
```

To run the fit checker by hand (it normally runs automatically via the save-hook):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # one-time
.venv/bin/python .claude/skills/tailor/scripts/check_resume_fit.py --all
```

## The save-hook

`.claude/settings.json` (or `settings.local.json`) wires a `PostToolUse` hook to
`scripts/post_save_build.py`: whenever Claude writes `output/<Company>/resume.tex` (or
`cover_letter.tex`), the PDF is recompiled and the resume is fit-checked, with the verdict fed
back automatically. Open `/hooks` once (or restart) after first install to activate it.
