# Reasoning — Etched_Firmware

_Backfilled 2026-06-02 by reading `jobDescription/Etched_Firmware.txt` against the committed `resume.tex` / `cover_letter.md`. Decision log for this application: what was produced, why, and where it's uncertain. Every fact still traces to source — this file explains choices, it does not add new claims._

## 1. JD analysis
- **role_type:** SWE (firmware / embedded — custom ASIC bring-up)
- **top_keywords:** firmware, custom ASICs, low-level drivers, hardware interfaces, system initialization, runtime libraries, model-execution frameworks, high-throughput inference/training, silicon bring-up, C/C++, Rust, DS&A, hardware/software co-design, Linux internals, CI/CD
- **must_haves:** CS/Eng degree progress; C/C++ **or** Rust; strong DS&A; low-level SW; HW/SW co-design
- **nice_to_haves:** Linux internals / kernel / driver debugging; hardware diagnostics / logs; virtualization / CI/CD; Rust or embedded
- **anti_signals:** none explicit (role is firmware/systems, not applied-ML/web)

## 2. Project selection (3 of 5)
| Project | Verdict | Why |
|---|---|---|
| Local Lens | ✅ picked (P1) | Strongest numbers; on-device inference + test/uptime bullets give a perf + reliability story that maps to "operate reliably at peak performance" |
| P4-stack | ✅ picked (P2) | Low-level dev tool + algorithm; "I make the slow thing fast" narrative for bring-up work |
| PR Pilot | ✅ picked (P3) | CI/CD + GitHub Actions hits the desired CI/CD qualification |
| LinkedIn Outreach | ❌ dropped | No firmware/systems/HW signal |
| Autoly | ❌ dropped | Web forms — no overlap |

Same 3 projects as the ChipSimSW variant; the project axis didn't change because both Etched roles share the same requirements block.

## 3. Per-project rewrites
- **Local Lens** — **4 bullets** here (installs → dual-engine inference → test suite → AWS 99.9% uptime). Ordering leads with the shipped/installs proof, then perf, then validation, then uptime; the **AWS uptime bullet was added** (vs. ChipSimSW's 3) to push the "reliable, peak performance" firmware theme. `\emph{}`: TypeScript, ONNX Runtime Web, PaddleOCR, WebGPU.
- **P4-stack** — both pool bullets, near-verbatim (diff3 algorithm + 1000+ line changelist splitting).
- **PR Pilot** — automation bullet + cold-email validation bullet; `\emph{}` keeps GitHub Actions + Docker for CI/CD.

## 4. Experience reframes
- **IOE:** kept verbatim. The Vocode-bug-fix bullet is reused in the cover letter as a "reliability under deadline" proof, which is the firmware-relevant angle.
- **FPT Telecom:** verbatim, retained per Step 5; weak fit, no reframing.

## 5. Technical skills rebuild
- **categories used:** Languages / Hardware & Low-Level / AI/ML / Developer Tools (same shape as ChipSimSW)
- **added (+ source justification):** Hardware & Low-Level — Verilog, SystemVerilog, FPGA, Intel Quartus, Digital Logic, Linux (coursework, ALLOWED list); Quantization in AI/ML (Local Lens); HTML (JD keyword); CI/CD, GitHub Actions, Bash (PR Pilot)
- **dropped (+ reason):** none materially
- **considered but skipped:** Rust (FORBIDDEN); "firmware" / "embedded" / "driver debugging" as skills (no shipped evidence — see §9)

## 6. Honesty audit
- **triggers caught + fixes:** none in committed output. "High-throughput" appears in the *JD*, but the resume correctly does **not** claim it for Khoa's work (Step 8 rule 5 held).

## 7. JD coverage
- **addressed:** DS&A → ICPC + skills; C++ → Languages; low-level/HW → Hardware & Low-Level block; reliability/peak-performance → Local Lens uptime + inference perf; CI/CD → PR Pilot + skills; Linux → skills
- **unaddressed:** **firmware** (no project), **low-level drivers / system initialization**, **silicon bring-up**, **runtime libraries / model-execution frameworks**, **C/C++ or Rust in a real project**, **Rust**, **kernel/driver debugging**, **high-throughput inference/training**

## 8. Cover letter
- **company research:** etched.com → 500,000+ tokens/sec on Llama 70B, 8xSohu replaces 160 H100s, first transformer ASIC, "$120M raised", "building the hardware for superintelligence"
- **angle chosen:** "the low, unglamorous layer where software meets hardware and has to not break" — explicitly leans into firmware/reliability framing. Showcase bullets: ICPC (DS&A), P4-stack (low-level, making the slow thing fast), Vocode bug fix (reliability under a deadline → seed funding).

## 9. Uncertainty & judgment calls
- **Stretches:**
  - Same coursework-based Hardware & Low-Level block as ChipSimSW — **medium** confidence; it's the firmware proxy but it isn't firmware.
  - "Quantization" in AI/ML — **high** confidence (real Local Lens work), included to gesture at model-execution efficiency.
- **Gaps the resume can't close:** This is the **weakest-fit** of the Etched variants. The role is *firmware for custom ASICs — drivers, system init, silicon bring-up*, and Khoa has zero firmware/driver/embedded shipping history. The cover letter's "I want to live in that layer" is aspirational, honestly so, but the resume body offers no firmware evidence. A screener filtering on firmware experience would likely cut this.
- **Coin-flips:** 3-bullet vs. 4-bullet Local Lens — the 4th (AWS uptime) was kept here for the reliability theme; it's borderline filler and could be cut to tighten the page.
- **Open questions for Khoa:** Worth deciding whether to even apply to the *firmware* req vs. concentrating on ChipSimSW (tooling) and Inference, which are closer to the actual portfolio.

## 10. Output artifacts
- resume.tex / Khoa_Ngo_resume.pdf — page count: 1
- experience.txt
- cover_letter.md (cover-letter PDF was not present in this dir at backfill time)
