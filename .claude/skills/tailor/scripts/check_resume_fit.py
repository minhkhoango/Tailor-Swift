#!/usr/bin/env python3
"""Deterministic 1-page resume fit checker for the /tailor skill.

Measures two things on a compiled ``Khoa_Ngo_resume.pdf`` (paired with its
``resume.tex``) — *deterministically*, by reading the rendered word boxes out
of the PDF with pdfplumber:

1. **Fullness** — how far down the page the content reaches (target 95-100%;
   pack it as high as possible without spilling to a 2nd page).
2. **Spillover** — any bullet whose *last rendered line* carries <= 4 words
   (a <= 2-word dangling line is the worst case and must be fixed).

It only DETECTS. It never edits the .tex. During /tailor, Claude acts on the
report (LIGHTLY rewords an orphan-flagged bullet so it stops dangling, or adds a
whole pool project/bullet when under-full) — it never heavy-rewrites or shortens
a bullet, and it keeps JD keywords and locked facts intact. UNDERFULL is only
actionable while there is still content to add: once all bullets + up to 5 skill
rows are in and it is still < 0.95, that is acceptable.

Run from the repo root (the script lives in .claude/skills/tailor/scripts/):
    .venv/bin/python .claude/skills/tailor/scripts/check_resume_fit.py <company>
    .venv/bin/python .claude/skills/tailor/scripts/check_resume_fit.py --all

Exit codes (mirrors build_resume.py):
    0  every analyzed resume is OK (1 page, 95-100% full, no <=4-word spillover)
    1  ran fine but at least one resume is actionable (under/over-full / spillover / multipage)
    2  environment or usage error (pdfplumber missing, no args, missing files)
"""

import argparse
import importlib.util
import json
import re
import string
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

# Shared tex parsing lives in tex_parse (same dir; on sys.path when run as a script).
from tex_parse import (  # noqa: E402
    extract_skill_rows,
    replace_href as _replace_href,
    resume_items as extract_resume_items,
)
from paths import OUTPUT

JOBNAME = "Khoa_Ngo_resume"

# --- Page geometry (US Letter, points; 1in = 72pt) ---
PAGE_W_PT = 612.0
PAGE_H_PT = 792.0

# --- Printable band (the template shifts \topmargin -0.5in, so ~0.5in margins).
# These two constants are the only values that may need one-time calibration;
# run `--calibrate <company>` against a visually-full resume to back-solve them.
PRINTABLE_TOP_PT = 36.0     # ~0.5in from the paper top
PRINTABLE_BOTTOM_PT = 756.0  # 792 - 36 ; ~0.5in from the paper bottom

# --- Targets / thresholds ---
FULLNESS_TARGET_LOW = 0.95   # below this is UNDERFULL (add a whole project/bullet)
FULLNESS_TARGET_HIGH = 1.00  # above this means content spilled into the bottom margin
SPILLOVER_MAX_WORDS = 4       # a last line with <= this many words is flagged
MIN_LINES_TO_FLAG = 2         # only wrapped (>1 line) bullets can spill

# --- Alignment tuning ---
MATCH_RATIO_THRESHOLD = 0.55  # min fraction of bullet tokens matched to trust a bullet
LINE_CLUSTER_EPS_PT = 3.0     # words within this top-gap are the same physical line
MAX_W_SKIP = 8                # rendered words tolerated between two bullet-token matches

_PUNCT = string.punctuation + "•–—"  # incl. bullet, en/em dash
_MARKER_TEXTS = {"", "•", "|", "$", "bullet"}


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    line_id: int = -1


@dataclass
class Page:
    width: float
    height: float
    words: list[Word]


@dataclass
class AlignResult:
    matched_word_indices: list[int]
    end_index: int
    match_ratio: float


@dataclass
class BulletReport:
    index: int
    preview: str
    rendered: bool
    n_lines: int
    last_line_word_count: int
    match_ratio: float
    flagged: bool


@dataclass
class BulletFields:
    rendered: bool
    n_lines: int
    last_line_word_count: int
    match_ratio: float
    flagged: bool


@dataclass
class SkillRowReport:
    category: str
    rendered: bool
    n_lines: int
    wrapped: bool   # True when the row spans more than one rendered line


@dataclass
class FitReport:
    company: str
    page_count: int
    fullness: Optional[float]  # None when page_count != 1
    content_top: Optional[float]
    content_bottom: Optional[float]
    bullets: list[BulletReport]
    verdict: str
    notes: list[str] = field(default_factory=list[str])
    skill_rows: list[SkillRowReport] = field(default_factory=list[SkillRowReport])


# --------------------------------------------------------------------------- #
# Pure core: tex parsing
# (match_braces / strip_tex_comments / replace_href / resume_items now live in
#  tex_parse; imported above. normalize_bullet stays here -- it is alignment-
#  specific tokenization for matching against rendered PDF words.)
# --------------------------------------------------------------------------- #
def normalize_bullet(raw_tex: str) -> list[str]:
    """Tex bullet body -> lowercased token list for alignment against the PDF."""
    s = _replace_href(raw_tex)
    # Unescape LaTeX literals (mirror the Step 9b list).
    for a, b in (("\\%", "%"), ("\\$", "$"), ("\\&", "&"),
                 ("\\#", "#"), ("\\_", "_"), ("~", " ")):
        s = s.replace(a, b)
    s = s.replace("{,}", "")           # 4{,}000 -> 4000
    s = s.replace("---", "-").replace("--", "-")
    s = re.sub(r"\\[A-Za-z]+", " ", s)  # strip remaining control sequences
    s = s.replace("{", " ").replace("}", " ").replace("$", " ").replace("\\", " ")
    tokens: list[str] = []
    for tok in s.lower().split():
        tok = tok.strip(_PUNCT)
        if not tok:
            continue
        tokens.append(tok)
    return tokens


# --------------------------------------------------------------------------- #
# Pure core: rendered-word handling
# --------------------------------------------------------------------------- #
def normalize_pdf_word(text: str) -> str:
    t = unicodedata.normalize("NFKD", text)
    t = t.replace("–", "-").replace("—", "-")
    t = t.lower().strip(_PUNCT)
    return t


def assign_line_ids_by_y(words: list[Word], eps: float = LINE_CLUSTER_EPS_PT) -> list[Word]:
    """Return new Words with line_id assigned by clustering on `top`."""
    if not words:
        return []
    tops = sorted({round(w.top, 1) for w in words})
    mapping = {tops[0]: 0}
    cid = 0
    prev = tops[0]
    for t in tops[1:]:
        if t - prev > eps:
            cid += 1
        mapping[t] = cid
        prev = t
    return [Word(w.text, w.x0, w.x1, w.top, w.bottom, mapping[round(w.top, 1)])
            for w in words]


def strip_markers(words: list[Word]) -> list[Word]:
    """Drop bullet/pipe/dollar glyphs and single non-alnum marks."""
    out: list[Word] = []
    for w in words:
        n = normalize_pdf_word(w.text)
        if n in _MARKER_TEXTS:
            continue
        if len(n) == 1 and not n.isalnum():
            continue
        out.append(w)
    return out


def tokens_match(b: str, w: str) -> bool:
    if not b or not w:
        return False
    if b == w:
        return True
    b2, w2 = b.replace("-", ""), w.replace("-", "")
    if b2 and b2 == w2:
        return True
    if len(b2) >= 4 and len(w2) >= 4 and (b2.startswith(w2) or w2.startswith(b2)):
        return True
    bn = re.sub(r"[^0-9]", "", b)
    wn = re.sub(r"[^0-9]", "", w)
    if bn and bn == wn:
        return True
    return False


def align_bullet(bullet_tokens: list[str], words: list[Word], norm_words: list[str],
                 start_hint: int = 0) -> AlignResult:
    """Sequentially align a bullet's tokens to the rendered word stream."""
    i = start_hint
    j = 0
    matched: list[int] = []
    skips = 0
    started = False  # lock-on scan (before first match) is unbounded
    nB, nW = len(bullet_tokens), len(words)
    while j < nB and i < nW:
        if tokens_match(bullet_tokens[j], norm_words[i]):
            matched.append(i)
            i += 1
            j += 1
            skips = 0
            started = True
        elif started and j + 1 < nB and tokens_match(bullet_tokens[j + 1], norm_words[i]):
            j += 1  # bullet token absent in render; skip it
        else:
            i += 1
            if started:
                skips += 1
                if skips > MAX_W_SKIP:
                    break
    ratio = len(matched) / max(1, nB)
    end = (matched[-1] + 1) if matched else start_hint
    return AlignResult(matched, end, ratio)


def detect_spillover(bullet_tokens: list[str], words: list[Word], norm_words: list[str],
                     start_hint: int) -> tuple[BulletFields, int]:
    """Return (BulletFields, new_hint) for one bullet."""
    ar = align_bullet(bullet_tokens, words, norm_words, start_hint)
    if ar.match_ratio < MATCH_RATIO_THRESHOLD or not ar.matched_word_indices:
        return (BulletFields(False, 0, 0, ar.match_ratio, False), start_hint)
    matched = [words[k] for k in ar.matched_word_indices]
    line_ids = sorted({w.line_id for w in matched})
    n_lines = len(line_ids)
    last = line_ids[-1]
    last_count = sum(1 for w in matched if w.line_id == last)
    flagged = (n_lines >= MIN_LINES_TO_FLAG and last_count <= SPILLOVER_MAX_WORDS)
    return (BulletFields(True, n_lines, last_count, ar.match_ratio, flagged), ar.end_index)


def detect_skill_wrap(rows: list[tuple[str, str]], words: list[Word],
                      norm_words: list[str], start_hint: int) -> list[SkillRowReport]:
    """Flag any Technical-Skills row that wraps to more than one rendered line.

    Each row's tokens (category label + content) are aligned against the word
    stream with a threaded hint anchored on the category, then the distinct
    rendered line_ids it touches are counted. >1 line == WRAP (advisory).
    """
    out: list[SkillRowReport] = []
    hint = start_hint
    for category, content in rows:
        toks = normalize_bullet(f"{category} {content}")
        if not toks:
            out.append(SkillRowReport(category, False, 0, False))
            continue
        ar = align_bullet(toks, words, norm_words, hint)
        if ar.match_ratio < MATCH_RATIO_THRESHOLD or not ar.matched_word_indices:
            out.append(SkillRowReport(category, False, 0, False))
            continue
        line_ids = {words[k].line_id for k in ar.matched_word_indices}
        n_lines = len(line_ids)
        out.append(SkillRowReport(category, True, n_lines, n_lines > 1))
        hint = ar.end_index
    return out


# --------------------------------------------------------------------------- #
# Pure core: fullness + verdict + orchestration
# --------------------------------------------------------------------------- #
def compute_fullness(page: Page,
                     printable_top: float = PRINTABLE_TOP_PT,
                     printable_bottom: float = PRINTABLE_BOTTOM_PT) -> tuple[float, float, float]:
    if not page.words:
        return 0.0, 0.0, 0.0
    content_top = min(w.top for w in page.words)
    content_bottom = max(w.bottom for w in page.words)
    band = printable_bottom - printable_top
    fullness = (content_bottom - printable_top) / band
    return fullness, content_top, content_bottom


def build_verdict(page_count: int, fullness: Optional[float],
                  bullets: list[BulletReport]) -> tuple[str, list[str]]:
    notes: list[str] = []
    if page_count >= 2:
        return "MULTIPAGE", notes
    spill = [b for b in bullets if b.flagged]
    if spill:
        notes.append(f"{len(spill)} bullet(s) with <= {SPILLOVER_MAX_WORDS}-word last line")
    if fullness is not None and fullness > 1.0:
        return "OVERFULL", notes
    if spill:
        return "SPILLOVER", notes
    if fullness is not None and fullness < FULLNESS_TARGET_LOW:
        return "UNDERFULL", notes
    if fullness is not None and fullness > FULLNESS_TARGET_HIGH:
        return "OVERFULL", notes
    return "OK", notes


def analyze_from_pages(tex: str, pages: list[Page], company: str) -> FitReport:
    """Pure orchestrator: tex string + extracted Pages -> FitReport."""
    page_count = len(pages)
    raw_items = extract_resume_items(tex)
    notes: list[str] = []

    if page_count != 1:
        return FitReport(company, page_count, None, None, None, [],
                         *build_verdict(page_count, None, []))

    page = pages[0]
    words = strip_markers(page.words)
    norm_words = [normalize_pdf_word(w.text) for w in words]

    bullets: list[BulletReport] = []
    hint = 0
    for idx, raw in enumerate(raw_items, start=1):
        toks = normalize_bullet(raw)
        preview = " ".join(toks)[:40]
        if not toks:
            bullets.append(BulletReport(idx, preview, False, 0, 0, 0.0, False))
            continue
        fields, hint = detect_spillover(toks, words, norm_words, hint)
        bullets.append(BulletReport(idx, preview, fields.rendered,
                                    fields.n_lines, fields.last_line_word_count,
                                    fields.match_ratio, fields.flagged))

    skill_rows = detect_skill_wrap(extract_skill_rows(tex), words, norm_words, hint)

    fullness, c_top, c_bottom = compute_fullness(page)
    if c_top - PRINTABLE_TOP_PT > 24:
        notes.append(f"unexpected top gap ({c_top:.0f}pt); PRINTABLE_TOP may need calibration")
    n_skipped = sum(1 for b in bullets if not b.rendered)
    if n_skipped:
        notes.append(f"{n_skipped} bullet(s) skipped (low match confidence)")
    n_wrap = sum(1 for s in skill_rows if s.wrapped)
    if n_wrap:
        wrapped = ", ".join(s.category for s in skill_rows if s.wrapped)
        notes.append(f"{n_wrap} skill row(s) WRAP to >1 line: {wrapped} (prune to fit)")

    verdict, vnotes = build_verdict(page_count, fullness, bullets)
    notes.extend(vnotes)
    return FitReport(company, page_count, fullness, c_top, c_bottom,
                     bullets, verdict, notes, skill_rows)


# --------------------------------------------------------------------------- #
# Impure wrappers
# --------------------------------------------------------------------------- #
def check_deps() -> Optional[str]:
    """Return an install-hint string if pdfplumber is unavailable, else None."""
    if importlib.util.find_spec("pdfplumber") is None:
        return ("pdfplumber not installed - run: "
                "python3 -m venv .venv && .venv/bin/pip install -r requirements.txt "
                "(then run this script with .venv/bin/python)")
    return None


def extract_pages(pdf_path: Path) -> list[Page]:
    import pdfplumber  # untyped third-party (reportMissingTypeStubs off in pyrightconfig)

    pages: list[Page] = []
    pdf_open: Any = pdfplumber.open
    with pdf_open(str(pdf_path)) as pdf:
        for p in pdf.pages:
            raw: list[dict[str, Any]] = p.extract_words(use_text_flow=True)
            words = [Word(str(w["text"]), float(w["x0"]), float(w["x1"]),
                          float(w["top"]), float(w["bottom"])) for w in raw]
            pages.append(Page(float(p.width), float(p.height), assign_line_ids_by_y(words)))
    return pages


def load_tex(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def analyze_company(company: str) -> FitReport:
    out_dir = OUTPUT / company
    pdf = out_dir / f"{JOBNAME}.pdf"
    tex = out_dir / "resume.tex"
    if not pdf.exists():
        raise FileNotFoundError(f"missing PDF: {pdf}")
    if not tex.exists():
        raise FileNotFoundError(f"missing tex: {tex}")
    return analyze_from_pages(load_tex(tex), extract_pages(pdf), company)


# --------------------------------------------------------------------------- #
# Reporting / CLI
# --------------------------------------------------------------------------- #
def format_report(r: FitReport) -> str:
    """One headline line, plus ONLY the problematic items when something's wrong.

    Clean (verdict OK, no spillover FLAG, no skill-row WRAP) collapses to a single
    line -- the headline numbers carry everything the model needs. When anything is
    actionable, the headline is followed by the FLAG bullets / WRAP rows / notes
    the model must target (never the OK bullets, which were the bulk of the cost).
    """
    n_flag = sum(1 for b in r.bullets if b.flagged)
    n_wrap = sum(1 for s in r.skill_rows if s.wrapped)
    n_skip = sum(1 for b in r.bullets if not b.rendered)
    full = "n/a" if r.fullness is None else f"{r.fullness:.2f}"
    skills_tag = "skills fit" if n_wrap == 0 else f"{n_wrap} skill WRAP"
    head = (f"{r.company}: {r.verdict}  {r.page_count}pg  fullness {full}"
            f"  spillover {n_flag}  {skills_tag}")
    if n_skip:
        head += f"  ({n_skip} low-confidence)"

    if r.verdict == "OK" and n_flag == 0 and n_wrap == 0:
        return head

    lines = [head]
    for b in r.bullets:
        if b.flagged:
            lines.append(f"    [{b.index:02d}] FLAG lines={b.n_lines} "
                         f"last_line_words={b.last_line_word_count}  \"{b.preview}\"")
    for s in r.skill_rows:
        if s.wrapped:
            lines.append(f"    [WRAP] lines={s.n_lines}  \"{s.category}\"")
    if r.notes:
        lines.append(f"  notes: {'; '.join(r.notes)}")
    return "\n".join(lines)


def report_to_dict(r: FitReport) -> dict[str, Any]:
    """Serialize a FitReport for machine consumers (the /tailor pipeline).

    Carries the full structured report (``asdict``), the verdict, the headline
    numbers the pipeline branches on, and the same human ``text`` the CLI prints
    -- so the caller never re-parses formatted stdout.
    """
    return {
        "company": r.company,
        "verdict": r.verdict,
        "ok": r.verdict == "OK",
        "page_count": r.page_count,
        "fullness": r.fullness,
        "spillover_flags": sum(1 for b in r.bullets if b.flagged),
        "notes": list(r.notes),
        "report": asdict(r),
        "text": format_report(r),
    }


def calibrate(company: str) -> int:
    pages = extract_pages((OUTPUT / company) / f"{JOBNAME}.pdf")
    if not pages:
        print(f"{company}: no pages", file=sys.stderr)
        return 2
    p = pages[0]
    c_top = min(w.top for w in p.words)
    c_bottom = max(w.bottom for w in p.words)
    sug_top = round(c_top - 10)  # ~first-baseline ascent pad
    sug_bottom = round((c_bottom - PRINTABLE_TOP_PT) / 0.97 + PRINTABLE_TOP_PT)
    print(f"{company}: page {p.width:.0f}x{p.height:.0f}pt")
    print(f"  content_top={c_top:.1f}  content_bottom={c_bottom:.1f}")
    print(f"  origin check: content_bottom > content_top ? {c_bottom > c_top} (expect True)")
    print("  suggested constants for a 0.97 = full reading:")
    print(f"    PRINTABLE_TOP_PT    = {float(sug_top)}")
    print(f"    PRINTABLE_BOTTOM_PT = {float(sug_bottom)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic 1-page resume fit checker.")
    ap.add_argument("company", nargs="?", help="company stem under output/")
    ap.add_argument("--all", action="store_true", help="check every output/*/")
    ap.add_argument("--calibrate", metavar="COMPANY",
                    help="print suggested PRINTABLE_* constants from a known-good resume")
    ap.add_argument("--pages", metavar="PDF",
                    help="print the page count of a PDF and exit (used by the cover-letter hook)")
    ap.add_argument("--json", metavar="COMPANY", dest="json_company",
                    help="emit one company's FitReport as JSON (used by the /tailor pipeline)")
    args = ap.parse_args()

    hint = check_deps()
    if hint:
        print(hint, file=sys.stderr)
        return 2

    if args.json_company:
        try:
            r = analyze_company(args.json_company)
        except FileNotFoundError as e:
            print(json.dumps({"company": args.json_company, "error": str(e)}))
            return 2
        print(json.dumps(report_to_dict(r)))
        return 0 if r.verdict == "OK" else 1

    if args.pages:
        try:
            print(len(extract_pages(Path(args.pages))))
            return 0
        except Exception as e:  # noqa: BLE001 - report any read failure to the caller
            print(str(e), file=sys.stderr)
            return 2

    if args.calibrate:
        try:
            return calibrate(args.calibrate)
        except FileNotFoundError as e:
            print(str(e), file=sys.stderr)
            return 2

    if args.all:
        companies = sorted(d.name for d in OUTPUT.iterdir()
                           if d.is_dir() and (d / f"{JOBNAME}.pdf").exists())
    elif args.company:
        companies = [args.company]
    else:
        ap.print_usage(sys.stderr)
        print("error: provide a <company>, --all, or --calibrate", file=sys.stderr)
        return 2

    if not companies:
        print(f"No resumes found under {OUTPUT}", file=sys.stderr)
        return 2

    worst = 0
    for c in companies:
        try:
            r = analyze_company(c)
        except FileNotFoundError as e:
            print(f"{c}:\n  error: {e}")
            worst = max(worst, 2)
            continue
        print(format_report(r))
        if r.verdict != "OK":
            worst = max(worst, 1)
    return worst


if __name__ == "__main__":
    sys.exit(main())
