# Cover-letter pipeline

Only runs with **`--cover`** (e.g. `/tailor --cover Stash`, or "also write a cover letter for
Stash"). Default `/tailor` writes the resume only.

Output: `output/<company>/cover_letter.tex`, compiled to `Khoa_Ngo_cover_letter.pdf` by
`build_cover_letter.py` (which the save-hook runs automatically when you write the `.tex`).
Template: `assets/cover_letter.tex`. Voice anchor: `assets/cover_letter_voice.md`. No markdown,
no pandoc.

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

## 2. Compose by filling `assets/cover_letter.tex`

Copy the template to `output/<company>/cover_letter.tex` and fill it:

- **`% Company insights` comment block** at the top: paste `url_used`, `impressive_numbers`,
  `notable_specifics`. These are LaTeX comments — audit metadata that never renders.
- **`<<Company>>`** in the recipient + salutation.
- **Opening paragraph** — 1-line identity hook in voice: junior CompE at FSU (3.9 GPA, ICPC Gold
  '24, 1st in Div 2 NA South), then "the things I actually want to tell you about are below".
- **Body paragraph** — ONE project (strongest JD fit, often resume P1), told as a story in voice,
  mapped to the JD. Not resume-bullet shape.
- **Closing paragraph** — why THIS company. Name at least one researched fact by its **actual
  value** ("the 74,000+ businesses already on Stash", not "your impressive customer base").
  2–3 sentences.

Read `assets/cover_letter_voice.md` first — self-deprecating, specific, narrative; never corporate.
Date is `\today` (renders at compile).

## 3. Honesty audit

Run `references/honesty-rules.md`, plus the cover-letter rule: every company fact in the closing
traces 1:1 to the sub-agent's output. If research came up empty, keep the insights block as
`% [none found from <url>]` and write the closing as a one-line
`<<[TODO: Khoa — why this company]>>` placeholder; flag it in the run summary. Never a generic
"I'm excited about your innovative mission".

## 4. Compile

Writing `output/<company>/cover_letter.tex` fires the save-hook, which runs
`build_cover_letter.py <company>` → `Khoa_Ngo_cover_letter.pdf`. To rebuild manually:
`python3 build_cover_letter.py <prefix>`.
