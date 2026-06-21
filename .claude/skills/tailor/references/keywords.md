# Keyword ledger

The defensible keyword palette for `/tailor`. Pull from **ALLOWED** when a JD
demands an exact ATS match; never put anything from **FORBIDDEN** on the page.
Organized by category so it stays easy to edit. Every ALLOWED term is honestly
inferable from Khoa's real work (source noted where it isn't obvious).

**Rules**
- ATS rewards verbatim string matches — if a JD says "data analysis", list
  `Data Analysis`, not `Data Analytics`.
- An ALLOWED term is only fair game if the JD actually signals it. Don't pad.
- A skill the JD never touches gets dropped from that resume.
- When in doubt, skip it and note the gap in the run summary.

---

## ALLOWED

### Languages
Python, JavaScript, TypeScript, C++, SQL, HTML/CSS, Bash / Shell Scripting

### AI / ML
Machine Learning, Deep Learning, Neural Networks, AI, genAI, LLM, NLP,
Prompt Engineering, AI agent, PyTorch, Scikit-learn, Claude API, PaddleOCR, ONNX
- *Deep Learning / Neural Networks*: Coursera DL Specialization + CS50 AI, plus
  XGBoost / Random Forest / PyTorch in work.
- *agentic workflow*: **JD-conditional** — only if the JD itself uses "agent/agentic".

### Information Retrieval
Information Retrieval, Ranked Retrieval, Few-shot Retrieval
- Source: LinkedIn Outreach (tier/rank-based — **never** call it RAG).

### Software Engineering / Backend
OOP, REST APIs, Error Handling, Retry Logic, Type Hints, backend, full-stack,
WebSocket, Real-time Systems, Pipeline Orchestration, Performance Optimization,
Software Testing
- Source: PR Pilot (REST API), IOE gateway (WebSocket/real-time), pytest suites.

### Web / Frontend & Browser
Web Development, React.js, Svelte, Node.js, Browser Extensions, Manifest V3,
Service Workers, Web Workers, WebGPU, WASM
- Source: Local Lens (React 19 / TS, MV3 extension, WebGPU/WASM), metriclens (Svelte).

### Design / Media
Adobe Creative Suite, Adobe Acrobat Pro, Graphic Design, Video Editing,
ClipChamp, YouTube Studio
- Source: Khoa-confirmed — Adobe Acrobat Pro in the Creative Suite; graphic/video
  design work in ClipChamp + YouTube Studio. Render as
  `Adobe Creative Suite (Acrobat Pro), Graphic Design (ClipChamp, YouTube Studio)`.

### Data / Analytics
Data Analysis, data science, Pandas, NumPy, Matplotlib, Seaborn, Jupyter, Excel
- Source: FPT Telecom data work.

### Audio / Real-time
Audio Processing, Telephony, Streaming, Speech Recognition, Text-to-Speech
- Source: IOE / Mastra Voice Gateway (Vocode + Twilio).

### DevOps & Tools
Docker, Containerization, CI/CD, DevOps, Git / Git workflows, Linux, AWS, Azure,
Google Cloud, Google Colab, Windows 11
- Source: PR Pilot (Docker + GitHub Actions), Local Lens (AWS S3 + CloudFront).

### Databases
SQL, SQLite
- Source: Autoly (SQLite + sqlite3 + auth). No SQL at FPT (CSV-based).

### Hardware / Digital Logic
Verilog, SystemVerilog, HDL, Digital Logic, FPGA, Intel Cyclone V,
Intel Quartus Prime Lite
- Source: FSU Engineering Tools Lab coursework.

---

## FORBIDDEN (never put on the page)

> The machine-checkable FORBIDDEN list is enforced by
> `scripts/lint_honesty.py` (its module constants are the single source of
> truth; the save-hook runs it automatically). This list is the human-readable
> mirror — keep the two in sync. The linter catches the mechanical cases; the
> judgment cases (category relabeling, attribution) stay with you.

- **Tech Khoa hasn't touched:** Java, Kubernetes, Rust, Go, .NET, Angular, Vue,
  Solana, Spring. (If a genuinely defensible source ever emerges, move it up and
  note the source — until then, off-limits.)
- **Scale Khoa didn't operate at:** large-scale, production-grade, high-throughput.
- **RAG** — LinkedIn Outreach is rank/tier-based, not embedding-based.
- **XGBoost ... 93%** — that accuracy jump was a teammate's work at FPT.
- **Resume buzzwords:** spearheaded, leveraged, owned, world-class, 10x,
  best-in-class, synergize.

(Note: "Honors Program" in Education is real and confirmed — keep it.)
