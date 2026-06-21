# Tailor

A personal resume-tailoring toolkit that turns a job description into a **packed one-page,
ATS-friendly resume** (and, on request, a matching cover letter) — while keeping every fact
locked to source.

## How it works

1. Drop a job description into `jobDescription/<Company>.txt`.
2. Run the **`/tailor`** agent skill (in [Claude Code](https://claude.com/claude-code)). It reads
   the JD and **selects** the most relevant projects from one master resume, then writes a small
   `output/<Company>/resume.slots.json` — which experiences/projects, which bullets (by `id` for
   a verbatim copy, or `text` for a light reword), and the skills rows.
3. Saving the slot file fires a **save-hook** that runs the whole deterministic chain with no
   further LLM steps: `assemble_resume.py` builds `resume.tex` (preamble, headings, and `id`-bullets
   pulled byte-identical from the master, so verbatim bullets are honesty-safe by construction),
   then it compiles the PDF, runs the fit checker, and runs the **honesty linter**
   (`scripts/lint_honesty.py`). Claude packs the page to 95–100% based on the combined report.
4. With `--cover`, it also writes `output/<Company>/cover_letter.tex` (Jake-style LaTeX, fixed
   body with the `why this company` paragraph personalized via light web research).

The core rule: **wording barely moves, facts never move.** Every number, date, and technology
traces 1:1 back to source. The honesty audit lives in `.claude/skills/tailor/references/`.

## Layout

```
jobDescription/                  input JDs, <Company>.txt
output/<Company>/                generated, one folder per company
  resume.slots.json              the LLM's pick (keys + bullet ids/rewords + skills)
  resume.tex                     assembled from the slot file (1 page)
  Khoa_Ngo_resume.pdf            compiled, verified one page
  cover_letter.tex               only when --cover was used
  Khoa_Ngo_cover_letter.pdf
dataset/<Company>/               AI baseline + human-edited finals (preference data)
build_resume.py                  compile output/*/resume.tex -> PDF
build_cover_letter.py            compile output/*/cover_letter.tex -> PDF
watch.py                         live PDF rebuild + dataset capture during human edits
requirements.txt                 pip deps (pdfplumber, watchdog)
pyrightconfig.json               Pyright strict mode for the .py scripts
.claude/skills/tailor/
  SKILL.md                       the /tailor skill (commands + pipeline overview)
  assets/master_resume.tex       THE source of truth — every project + every bullet
  assets/cover_letter.tex        Jake-style cover-letter template (fixed body)
  references/                    tailoring-guide, honesty-rules, keywords, cover-letter
  scripts/tex_util.py            shared LaTeX parsing (brace matcher, master parser)
  scripts/assemble_resume.py     slot file -> resume.tex (verbatim-by-id bullets)
  scripts/check_resume_fit.py    deterministic page-fullness + orphan-line checker
  scripts/lint_honesty.py        deterministic honesty linter (forbidden tech, number trace)
  scripts/capture_baseline.py    snapshot AI output into dataset/ before human edits
  scripts/post_save_build.py     PostToolUse hook: assemble + compile + fit + honesty
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
`scripts/post_save_build.py`: whenever Claude writes `output/<Company>/resume.slots.json`, the
resume is assembled, compiled, fit-checked, and honesty-linted, with the combined verdict fed back
automatically (a direct `resume.tex` write skips the assemble step; `cover_letter.tex` is compiled,
page-checked, and honesty-linted). Open `/hooks` once (or restart) after first install to activate it.
