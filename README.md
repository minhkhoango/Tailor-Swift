# Tailor Swift

Turn a job description into a **packed, one-page, ATS-friendly resume** — tailored to the
role but with **every fact locked to source**. Optionally writes a matching cover letter too.

The whole thing runs inside [Claude Code](https://claude.com/claude-code) as a skill.

## The idea

You keep **one master resume** with all your projects and bullets. For each job, the tool
**picks** the most relevant pieces and *lightly* rewords them to match the job's keywords —
then packs them into exactly one full page.

The core rule: **wording barely moves, facts never move.** Every number, date, and
technology traces 1:1 back to your master resume. Nothing gets invented.

## How you use it

1. **Get a job description in.** Drop a `.txt` into `jobDescription/`, or run `/scrape-jobs`
   to pull them automatically from a filtered [simplify.jobs](https://simplify.jobs) list.

2. **Run `/tailor`.** It reads the job, selects the best-fitting projects and bullets from
   your master resume, and builds a finished PDF under `output/<Company>/`.

   - `/tailor` — do every new job description
   - `/tailor <name>` — just one company (prefix match)
   - `/tailor --cover <name>` — also write a cover letter
   - `/tailor --force` — redo everything

3. **Done.** You get a compiled one-page `resume.pdf` (and `cover_letter.pdf` with `--cover`).

Everything after the selection step is automatic and deterministic: assemble the LaTeX,
compile the PDF, check it fills exactly one page, and run an **honesty check** that verifies
no fact drifted from the master. No guessing about whether the page is full or whether a
number is real — it's checked.

## Where things live

```
jobDescription/        the jobs you want to apply to (input)
output/<Company>/       the finished resume + cover letter per company
.claude/skills/tailor/  the skill itself, including assets/master_resume.tex (your source of truth)
src/                    the build scripts (compile, watch, fit-check)
```

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

You also need a LaTeX toolchain (`pdflatex`) installed for PDF compilation.

---

*The one file that matters most is `.claude/skills/tailor/assets/master_resume.tex` — that's
the single pool every tailored resume is selected from. Edit your real experience there.*
