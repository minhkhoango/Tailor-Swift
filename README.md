# Tailor-Swift

A personal resume-tailoring toolkit that customizes **Ngo Minh Khoa's** master resume
to specific job descriptions pulled from [Simplify](https://simplify.jobs/). For each job,
it produces a one-page, ATS-friendly tailored resume (and a matching cover letter) while
keeping every fact locked to source material.

## What it does

1. You drop a job description into `jobDescription/<Company>.txt`. These are copied straight
   from Simplify postings (requirements, responsibilities, keyword-match hints, and any
   application questions).
2. The `/tailor` agent skill reads the JD, analyzes it (role type, keywords, must-haves,
   anti-signals), and rebuilds the resume around it.
3. It picks the 3 most relevant projects from a fixed pool, heavy-rewrites the bullets into
   the JD's exact vocabulary for ATS keyword matching, rebuilds the skills section, and
   compiles a verified single-page PDF with `pdflatex`.
4. A cover letter is generated for every JD, with the closing paragraph personalized via
   light web research on the company.

The core rule: **wording can be rewritten aggressively, but facts are never invented.**
Every number, date, and technology name must trace 1:1 back to a source file.

## Layout

```
jobDescription/                 # input JDs copied from Simplify (<Company>.txt)
source/
  one_page_general.tex          # master resume (preamble + content)
  bullet_pool.tex               # per-project enriched bullets + allowed/forbidden keywords
cover_source/
  cover_letter_template.md      # cover-letter voice anchor
example_output/                 # generated, one folder per company
  <Company>/
    resume.tex                  # tailored resume source
    Khoa_Ngo_resume.pdf         # compiled, verified one page
    experience.txt              # plain-text experience section (for application forms)
    cover_letter.md             # cover letter (when applicable)
rebuild_resumes.py              # recompile every example_output/*/resume.tex
rebuild_cover_letter.py         # compile a company's cover_letter.md to PDF
check_resume_fit.py             # deterministic page-fullness + bullet-spillover checker
test_check_resume_fit.py        # unit tests for the checker
requirements.txt                # pip deps (pdfplumber) for the checker
.claude/skills/tailor/          # the /tailor agent skill definition
```

## Usage

The pipeline runs inside [Claude Code](https://claude.com/claude-code) via the `tailor`
skill:

- `/tailor` — process every JD in `jobDescription/` that does not already have output.
- `/tailor <Company>` — (re)process specific JD file(s), overwriting existing output.
- `/tailor --force` — reprocess all JDs.

To recompile PDFs after manual edits:

```bash
python rebuild_resumes.py              # all resumes
python rebuild_cover_letter.py <Company>   # one cover letter
```

To check that a compiled resume is reasonably full (85–95% of the page) and has no bullet
whose last wrapped line dangles ≤4 words (run automatically inside `/tailor`):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # one-time
.venv/bin/python check_resume_fit.py <Company>    # or --all
.venv/bin/python -m unittest test_check_resume_fit   # run the tests
```

## Requirements

- `pdflatex` (TeX Live: `texlive-latex-recommended texlive-fonts-recommended texlive-latex-extra`)
- `pandoc` (for cover-letter PDF rendering)
- Python 3, plus `pdfplumber` for `check_resume_fit.py` (`pip install -r requirements.txt`)

The full per-step pipeline and the honesty rules live in
`.claude/skills/tailor/SKILL.md`.
