# Reasoning — MarmonHoldings_Data_Eng

_Backfilled 2026-06-02 by reading `jobDescription/MarmonHoldings_Data_Eng.txt` against the committed `resume.tex`. Decision log for this application: what was produced, why, and where it's uncertain. Every fact still traces to source — this file explains choices, it does not add new claims._

## 1. JD analysis
- **role_type:** Data (data engineering / analytics)
- **top_keywords:** SQL (complex, optimized), data pipelines / dataflow, machine learning (linear regression, correlation, statistical modeling), predictive/prescriptive analytics, Snowflake (Snowpipes, SnowSight), Google Analytics, social/media analytics, retail merchandising, trends & patterns, data documentation/visualization
- **must_haves:** undergrad CS/SW Eng; 2+ years data-tech/architecture experience; complex optimized SQL; data-pipeline management; ML methods (regression/statistical)
- **nice_to_haves:** Snowflake; Google Analytics / social-media analytics; predictive/prescriptive analytics
- **anti_signals:** none explicit
- **JD-author hint (in file):** "For Local Lens, I use Google Analytics (Google Developer Dashboard to track user count, install/uninstall over time)" → explicit instruction to surface Google Analytics via Local Lens. **NOTE: no cover letter needed.**

## 2. Project selection (3 of 5)
| Project | Verdict | Why |
|---|---|---|
| Local Lens | ✅ picked (P1) | Khoa's own hint ties it to **Google Analytics**; strongest user/install numbers → "trends and patterns in data" |
| LinkedIn Outreach | ✅ picked (P2) | Information-retrieval / personalization + a quantified pipeline; the closest thing to a data-systems project in the pool |
| Autoly | ✅ picked (P3) | The only project with real **SQL / SQLite** — directly backs the JD's "complex SQL" must-have |
| P4-stack | ❌ dropped | Dev-tooling, no data/SQL/analytics signal |
| PR Pilot | ❌ dropped | CI/CD automation, no data/analytics signal |

**This is a different 3 from the Etched runs** — the pool genuinely re-scored for a data role (dropped both dev-tools projects, pulled in Autoly for SQL and LinkedIn Outreach for retrieval/pipeline). Ordering is chronological with both "Present" projects up top; Local Lens leads LinkedIn Outreach on JD relevance (the Google Analytics hook).

## 3. Per-project rewrites
- **Local Lens** — bullets: GA-tracking install/uninstall/user-count (reframed bullet 1 to name **Google Analytics** explicitly per the JD hint) → dual-engine **OCR** pipeline (kept "OCR", not "inference" — wrong audience) → test suite → AWS uptime. `\emph{}` changed to **TypeScript, Google Analytics, AWS, PaddleOCR** (added Google Analytics, dropped WebGPU/ONNX — irrelevant to a data role).
- **LinkedIn Outreach** — 4 bullets: 60% time reduction → tier-based few-shot retrieval → 11-min pytest QA → human-in-the-loop voice.md. `\emph{}`: Python, pytest, **Information Retrieval** (no "RAG", honored). Reads as a data/ML pipeline.
- **Autoly** — 8-step app → **SQLite via sqlite3** (the SQL proof) → Render deploy + 50 users. `\emph{}`: Python, **SQLite, SQL**, PyMuPDF.

## 4. Experience reframes
- **IOE:** verbatim from pool (weak fit for a data role; retained per Step 5).
- **FPT Telecom:** **reframed toward the JD** — "Random Forest **predictive model**… with **regression** signals" (hits "predictive analytics" + "regression"), and "Built a **data pipeline**…driving feature selection in Jupyter" (hits "data pipelines"). This is the strongest-fit experience for Marmon and was rewritten to say so. Facts (86%, 60+ features, 20 years, 8 sectors, $4,000) unchanged.

## 5. Technical skills rebuild
- **categories used:** Languages / **Data & Analytics** / **ML & Modeling** / Developer Tools — both middle categories renamed for the data role (from the default "Frameworks & Libraries" / "AI/ML"); all hardware/low-level skills dropped wholesale.
- **added (+ source justification):** SQL (Autoly), Pandas, NumPy (FPT data work), Google Analytics (Local Lens, per JD hint), Data Pipelines (FPT + LinkedIn Outreach), Scikit-learn / Random Forest / Regression / Statistical Modeling / Predictive Analytics (FPT Random Forest model), Render, AWS
- **dropped (+ reason):** Verilog, SystemVerilog, FPGA, Quartz, Digital Logic, ONNX, Quantization, WebGPU — zero data-role signal
- **considered but skipped:** **Snowflake** (JD plus, but no source — left off honestly), **Airflow/cron** (FPT was CSV-based, no orchestrator — honesty note in pool)

## 6. Honesty audit
- **triggers caught + fixes:** "RAG" correctly avoided for LinkedIn Outreach (used "Information Retrieval"). The FPT bullet correctly does **not** reinstate the teammate's 86%→93% XGBoost claim. No "large-scale". See §9 for one skill that flirts with the line.

## 7. JD coverage
- **addressed:** SQL → Autoly + skills; ML/regression/statistical modeling → FPT bullets + ML & Modeling skills; predictive analytics → FPT "predictive model" + skills; data pipelines → FPT + LinkedIn Outreach + skills; Google Analytics → Local Lens bullet + stack + skills; trends/patterns → Local Lens GA tracking
- **unaddressed:** **Snowflake / Snowpipes / SnowSight** (no source — the biggest gap), **2+ years data experience** (Khoa has one ~3-month internship), **retail merchandising** domain, **prescriptive analytics**, **complex *optimized* SQL** (Autoly's SQL is CRUD-level, not optimized analytics SQL)

## 8. Cover letter
- n/a — JD explicitly said no cover letter needed. None generated. ✅ Correct call.

## 9. Uncertainty & judgment calls
- **Stretches:**
  - **Social Media Analytics** in skills — **low** confidence. JD lists "media analytics / Social Media Analytics," but Khoa's only analytics surface is *Google* Analytics on a Chrome extension. This is the thinnest entry on the page; **recommend cutting or downgrading to just "Google Analytics."**
  - **Predictive Analytics / Statistical Modeling** — **medium**. Defensible from the Random Forest model, but "statistical modeling" oversells a tree-based classifier slightly.
  - "complex, highly optimized SQL" framing — the resume implies SQL competence (Autoly) but the underlying SQL is basic; **medium-low** on the JD's specific bar.
- **Gaps the resume can't close:** **Snowflake** (the headlined nice-to-have) and **2+ years of data experience** — both are real misses with no honest workaround. Marmon is a domain-stretch application: Khoa is a strong generalist, not a seasoned data engineer.
- **Coin-flips:** LinkedIn Outreach vs. a stronger pure-data project — there isn't a better data project in the pool, so it's in by default more than by merit. Autoly earns its slot purely on the SQL keyword.
- **Open questions for Khoa:** (1) Drop "Social Media Analytics"? (2) Any actual Snowflake exposure to add? (3) Is the FPT "regression signals" phrasing accurate to what the model actually used (rolling features), or does it overclaim regression specifically?

## 10. Output artifacts
- resume.tex / Khoa_Ngo_resume.pdf — page count: 1
- experience.txt
- cover_letter.md — n/a (JD said none)
