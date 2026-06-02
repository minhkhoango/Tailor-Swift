# Reasoning — Etched_Infrastrucutre

_Backfilled 2026-06-02 by reading the committed `resume.tex` (no source JD exists — see anomaly note). Decision log: what's here, why it appears to exist, and what's uncertain._

## ⚠️ Anomaly note (read first)
- **There is no `jobDescription/Etched_Infrastrucutre.txt`.** This output directory has no source JD, so its reasoning can't be traced to a JD analysis the way every other job can. (The directory name is also misspelled — "Infrastrucutre".)
- This directory also contains a stray **`resume copy.tex`** alongside `resume.tex` — a manual duplicate, not something `/tailor` produces. Its body is identical to the Etched_Inference resume.
- **Most likely explanation:** this folder is an experimental copy/rename of **Etched_Inference** (the resume body, skills axis, and the cover letter are near-identical, including the same `I set my goal` trailing fragment). It does not correspond to a real, distinct Etched "Infrastructure" posting that exists in this repo.
- **Recommendation for Khoa:** either (a) add the real Infrastructure JD to `jobDescription/` and re-run `/tailor Etched_Infrastrucutre` (fixing the spelling), or (b) delete this directory and `resume copy.tex` as a stray. Until then, treat the analysis below as reconstructed from the artifact, not authoritative.

## 1. JD analysis
- **Reconstructed (no source JD).** The skills axis and cover letter mirror Etched_Inference, so the implied target is an Etched infrastructure/systems role sharing the standard Etched requirements: C/C++ or Rust, DS&A, low-level SW, HW/SW co-design, Linux internals, CI/CD, server virtualization.
- Treat role_type as **SWE (infrastructure / systems)**, inferred — not parsed from a JD.

## 2. Project selection (3 of 5)
| Project | Verdict | Why |
|---|---|---|
| Local Lens | ✅ picked (P1) | Same as the Inference variant — strongest numbers + client-side inference |
| P4-stack | ✅ picked (P2) | Low-level dev tooling |
| PR Pilot | ✅ picked (P3) | CI/CD |

Identical selection to Etched_Inference, reinforcing that this is a copy of that run.

## 3. Per-project rewrites
- **Local Lens** — 4 bullets (installs → dual-engine inference → test suite → AWS uptime); `\emph{}`: TypeScript, ONNX Runtime Web, PaddleOCR, WebGPU.
- **P4-stack** — bullet 1 lightly reworded vs. Inference: "Engineered a stacked-diff workflow CLI **for engineers** that cut merge conflict resolution from 10 minutes to 5 seconds **in Perforce**…" (moved the "engineers" / "Perforce" emphasis around — cosmetic).
- **PR Pilot** — automation + validation bullets.

## 4. Experience reframes
- **IOE:** verbatim.
- **FPT Telecom:** bullet 1 reads "Random Forest **machine learning** model…" — "machine learning" inserted vs. the Inference variant. Otherwise verbatim.

## 5. Technical skills rebuild
- **categories used:** Languages / Hardware & Low-Level / AI/ML / Developer Tools
- **notable differences vs. Etched_Inference:**
  - Languages reordered to lead with **Verilog, SystemVerilog** and added **HTML/CSS**
  - AI/ML added **PaddleOCR, Numpy** (alongside SIMD, Transformers)
  - Developer Tools swapped **GitHub Actions → WSL**
- **added:** HTML/CSS, PaddleOCR, Numpy, WSL, SIMD, Transformers, Driver Debugging
- **considered but skipped:** Rust (FORBIDDEN)

## 6. Honesty audit
- **triggers caught + fixes:** none recorded — and, as with Etched_Inference, **SIMD** and **Driver Debugging** slipped through (see §9). RAG / XGBoost-93% / large-scale all correctly absent.

## 7. JD coverage
- Cannot be computed honestly without a source JD. Addressed/unaddressed mirror Etched_Inference: DS&A, C++, low-level, Linux, CI/CD addressed; Rust, firmware, real C/C++ project, kernel/driver work unaddressed.

## 8. Cover letter
- **company research:** etched.com → 500,000+ tokens/sec on Llama 70B, 8xSohu replaces 160 H100s, transformer ASIC, "$120M raised", superintelligence mission.
- **angle chosen:** byte-for-byte the Etched_Inference letter ("making inference run on small hardware… I'd like the silicon"). It still ends with the stray **`I set my goal`** fragment — same artifact, should be deleted.
- The letter is **not tailored to an "infrastructure" angle** — further evidence this is an Inference copy, not a purpose-built infrastructure application.

## 9. Uncertainty & judgment calls
- **Biggest uncertainty:** the directory itself. No JD = no auditable target. Everything above is reverse-engineered from the artifact.
- **Stretches carried over from Inference:** **SIMD** (low confidence — not in ALLOWED list, no source) and **Driver Debugging** (low/medium — a JD desired-qual listed as a possessed skill). Both should be confirmed or cut. PaddleOCR/Numpy are honestly sourced.
- **Duplicate artifacts:** `resume.tex` and `resume copy.tex` coexist; the cover letter is a verbatim Inference copy with the same trailing fragment.
- **Open questions for Khoa:** (1) Is there a real Etched Infrastructure JD? If so, add it and re-run. (2) Delete `resume copy.tex` and the `I set my goal` fragment. (3) Same SIMD / Driver Debugging questions as the Inference variant.

## 10. Output artifacts
- resume.tex / Khoa_Ngo_resume.pdf — page count: 1
- **resume copy.tex** — stray duplicate, not produced by `/tailor` (recommend deleting)
- experience.txt
- cover_letter.md (verbatim copy of Etched_Inference; cover-letter PDF not present at backfill time)
