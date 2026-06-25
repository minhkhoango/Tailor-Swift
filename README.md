# Tailor Swift

Turn a job description into a **packed, one-page, ATS-friendly resume** — tailored to the
role but with **every fact locked to source**.

It runs as a **plain Python program** (`python -m tailor`) that calls the Anthropic API
directly 1–3 times per job. No Claude Code harness in the middle — either side of the
scrape→tailor pipeline is runnable alone, and a cron can drive it later.

## The idea

You keep **one master resume** with all your projects and bullets. For each job, the tool
**picks** the most relevant pieces and *lightly* rewords them to match the job's keywords —
then packs them into exactly one full page.

The core rule: **wording barely moves, facts never move.** Every number, date, and
technology traces 1:1 back to your master resume. Nothing gets invented. Honesty is the
hard gate: if a draft can't be made honest within 3 passes, **nothing ships**.

## How you use it

1. **Get a job description in.** Drop a `.txt` into `jobDescription/`, or run `/scrape-jobs`
   to pull them automatically from a filtered [simplify.jobs](https://simplify.jobs) list.

2. **Run the program.**

   ```bash
   python -m tailor                 # tailor every JD with no output/<stem>/ yet
   python -m tailor --force         # re-tailor ALL JDs (ignore skip; for testing)
   python -m tailor why Apple*      # apply-time "why this company" blurb(s)
   python -m tailor force why A* B* # regenerate the why blurb even if present
   ```

   It reads the job, selects the best-fitting projects and bullets, assembles the LaTeX,
   compiles the PDF, checks it fills exactly one page, and runs a number-traceability
   **honesty check** — looping up to 3 passes — then ships `output/<stem>/resume.slots.json`
   + `Khoa_Ngo_resume.pdf`.

3. **`why` is separate and apply-time.** The scraper pulls many JDs; you apply to few. When
   you click "Apply", `python -m tailor why <glob>` writes a short, honest
   `output/<stem>/why_company.md` (one web-search call, verifiable numbers only) to paste
   into the application's "why us" box. It tailors the resume first if it's missing.

Everything after the model's selection step is deterministic: assemble, compile, fit-check,
honesty-check. No guessing about whether the page is full or a number is real — it's checked.

### Ergonomic launch (WSL / bash)

One line in `~/.bashrc` so you can run `tailor …` from anywhere:

```bash
tailor(){ ( cd ~/Breakthrough/Resume && .venv/bin/python -m tailor "$@"; ) }
```

## Where things live

```
jobDescription/<stem>.txt   the jobs you want to apply to (input, gitignored)
output/<stem>/              shipped resume.slots.json + Khoa_Ngo_resume.pdf (+ why_company.md)
dataset/<stem>/             frozen AI-baseline / human-final slot pairs (benchmark)
.tailor_cache/<stem>/       scratch for in-flight passes (gitignored; kept on abort)
logs/tailor-<ts>.jsonl      one JSON event per action per run (gitignored)
tailor/                     the program — orchestrator + llm + core/ (assemble, fit, compile, …)
assets/master_resume.tex    your single source of truth (the pool everything is selected from)
references/                 honesty-rules.md + keywords.md (loaded into the model's prompt)
build_resume.py             standalone helper to rebuild resume PDFs by hand
```

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...      # the program reads the key from the env
```

You also need a LaTeX toolchain (`pdflatex`) installed for PDF compilation.

## Tests

```bash
pytest -m "not inspect"   # fast hermetic suite (no network, no LaTeX) + core fixtures
pytest -s -m inspect      # tier-3 inspect dump: real chain on slot files, eyeball the output
```

The root `conftest.py` trip-wires the real Anthropic client, so no test can touch the
metered API by accident.

---

*The one file that matters most is `assets/master_resume.tex` — that's the single pool every
tailored resume is selected from. Edit your real experience there.*
