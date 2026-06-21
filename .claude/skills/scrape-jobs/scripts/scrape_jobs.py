#!/usr/bin/env python3
"""
scrape_jobs.py — walk a filtered simplify.jobs list and save each job's
Requirements + Responsibilities to jobDescription/<Company>.txt, verbatim.

How it works (fully deterministic — no LLM, no fragile DOM scraping):
  1. Open a headed Chromium with a PERSISTENT profile (log into simplify.jobs
     once; the session is reused on every later run).
  2. Navigate to the filtered URL and capture the page's own Typesense
     `multi_search` request — this encodes your exact filters (and, when logged
     in, the excludeApplied exclusion).
  3. Replay that query with pagination to collect the first --limit job IDs.
  4. For each job, GET api.simplify.jobs/v2/job-posting/:id/<id>/company and read
     the structured `requirements` / `responsibilities` arrays.
  5. Write jobDescription/<Company>.txt in the same format as the existing files.

Filters are printed at the start of every run (transparency).

Run OUTSIDE the Claude sandbox (needs network + the WSLg display):
  .venv/bin/python .claude/skills/scrape-jobs/scripts/scrape_jobs.py
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit, parse_qs

from playwright.sync_api import sync_playwright, Response, Page, BrowserContext

# ----- paths -------------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parents[1]          # .../skills/scrape-jobs
PROFILE_DIR = SKILL_DIR / ".profile"                     # persistent login (gitignored)
DEBUG_DIR = SKILL_DIR / ".debug"                         # discovery dumps (gitignored)

DETAIL_URL = "https://api.simplify.jobs/v2/job-posting/:id/{job_id}/company"

DEFAULT_URL = (
    "https://simplify.jobs/jobs?state=United%20States&country=United%20States"
    "&category=Data%20Engineering%3BData%20Management%3BAI%20%26%20Machine%20Learning"
    "%3BFrontend%20Engineering%3BDevOps%20%26%20Infrastructure%3BElectrical%20Engineering"
    "%3BFull-Stack%20Engineering%3BApplied%20Machine%20Learning%3BData%20Science"
    "%3BUI%2FUX%20%26%20Design%3BData%20Analysis%3BAI%20Research"
    "%3BAI%2FML%2FGenAI%20Engineering%3BAI%2FML%20Engineering%20Management"
    "%3BBackend%20Engineering%3BSoftware%20Engineering"
    "&education=Bachelor%27s%3BAssociate%27s%3BCertificate"
    "&seasons=Summer%202027%3BFall%202026%3BSpring%202026"
    "&excludeApplied=true&jobType=Internship"
)


def log(msg: str) -> None:
    print(msg, flush=True)


# ----- filters (transparency) --------------------------------------------------
FILTER_LABELS: dict[str, str] = {
    "state": "State",
    "country": "Country",
    "category": "Categories",
    "education": "Education",
    "seasons": "Seasons",
    "jobType": "Job type",
    "excludeApplied": "Exclude already-applied",
    "experienceLevel": "Experience level",
    "compensation": "Compensation",
    "query": "Keyword",
}


def decode_filters(url: str) -> list[tuple[str, list[str]]]:
    """Turn the (URL-encoded, ';'-joined) query string into readable filters."""
    q = parse_qs(urlsplit(url).query, keep_blank_values=True)
    out: list[tuple[str, list[str]]] = []
    for key, vals in q.items():
        if key == "jobId":  # a selection, not a filter
            continue
        raw = vals[0] if vals else ""
        parts = [s.strip() for s in raw.split(";") if s.strip()]
        if not parts and raw:
            parts = [raw]
        out.append((FILTER_LABELS.get(key, key), parts))
    return out


def print_filters(url: str) -> list[tuple[str, list[str]]]:
    filt = decode_filters(url)
    log("Active simplify.jobs filters for this scrape (transparent):")
    for label, parts in filt:
        log(f"  • {label}: {', '.join(parts) if parts else '(on)'}")
    log("")
    return filt


# ----- small helpers -----------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")


def html_to_text(raw: str) -> str:
    """Minimal HTML -> readable text (fallback only, when no parsed lists exist)."""
    if not raw:
        return ""
    raw = re.sub(r"(?i)</(p|div|li|tr|h[1-6]|ul|ol)>", "\n", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)<li[^>]*>", "• ", raw)
    text = _TAG_RE.sub("", raw)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text)
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def detect_logged_in(page: Page) -> bool:
    """Best-effort: simplify keeps a JWT (eyJ…) once you sign in. Check the
    common client-side stores so we continue the instant login lands."""
    try:
        return bool(
            page.evaluate(
                "() => { const jwt = /eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\./;"
                " try {"
                "  for (const s of [localStorage, sessionStorage]) {"
                "    for (const v of Object.values(s)) if (jwt.test(v||'')) return true; }"
                "  if (jwt.test(document.cookie||'')) return true;"
                " } catch(e){}"
                " return false; }"
            )
        )
    except Exception:
        return False


def wait_for_login(page: Page, max_wait: int) -> bool:
    """Give the user a window to log in. Returns True if a session is detected."""
    if max_wait <= 0:
        return detect_logged_in(page)
    log(
        f"\n=== Log into simplify.jobs in the open window (up to {max_wait}s).        ===\n"
        "=== This applies excludeApplied + your personalized view. Already logged ===\n"
        "=== in? It continues immediately. Don't need it? It proceeds anyway.     ===\n"
    )
    deadline = time.time() + max_wait
    while time.time() < deadline:
        if detect_logged_in(page):
            log("Login detected.")
            return True
        time.sleep(2)
    log("No login detected — proceeding anonymously (excludeApplied not personalized).")
    return False


# ----- list (Typesense multi_search) -------------------------------------------
def capture_list_query(page: Page, url: str) -> tuple[str, dict[str, Any]]:
    """Navigate to the filtered URL and grab the page's own multi_search request.

    Returns (typesense_url_with_api_key, search0_body). search0_body is the first
    of the multi_search 'searches' — the actual job-list query, filters included.
    """
    with page.expect_response(
        lambda r: "multi_search" in r.url and r.request.method == "POST",
        timeout=45000,
    ) as info:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
    resp: Response = info.value
    body: dict[str, Any] = json.loads(resp.request.post_data or "{}")
    searches = cast("list[Any]", body.get("searches") or [])
    if not searches:
        raise RuntimeError("multi_search captured but had no 'searches' body.")
    return resp.url, cast("dict[str, Any]", searches[0])


def fetch_list(
    ctx: BrowserContext, ts_url: str, search0: dict[str, Any], limit: int
) -> list[dict[str, Any]]:
    """Replay the job-list query with pagination until we have `limit` docs."""
    docs: list[dict[str, Any]] = []
    per_page = min(max(limit, 1), 100)
    page_n = 1
    found: int | None = None
    while len(docs) < limit:
        s = dict(search0)
        s["per_page"] = per_page
        s["page"] = page_n
        r = ctx.request.post(
            ts_url,
            data=json.dumps({"searches": [s]}),
            headers={"content-type": "text/plain"},
        )
        if r.status != 200:
            log(f"  list page {page_n}: HTTP {r.status} — stopping pagination.")
            break
        payload = cast("dict[str, Any]", r.json())
        results = cast("list[Any]", payload.get("results") or [{}])
        res = cast("dict[str, Any]", results[0])
        hits = cast("list[Any]", res.get("hits") or [])
        fval = res.get("found")
        if isinstance(fval, int):
            found = fval
        for h in hits:
            if not isinstance(h, dict):
                continue
            doc = cast("dict[str, Any]", h).get("document")
            if isinstance(doc, dict):
                docs.append(cast("dict[str, Any]", doc))
        if not hits:
            break
        if found is not None and len(docs) >= found:
            break
        page_n += 1
    if found is not None:
        log(f"Filtered list: {found} jobs match; pulled {len(docs[:limit])} candidates.")
    return docs[:limit]


# ----- detail (job-posting JSON) -----------------------------------------------
def fetch_detail(ctx: BrowserContext, job_id: str) -> dict[str, Any] | None:
    r = ctx.request.get(
        DETAIL_URL.format(job_id=job_id),
        headers={"referer": "https://simplify.jobs/", "origin": "https://simplify.jobs"},
    )
    if r.status != 200:
        return None
    try:
        return cast("dict[str, Any]", r.json())
    except Exception:
        return None


def clean_lines(items: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(items, list):
        return out
    for it in cast("list[Any]", items):
        s = (it if isinstance(it, str) else str(it)).strip()
        if s:
            out.append(s)
    return out


def format_job_text(detail: dict[str, Any]) -> str:
    """Build the <Company>.txt body: Requirements then Responsibilities (verbatim)."""
    reqs = clean_lines(detail.get("requirements"))
    resps = clean_lines(detail.get("responsibilities"))
    sections: list[str] = []
    if reqs:
        sections.append("Requirements\n" + "\n".join(reqs))
    if resps:
        sections.append("Responsibilities\n" + "\n".join(resps))
    if not sections:
        # Fallback: no parsed lists — keep the file useful via the raw description.
        body = html_to_text(str(detail.get("description") or "")).strip()
        if body:
            sections.append("Description\n" + body)
    return ("\n".join(sections)).strip() + "\n"


# ----- naming + duplicate detection --------------------------------------------
# Words stripped from the role part of a filename (they add no signal).
ROLE_NOISE = {
    "intern", "interns", "internship", "internships", "coop", "co", "op",
    "summer", "fall", "spring", "winter", "program", "months", "month",
    "the", "a", "an", "of", "for", "and", "to", "in",
}
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")


def _word_slug(text: str, max_words: int) -> str:
    """Lowercase-dedup words (drop noise/years), keep order, join with '_'."""
    words: list[str] = []
    seen: set[str] = set()
    for raw in re.split(r"[^A-Za-z0-9]+", text):
        if not raw:
            continue
        key = raw.lower()
        if key in ROLE_NOISE or _YEAR_RE.match(key) or key in seen:
            continue
        seen.add(key)
        words.append(raw)
        if len(words) >= max_words:
            break
    return "_".join(words)


def make_filename(company: str, title: str) -> str:
    """Descriptive `<Company>_<Role>` stem, e.g. Tesla_Industrial_Design_Studio."""
    comp = _word_slug(company, max_words=4) or "Company"
    role = _word_slug(title, max_words=7)
    stem = f"{comp}_{role}".strip("_") if role else comp
    return stem or "job"


_FP_WS = re.compile(r"\s+")


def content_fingerprint(detail: dict[str, Any]) -> str:
    """Hash of (Requirements+Responsibilities) AND the full description.

    Two postings are duplicates only when BOTH match — simplify occasionally
    lists the same job twice; we keep just one copy.
    """
    summary = "\n".join(
        clean_lines(detail.get("requirements")) + clean_lines(detail.get("responsibilities"))
    )
    full = html_to_text(str(detail.get("description") or ""))

    def norm(t: str) -> str:
        return _FP_WS.sub(" ", t).strip().lower()

    return hashlib.sha1(f"{norm(summary)}||{norm(full)}".encode("utf-8")).hexdigest()


# ----- discover (debugging) ----------------------------------------------------
class ApiBuffer:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def on_response(self, response: Response) -> None:
        try:
            url = response.url
            if "simplify" not in url:
                return
            ct = (response.headers or {}).get("content-type", "")
            if "json" not in ct and "text" not in ct:
                return
            try:
                body: Any = response.json() if "json" in ct else response.text()
            except Exception:
                return
            self.events.append(
                {"url": url, "status": response.status, "method": response.request.method,
                 "content_type": ct, "body": body}
            )
        except Exception:
            pass


def discover(page: Page, buf: ApiBuffer) -> None:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    (DEBUG_DIR / "page.html").write_text(page.content(), encoding="utf-8")
    try:
        page.screenshot(path=str(DEBUG_DIR / "screenshot.png"))
    except Exception:
        pass
    with (DEBUG_DIR / "network.jsonl").open("w", encoding="utf-8") as f:
        for e in buf.events:
            b = e["body"]
            snip = (b if isinstance(b, str) else json.dumps(b))[:40000]
            f.write(json.dumps({k: e[k] for k in ("url", "status", "method", "content_type")}
                               | {"body_snippet": snip}) + "\n")
    log(f"Discovery bundle written to {DEBUG_DIR} ({len(buf.events)} simplify responses).")


# ----- orchestration -----------------------------------------------------------
def build_browser(p: Any, headless: bool) -> BrowserContext:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=headless,
        viewport={"width": 1500, "height": 1000},
        args=["--disable-blink-features=AutomationControlled"],
    )


def scrape(ctx: BrowserContext, page: Page, args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Open simplify FIRST: the user needs a page to sign into, and the auth JWT
    # lives on this origin (so login detection can see it).
    log("Opening simplify.jobs in the window ...")
    page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
    wait_for_login(page, 0 if args.no_login else args.login_wait)

    log("Capturing the filtered job-list query ...")
    ts_url, search0 = capture_list_query(page, args.url)
    # The app only adds a Typesense negation (`:!=`) to exclude already-applied
    # postings when you're logged in; anonymous sessions get the full list.
    excl = ":!=" in str(search0.get("filter_by", ""))
    log(f"  excludeApplied applied to query: {'yes' if excl else 'no (full filtered list)'}")

    # Over-fetch a candidate pool so duplicate/skip removals don't shrink the result.
    pool_size = min(max(args.limit * 3, args.limit + 20), 300)
    docs = fetch_list(ctx, ts_url, search0, pool_size)
    if not docs:
        log("No jobs returned from the list query.")
        return 1

    pre_existing = {p.name for p in out_dir.glob("*.txt")}  # present before this run
    seen_fps: set[str] = set()                               # content de-dup within run
    used_names: set[str] = set()                             # avoid clobber within run
    written: list[dict[str, str]] = []
    n_dup = n_exist = n_fail = 0

    for doc in docs:
        if len(written) >= args.limit:
            break
        job_id = str(doc.get("id") or "")
        company = (str(doc.get("company_name") or "").strip() or "Unknown")
        title = str(doc.get("title") or "").strip()
        if not job_id:
            continue

        detail = fetch_detail(ctx, job_id)
        if not detail:
            n_fail += 1
            log(f"  {company} — {title[:55]}: detail fetch failed.")
            continue

        fp = content_fingerprint(detail)
        if fp in seen_fps:
            n_dup += 1
            log(f"  {company} — {title[:55]}: duplicate posting — skipped.")
            continue
        seen_fps.add(fp)

        stem = make_filename(company, title)
        fname = f"{stem}.txt"
        if fname in pre_existing and not args.force:
            n_exist += 1
            log(f"  {company} — {title[:55]}: {fname} exists — skipped (use --force).")
            continue
        n = 2  # distinct role whose stem collides with one already written this run
        while fname in used_names:
            fname = f"{stem}_{n}.txt"
            n += 1
        used_names.add(fname)

        (out_dir / fname).write_text(format_job_text(detail), encoding="utf-8")
        nreq = len(clean_lines(detail.get("requirements")))
        nres = len(clean_lines(detail.get("responsibilities")))
        log(f"[{len(written) + 1}/{args.limit}] {company} — {title[:48]}  →  {fname}  ({nreq} req, {nres} resp)")
        written.append({"company": company, "title": title, "id": job_id, "file": fname})

    # transparent run manifest (kept out of jobDescription/ so /tailor ignores it)
    (SKILL_DIR / "last_run.json").write_text(
        json.dumps(
            {"url": args.url, "filters": decode_filters(args.url), "limit": args.limit,
             "excludeApplied": excl, "written": written,
             "skipped": {"duplicate": n_dup, "exists": n_exist, "detail_failed": n_fail}},
            indent=2,
        ),
        encoding="utf-8",
    )
    log(f"\nDone: {len(written)} written; skipped {n_dup} duplicate, "
        f"{n_exist} existing, {n_fail} failed → {out_dir}/")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=DEFAULT_URL, help="filtered simplify.jobs URL")
    ap.add_argument("--limit", type=int, default=50, help="max jobs to scrape")
    ap.add_argument("--out", default="jobDescription", help="output dir for <Company>.txt")
    ap.add_argument("--force", action="store_true", help="overwrite existing <Company>.txt")
    ap.add_argument("--no-login", action="store_true", help="skip the login wait (anonymous)")
    ap.add_argument("--login-wait", type=int, default=150, help="seconds to wait for login")
    ap.add_argument("--headless", action="store_true", help="no window (only once logged in)")
    ap.add_argument("--discover", action="store_true", help="dump page/API structure and exit")
    args = ap.parse_args()

    print_filters(args.url)
    with sync_playwright() as p:
        ctx = build_browser(p, headless=args.headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            if args.discover:
                buf = ApiBuffer()
                ctx.on("response", buf.on_response)
                page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
                wait_for_login(page, 0 if args.no_login else args.login_wait)
                page.wait_for_timeout(4000)
                discover(page, buf)
                return 0
            return scrape(ctx, page, args)
        finally:
            ctx.close()


if __name__ == "__main__":
    sys.exit(main())
