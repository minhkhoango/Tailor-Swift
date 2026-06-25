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
Machine Learning, Deep Learning, Neural Networks, AI, genAI, LLM, NLP, RAG
Prompt Engineering, AI agent, PyTorch, Scikit-learn, Claude API, PaddleOCR, ONNX
chromedb, openai, sentence_transformers, groq
- *Deep Learning / Neural Networks*: Coursera DL Specialization + CS50 AI, plus
  XGBoost / Random Forest / PyTorch in work.
- *agentic workflow*: **JD-conditional** — only if the JD itself uses "agent/agentic".

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
- Source: FPT quant-finance work (ML on Vietnamese equities — see Finance / Quant).

### Finance / Quant
Financial Markets, Equities, Stock Prediction, Quantitative Finance,
Trading Strategy, Algorithmic Trading, Market Research, Time Series Analysis,
Feature Engineering, Macroeconomic Analysis
- Source: FPT — a Random-Forest trading model on Vietnamese equities (quant
  finance, not telecom). NO `Backtesting` (it wasn't backtested) and NO
  `Financial Modeling` (that means DCF/valuation; this was ML/predictive modeling
  on financial data).

### Baseline tools (universal — fill leftover skill-row space only)
Microsoft Office, Microsoft Word, Microsoft Excel, Microsoft PowerPoint,
Microsoft Outlook, Microsoft 365, Google Workspace, Windows
- Universal, no project source needed. Low priority: only add after every
  JD-relevant tech is already in a row; never crowd out impressive tech.
  (Excel + Windows 11 also appear above where a JD signals them specifically.)

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
Verilog, SystemVerilog, Digital Logic, FPGA, Intel Cyclone V,
Intel Quartus Prime Lite
- Source: FSU Engineering Tools Lab coursework.

---

## FORBIDDEN (never put on the page)

> This FORBIDDEN list is the single source of truth, applied by the model from
> `references/honesty-rules.md` during the tailor (nothing lints it now). The
> save-hook still auto-checks number-traceability; the judgment cases (category
> relabeling, attribution) stay with you.

- **Tech Khoa hasn't touched:** Java, Kubernetes, Rust, Go, .NET, Angular, Vue,
  Solana, Spring. (If a genuinely defensible source ever emerges, move it up and
  note the source — until then, off-limits.)
- **Scale Khoa didn't operate at:** large-scale, production-grade, high-throughput.
- **Resume buzzwords:** spearheaded, leveraged, owned, world-class, 10x,
  best-in-class, synergize.

(Note: "Honors Program" in Education is real and confirmed — keep it.)
