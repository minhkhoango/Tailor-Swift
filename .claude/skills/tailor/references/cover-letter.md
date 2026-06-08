# Cover-letter pipeline

Only runs with **`--cover`** (e.g. `/tailor --cover Stash`, or "also write a cover letter for
Stash"). Default `/tailor` writes the resume only.

Output: `output/<company>/cover_letter.tex`, compiled to `Khoa_Ngo_cover_letter.pdf` by
`build_cover_letter.py` (which the save-hook runs automatically when you write the `.tex`).
Template: `assets/cover_letter.tex`. No markdown, no pandoc.

**The body is fixed.** `assets/cover_letter.tex` already contains the vetted voice-anchor prose
(opening hook + IOE + FPT + Local Lens + LinkedIn Outreach — all four stories, never cut). You do
**not** write or pick paragraphs. Only two things vary per JD: **`<<Company>>`** (recipient +
salutation) and the single **`<<WHY_COMPANY>>`** paragraph between the
`% @lint:why-company-start` / `% @lint:why-company-end` sentinels.

## 1. Company research (sub-agent)

Spawn a sub-agent (`subagent_type: general-purpose`) that uses WebFetch to pull **impressive
concrete numbers** and **notable specifics** from the company's site.

- **URL:** lowercase the JD stem → `https://www.<stem>.com` first (e.g. `Skydio.txt` →
  skydio.com). If the JD body names a different official URL, or the stem is ambiguous
  (`OxfamInternational` → oxfam.org), prefer that.
- **Sub-agent prompt (self-contained):** visit the homepage; optionally follow 1–2 obvious links
  from {About, Customers, Investors, Press, Newsroom, Impact}. Return exactly:
  ```
  company: <name>
  url_used: <url>
  impressive_numbers:
    - "<fact with a number>"
  notable_specifics:
    - "<product / program / customer / mission>"
  ```
- **Bar for "impressive":** specificity + a number — "serving 74,000+ businesses",
  "100M+ monthly users". If the site has nothing usable, the sub-agent says so. **Never fabricate.**

## 2. Fill the two slots in `assets/cover_letter.tex`

Copy the template to `output/<company>/cover_letter.tex` and fill **only**:

- **`% Company insights` comment block** at the top: paste `url_used`, `impressive_numbers`,
  `notable_specifics`. These are LaTeX comments — audit metadata that never renders.
- **`<<Company>>`** in the recipient line + salutation.
- **`<<WHY_COMPANY>>`** — the one paragraph between the `% @lint:why-company-start` /
  `% @lint:why-company-end` sentinels. Why THIS company, 2–3 sentences, in voice. Name at least
  one researched fact by its **actual value** ("the 74,000+ businesses already on Stash", not
  "your impressive customer base").

Leave the four body stories exactly as they are. Date is `\today` (renders at compile).

## 3. Honesty audit

`lint_honesty.py --cover` runs automatically on save and scans **only** the why-company paragraph
(the fixed body is exempt — it legitimately attributes the teammate's "XGBoost … 93%"). On top of
that linter, every company fact in `<<WHY_COMPANY>>` must trace 1:1 to the sub-agent's output — no
inflating "74,000+" to "75,000+". If research came up empty, keep the insights block as
`% [none found from <url>]` and write the slot as a one-line
`<<[TODO: Khoa — why this company]>>` placeholder; flag it in the run summary. Never a generic
"I'm excited about your innovative mission".

## 4. Compile

Writing `output/<company>/cover_letter.tex` fires the save-hook, which runs
`build_cover_letter.py <company>` → `Khoa_Ngo_cover_letter.pdf`. To rebuild manually:
`python3 build_cover_letter.py <prefix>`.
