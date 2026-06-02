# Reasoning — Etched_Inference

_Backfilled 2026-06-02 by reading `jobDescription/Etched_Inference.txt` against the committed `resume.tex` / `cover_letter.md`. Decision log for this application: what was produced, why, and where it's uncertain. Every fact still traces to source — this file explains choices, it does not add new claims._

## 1. JD analysis
- **role_type:** SWE (inference / firmware — ASIC bring-up for transformer execution)
- **top_keywords:** inference, custom ASICs, transformer models, low-level drivers, system initialization, runtime libraries, model-execution frameworks, high-throughput inference/training, **Rust** (added to this variant's keyword list), firmware, C/C++, DS&A, HW/SW co-design, Linux, CI/CD
- **must_haves:** CS/Eng degree; C/C++ **or** Rust; DS&A; low-level SW; HW/SW co-design
- **nice_to_haves:** Linux internals / kernel / driver debugging; hardware diagnostics; virtualization / CI/CD; Rust or embedded
- **anti_signals:** none explicit

## 2. Project selection (3 of 5)
| Project | Verdict | Why |
|---|---|---|
| Local Lens | ✅ picked (P1) | The on-device / client-side **inference** angle is the single best match to an inference role; strongest numbers too |
| P4-stack | ✅ picked (P2) | Low-level tooling + algorithm; perf narrative |
| PR Pilot | ✅ picked (P3) | CI/CD desired qualification |
| LinkedIn Outreach | ❌ dropped | No systems/inference signal |
| Autoly | ❌ dropped | No overlap |

## 3. Per-project rewrites
- **Local Lens** — 4 bullets (client-side inference installs → dual-engine inference → test suite → AWS uptime). Bullet 1 keeps "100% client-side inference," which is the verbatim hook for an inference role.
- **P4-stack** — both bullets, near-verbatim.
- **PR Pilot** — automation + validation bullets.

## 4. Experience reframes
- **IOE:** verbatim. Latency bullet ("1.8-second latency") reads as inference-latency-adjacent.
- **FPT Telecom:** verbatim, retained per Step 5.

## 5. Technical skills rebuild
- **categories used:** Languages / Hardware & Low-Level / AI/ML / Developer Tools
- **added (+ source justification):**
  - Hardware & Low-Level: **Driver Debugging** added (JD desired qualification), plus Linux, Verilog, FPGA, Quartus, Digital Logic (coursework)
  - AI/ML: **SIMD** and **Transformers** added; **Claude API** and **Quantization** dropped — the block was re-pointed from "applied ML" toward "model execution on hardware"
- **dropped (+ reason):** Claude API, Quantization (less relevant to an inference-runtime role than Transformers/SIMD)
- **considered but skipped:** Rust (FORBIDDEN despite being a JD keyword — no source)

## 6. Honesty audit
- **triggers caught + fixes:** none flagged in the committed output — but see §9; two skills entries here are thinner than the audit ideally tolerates.

## 7. JD coverage
- **addressed:** inference → Local Lens client-side inference; DS&A → ICPC + skills; C++ → Languages; Transformers → skills; low-level/HW → Hardware & Low-Level; Linux + driver debugging → skills; CI/CD → PR Pilot
- **unaddressed:** **Rust**, **firmware / system initialization**, **runtime libraries / model-execution frameworks** as real experience, **silicon bring-up**, **high-throughput inference at scale**, **C/C++ project**

## 8. Cover letter
- **company research:** etched.com → 500,000+ tokens/sec on Llama 70B, 8xSohu replaces 160 H100s, first transformer ASIC, "$120M raised", "building the hardware for superintelligence"
- **angle chosen:** "most of my spare time goes into making inference run on small hardware… I'd like the silicon." The closing line ("I'd like the silicon") is a deliberate voice beat. Showcase bullets: ICPC (DS&A), P4-stack (low-level/perf), Local Lens client-side inference + quantization parity ("small-footprint inference is the whole game").
- ⚠️ The committed file has a stray trailing fragment `I set my goal` after `Khoa Ngo` — looks like an editing artifact that should be deleted.

## 9. Uncertainty & judgment calls
- **Stretches (the important ones for this variant):**
  - **SIMD** in AI/ML — **low** confidence. SIMD is *not* on the bullet_pool ALLOWED list and there's no project or coursework trace for it in the source files. This looks like an over-reach added to chase the "low-level inference" theme. **Recommend removing unless Khoa can point to real SIMD work.**
  - **Driver Debugging** in Hardware & Low-Level — **low/medium** confidence. It's a JD *desired* qualification, but Khoa has no driver-debugging evidence in source. Listing a desired-qual as a possessed skill is exactly the kind of thing the honesty audit exists to catch. **Recommend confirming or cutting.**
  - **Transformers** — **medium**. Defensible via on-device model work + DL coursework, but Khoa hasn't built transformer internals.
- **Gaps the resume can't close:** Same core gap as the other Etched roles — no Rust, no firmware, no C/C++ project. "Client-side inference" is the closest honest hook and it carries most of the load.
- **Coin-flips:** Dropping Quantization in favor of SIMD/Transformers was a judgment call; Quantization is the *better-sourced* term and arguably should have stayed.
- **Open questions for Khoa:** (1) Is SIMD real? (2) Is Driver Debugging real? (3) Delete the `I set my goal` fragment in cover_letter.md.

## 10. Output artifacts
- resume.tex / Khoa_Ngo_resume.pdf — page count: 1
- experience.txt
- cover_letter.md (cover-letter PDF was not present in this dir at backfill time; file has a stray trailing fragment — see §8)
