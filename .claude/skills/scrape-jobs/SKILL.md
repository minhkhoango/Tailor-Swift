---
name: scrape-jobs
description: Scrape a filtered simplify.jobs list into jobDescription/<Company>.txt (verbatim Requirements + Responsibilities), ready for /tailor. Use for "/scrape-jobs", "scrape the simplify jobs", "pull the new JDs from simplify", "grab job descriptions".
---

# Scrape Jobs (simplify.jobs → jobDescription/)

Walk a **filtered** simplify.jobs list and write one `jobDescription/<Company>.txt` per job —
the verbatim **Requirements** and **Responsibilities**, in the exact format `/tailor` consumes.
This is the upstream feeder for the tailor pipeline: **scrape → `jobDescription/<Company>.txt` →
`/tailor` → `output/<Company>/resume.tex`.**

## How it works (deterministic — no LLM, no DOM scraping)
1. Opens a **headed Chromium** with a persistent profile (`.profile/`), so you log into
   simplify.jobs **once**; the session is reused on every later run.
2. Navigates to the filtered URL and **captures the page's own Typesense `multi_search`
   query** — your exact filters, and (when logged in) the `excludeApplied` exclusion.
3. **Replays that query with pagination** to collect the first `--limit` job IDs.
4. For each job, GETs `api.simplify.jobs/v2/job-posting/:id/<id>/company` and reads the
   structured `requirements` / `responsibilities` arrays.
5. Writes `jobDescription/<Company>.txt`. Same input → same file, every time.

The active filters are **printed at the start of every run** (transparency), and a machine
manifest of the run lands in `.claude/skills/scrape-jobs/last_run.json`.

## Run it
Must run **outside** the Claude sandbox (needs network + the WSLg display). From repo root:

```bash
# Default: your filtered URL, log in once, 50 jobs, honoring excludeApplied
.venv/bin/python .claude/skills/scrape-jobs/scripts/scrape_jobs.py

# Anonymous & headless (full filtered list, excludeApplied NOT personalized)
.venv/bin/python .claude/skills/scrape-jobs/scripts/scrape_jobs.py --no-login --headless

# A different filtered list / count, overwrite existing files
.venv/bin/python .claude/skills/scrape-jobs/scripts/scrape_jobs.py --url "<paste simplify URL>" --limit 100 --force
```

When the window opens, **log into simplify.jobs** — the run auto-continues once a session is
detected (or after `--login-wait` seconds, proceeding anonymously). Already logged in from a
previous run? It continues immediately.

## Flags
| flag | default | meaning |
|------|---------|---------|
| `--url <URL>` | the saved filtered URL | which simplify.jobs filtered list to scrape |
| `--limit N` | `50` | max jobs to write this run |
| `--out DIR` | `jobDescription` | output folder for `<Company>.txt` |
| `--force` | off | overwrite existing `<Company>.txt` (else skip ones from earlier runs) |
| `--no-login` | off | skip the login wait; scrape the full filtered list anonymously |
| `--login-wait S` | `150` | seconds to wait for you to log in before proceeding |
| `--headless` | off | no window (only safe once already logged in, or with `--no-login`) |
| `--discover` | off | dump page/API structure to `.debug/` and exit (debugging only) |

## Output format (matches existing JDs)
```
Requirements
<one requirement per line>
Responsibilities
<one responsibility per line>
```
- One file per company: `Tesla.txt`. Multiple roles at the same company in one run →
  `Tesla.txt`, `Tesla (2).txt`, …
- If a job has no parsed lists, the file falls back to a `Description` section (stripped HTML).

## Notes
- **`excludeApplied`** only takes effect when logged in (simplify computes it server-side).
  The run prints whether it was applied. Anonymous runs return the full filtered set.
- **Order** follows simplify's `shuffle_key` sort, so "first N" is simplify's own ordering.
- `.profile/` (login) and `.debug/` (dumps) are gitignored; never commit them.
- Re-running is idempotent: existing `<Company>.txt` files are skipped unless `--force`.

## Files
```
jobDescription/<Company>.txt            output, one per job (also /tailor's input)
.claude/skills/scrape-jobs/
  SKILL.md                              this file
  scripts/scrape_jobs.py                the scraper (Playwright + simplify JSON APIs)
  .profile/                             persistent browser login (gitignored)
  .debug/                               --discover dumps (gitignored)
  last_run.json                         manifest of the most recent run (filters + files)
```

## Setup (one-time)
```bash
.venv/bin/pip install playwright
.venv/bin/playwright install chromium
```
