# Honesty rules

Run this audit on every draft **before** saving. Reject and fix your own draft if any trigger
fires, then note what you caught in the run summary. A flagged-and-fixed trigger is never
penalized; a buried stretch discovered later is the only real failure.

> **What fires automatically vs. what's yours.** On save, the hook
> (`scripts/post_save_build.py`) runs only the two deterministic checks an eyeball
> reliably misses: **number-traceability** (rule 1 — every number in an output bullet
> must trace to a *selected* master block) and the **PR-Pilot either/or** bullet.
> Everything else below is YOUR checklist — apply it before saving: the FORBIDDEN
> tech list (rule 2), RAG (rule 5), scale claims (rule 6), buzzwords (rule 7),
> "agentic" vs. the JD (rule 8), and the judgment rules — category relabeling
> (rule 4), IOE/FPT attribution, the closed pool (rule 9). The lists on this page
> are the single source of truth; nothing mirrors them in code anymore.

## Hard rejects (resume and cover letter)

1. **No invented metrics.** Every number / percentage / date / install / latency / accuracy
   traces 1:1 to `assets/master_resume.tex` or the project's repo. No new numbers.
2. **No invented technologies.** Every tech name on the page exists in source for that project.
   Forbidden (no defensible source): **Java, Kubernetes, Rust, Go, .NET, Angular, Vue, Solana,
   Spring**.
3. **No invented dates or companies.** Copy date ranges verbatim.
4. **No relabeling a project's category.** A Random Forest classifier is not a "ranking model"
   just because the JD says ranking. Reframing in JD vocabulary stops at honest reframings.
5. **No "RAG".** LinkedIn Outreach is rank/tier-based, not embedding-based. Use "ranked
   retrieval" / "tier-based retrieval" / "few-shot example retrieval" / "information retrieval".
6. **No scale Khoa didn't operate at:** never "large-scale", "production-grade",
   "high-throughput". 290 installs is not "large-scale".
7. **No generic buzzwords:** spearheaded, leveraged, owned, world-class, 10x, best-in-class,
   synergize.
8. **"Agentic"** only if the JD itself uses the term.
9. **The project pool is closed.** Never invent a project. If a JD needs a domain none of the 5
    covers, leave it uncovered and flag it in `uncovered must-haves`.

## Per-source honesty notes

- **IOE (gateway):** the Mastra agent + SQL + business logic pre-existed Khoa. He owned the
  **gateway** that wired a phone number to the agent. Never claim the agent itself. GPT-4o-mini was
  his own pick (cheapest/fastest testing); Vocode + Twilio were the team's choice.
- **FPT Telecom:** Khoa built the 86% Random Forest. No SQL (CSV-based), no DB, no Airflow/cron.
- **Education:** "GPA: 3.9/4.0, Honors Program" is real and confirmed — **keep it**. "1st in
  Division 2" on the ICPC line is real — keep it.

## Default

When uncertain whether a fact survives a reword, **keep the original wording**. When uncertain
whether a skill is defensible, **skip it and note the gap**. Less, not more.

## Cover-letter-specific (only with `--cover`)

The cover body is **fixed** (vetted voice-anchor prose); you only write the `<<WHY_COMPANY>>`
paragraph — and you check that paragraph against this list yourself (nothing lints it; the body
is exempt anyway). Every company fact in `<<WHY_COMPANY>>`
must trace 1:1 to what the research sub-agent returned. No inflating "74,000+" to "75,000+", no
merging two facts into a vaguer one. If research came up empty, write a
`[TODO: Khoa — why this company]` placeholder rather than a generic "I admire your innovative
mission" line. See `references/cover-letter.md`.
