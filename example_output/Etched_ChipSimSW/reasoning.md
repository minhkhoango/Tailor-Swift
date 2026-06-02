# Reasoning — Etched_ChipSimSW

_Backfilled 2026-06-02 by reading `jobDescription/Etched_ChipSimSW.txt` against the committed `resume.tex` / `cover_letter.md`. Decision log for this application: what was produced, why, and where it's uncertain. Every fact still traces to source — this file explains choices, it does not add new claims._

## 1. JD analysis
- **role_type:** SWE (hardware/software co-design — simulation & tooling)
- **top_keywords:** C/C++, Rust, data structures & algorithms, low-level software, hardware/software co-design, simulations, tools engineers use to analyze systems, Linux internals, kernel/driver debugging, CI/CD, embedded
- **must_haves:** progress toward CS/Eng degree; proficiency in C/C++ **or** Rust; strong DS&A fundamentals; low-level SW understanding; HW/SW co-design understanding
- **nice_to_haves:** Linux internals / kernel / driver debugging; hardware diagnostics / log interpretation; server virtualization / CI/CD; Rust or embedded
- **anti_signals:** none explicit (but the role is explicitly *not* applied-ML / web — it's systems/tooling)

## 2. Project selection (3 of 5)
| Project | Verdict | Why |
|---|---|---|
| Local Lens | ✅ picked (P1) | Strongest numbers; the test-suite + on-device-inference bullets map to "tools engineers use to analyze systems" and to low-level/perf work |
| P4-stack | ✅ picked (P2) | Best literal match to the JD — a CLI *tool that other engineers use*, with an algorithm (diff3) and a hard perf win |
| PR Pilot | ✅ picked (P3) | CI/CD + GitHub Actions hits the "CI/CD pipelines" desired qualification |
| LinkedIn Outreach | ❌ dropped | NLP/retrieval/outreach — no systems, low-level, or HW signal |
| Autoly | ❌ dropped | Web forms + SQLite — no overlap with systems/HW tooling |

Tiebreak: not needed; the top 3 were clearly the systems/tooling-flavored projects.

## 3. Per-project rewrites
- **Local Lens** — bullets kept (test suite → dual-engine inference → 290+ installs). Test suite **leads** here (it doesn't in other variants) because "tools engineers use to *analyze* systems" rewards a validation/observability story. `\emph{}` kept default-ish (TypeScript, ONNX Runtime Web, PaddleOCR, WebGPU). "OCR" softened toward "on-device inference pipeline" to read as low-level perf rather than a CV demo.
- **P4-stack** — both pool bullets kept. Left almost verbatim; the pool wording ("3-way diff3 merge algorithm", "split 1000+ line changelists") already speaks DS&A + dev-tooling, which is the JD's language.
- **PR Pilot** — GitHub Action automation bullet + cold-email validation bullet. `\emph{}` keeps GitHub Actions + Docker to surface CI/CD.

## 4. Experience reframes
- **IOE:** kept verbatim from pool. The "1.8-second latency" + "Fixed a Vocode bug" bullets double as a low-level / reliability story, which fits.
- **FPT Telecom:** kept verbatim (all 4 bullets). No reframing toward this JD — FPT is data-science work with weak fit, retained only because Step 5 never drops it.

## 5. Technical skills rebuild
- **categories used:** Languages / **Hardware & Low-Level** (renamed from "Frameworks & Libraries") / AI/ML / Developer Tools
- **added (+ source justification):** Hardware & Low-Level block — Verilog, SystemVerilog, FPGA, Intel Quartus, Digital Logic, Linux (all from FSU Engineering Tools Lab coursework, per bullet_pool ALLOWED list); HTML (JD lists it as an additional keyword); CI/CD, GitHub Actions, Bash (PR Pilot)
- **dropped (+ reason):** none of the prior skills needed dropping; the block was rebuilt around the HW/low-level axis
- **considered but skipped:** Rust (FORBIDDEN — no source), kernel/driver debugging as a skill (no real evidence; see §9)

## 6. Honesty audit
- **triggers caught + fixes:** none triggered in the committed output. Notably "RAG", "XGBoost 93%", "large-scale", and Rust were all kept out.

## 7. JD coverage
- **addressed:** DS&A → ICPC bullet + skills; C++ → Languages; low-level/HW → Hardware & Low-Level block; CI/CD → PR Pilot + skills; Linux → skills; "tools engineers use" → P4-stack + Local Lens test suite; HTML → Languages
- **unaddressed:** **C/C++ or Rust *proficiency demonstrated in a project*** (C++ appears only as a coursework skill, no shipped C/C++ project); **Rust**; **kernel development / driver debugging**; **hardware diagnostics / interpreting hardware logs**; **server virtualization**

## 8. Cover letter
- **company research:** etched.com → 500,000+ tokens/sec on Llama 70B, one 8xSohu server replaces 160 H100s, first transformer ASIC, "$120M raised", mission "building the hardware for superintelligence"
- **angle chosen:** "I build the tools that let you trust a system before it's real" — leans the application toward the *simulation/test-harness* half of the role (its honest strength) rather than the C/C++ half (its gap). The 3 showcase bullets are ICPC (DS&A must-have), P4-stack (tools other engineers depend on), Local Lens test suite (testing for failure modes).

## 9. Uncertainty & judgment calls
- **Stretches:**
  - "Hardware & Low-Level" skills (Verilog/SystemVerilog/FPGA/Quartus) — **medium** confidence. Honestly sourced to coursework, but it's *coursework*, not shipped systems work; a sharp screener will read it that way.
  - Framing Local Lens as low-level "on-device inference" — **medium**. The mechanic (bundled ONNX models running client-side) is real, but the project is a browser extension, not systems code.
- **Gaps the resume can't close:** The JD's spine is **C/C++ or Rust proficiency + HW/SW co-design + driver/kernel work**, and Khoa's shipped work is Python/TypeScript. This is the central honesty tension of the application — the resume routes around it via coursework skills and a tooling/testing narrative, but it cannot manufacture a C/C++ systems project that doesn't exist.
- **Coin-flips:** P3 could have been LinkedIn Outreach if the JD's "AI" keyword were weighted higher, but PR Pilot's CI/CD fit won. Reasonable either way.
- **Open questions for Khoa:** Is there any C/C++ coursework or embedded project (beyond Verilog labs) worth adding to the pool? Right now the single biggest must-have is the weakest part of the page.

## 10. Output artifacts
- resume.tex / Khoa_Ngo_resume.pdf — page count: 1
- experience.txt
- cover_letter.md (cover-letter PDF was not present in this dir at backfill time)
