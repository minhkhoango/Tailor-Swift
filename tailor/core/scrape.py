#!/usr/bin/env python3
"""Scrape feeder: simplify.jobs -> jobDescription/<Company>_<Role>.txt.

The upstream half of the pipeline `tailor scrape` drives:
**scrape -> jobDescription/<stem>.txt -> tailor -> output/<stem>/**.

Design (folded in from the old ``scrape-jobs`` skill, now config-driven):
  1. Read ``scrape.config.json`` -- a structured ``searches`` list, each a few
     readable fields (state / seasons / category ...). NO hand-edited 300-char
     URL: ``build_url`` re-encodes the simplify query from those fields.
  2. Open a headed Chromium with a PERSISTENT profile so you log into
     simplify.jobs ONCE; later runs reuse the session.
  3. Per search: navigate the built URL, capture the page's own Typesense
     ``multi_search`` POST (your exact filters + the server-side excludeApplied),
     replay it with pagination to collect candidate docs.
  4. Merge every search, de-dup by job id then by content fingerprint, GET each
     ``v2/job-posting/:id/<id>/company`` detail, and write one enriched ``.txt``:
     verbatim Requirements + Responsibilities, a fenced **Keywords** block the
     tailor LLM reads, and an ignore-marked footer with the company + job links.

Everything except the network/login is deterministic: same filters -> same files.
``run_scrape`` returns the count written; ``tailor scrape`` then runs the normal
batch over ``jobDescription/*.txt`` (skipping already-done unless ``--force``).

This is part of tailor -- NOT a Claude Code agent skill. The only state outside
the repo is ``.scrape/`` (gitignored): the persistent browser login + manifest.

Config (``scrape.config.json``, committed)::

    limit     default written files PER search (a search may override with "limit")
    login     wait for an interactive simplify login (applies excludeApplied)
    force     overwrite existing jobDescription/*.txt
    defaults  a SearchSpec every search inherits (put the big category list here once)
    searches  list of SearchSpec; each = defaults merged with its own fields (search wins)

A SearchSpec is plain fields -- state / country / seasons / category / education /
jobType / excludeApplied / mostRecent. ``build_url`` re-encodes them: list values
join with ';', booleans emit "true" (dropped when false), and the meta keys
name/limit never reach the URL. Remote is just ``state="Remote in USA"`` -- simplify
has no separate remote param.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict, cast
from urllib.parse import quote

from .paths import JOBDESC, SCRAPE_CONFIG, SCRAPE_LAST_RUN, SCRAPE_PROFILE

if TYPE_CHECKING:                                   # types only -- no runtime dep
    from playwright.sync_api import BrowserContext, Page

SIMPLIFY_JOBS_URL = "https://simplify.jobs/jobs"
DETAIL_URL = "https://api.simplify.jobs/v2/job-posting/:id/{job_id}/company"
JOB_POST_URL = "https://simplify.jobs/p/{job_id}"   # canonical fallback permalink

# Config keys that are meta (drive the run) rather than simplify URL params.
_META_KEYS = {"name", "limit"}
# Detail-JSON fields we probe for the LLM-facing keyword block, in priority order.
_KEYWORD_FIELDS = ("keywords", "skills", "key_skills", "tags", "tech_stack",
                   "techStack", "tools", "technologies")
# Detail-JSON fields we probe for the two reference links.
_COMPANY_URL_FIELDS = ("company_url", "companyWebsite", "website", "url", "homepage")
_JOB_URL_FIELDS = ("application_url", "applicationUrl", "job_url", "jobUrl",
                   "apply_url", "url", "source_url")
_IGNORE_MARKER = "---- reference only — tailor ignores below ----"


# --------------------------------------------------------------------------- #
# Config (the simple interface) -- typed, total=False so every field optional
# --------------------------------------------------------------------------- #
class SearchSpec(TypedDict, total=False):
    name: str
    state: str
    country: str
    seasons: list[str]
    category: list[str]
    education: list[str]
    jobType: str
    excludeApplied: bool
    mostRecent: bool
    limit: int


class ScrapeConfig(TypedDict):
    searches: list[SearchSpec]                      # required: the only must-have
    limit: NotRequired[int]
    login: NotRequired[bool]
    force: NotRequired[bool]
    defaults: NotRequired[SearchSpec]


class SearchBatch(TypedDict):
    """One search's collected candidates -- its own quota, its own doc list.

    Kept per-search (NOT merged into one global pool) so each search fills its
    write quota from its OWN candidates. A job both searches return is written
    once, but only counts against the search that wrote it; the other search
    keeps pulling its remaining candidates instead of silently under-delivering.
    """
    name: str
    limit: int                                      # files to write for THIS search
    docs: list[dict[str, Any]]                       # candidates, id-deduped within


def load_config(path: Path = SCRAPE_CONFIG) -> ScrapeConfig:
    """Read + sanity-check ``scrape.config.json``. Raises on missing/empty searches."""
    if not path.exists():
        raise FileNotFoundError(f"scrape config not found: {path}")
    cfg = cast("ScrapeConfig", json.loads(path.read_text(encoding="utf-8")))
    if not cfg.get("searches"):
        raise ValueError(f"{path}: no 'searches' defined")
    return cfg


def build_url(search: SearchSpec, defaults: SearchSpec) -> str:
    """Re-encode one search (defaults + its overrides) into a simplify.jobs URL.

    List values join with ';'; booleans emit ``true`` (and are dropped when
    false, mirroring the UI); meta keys (name/limit) never reach the URL. The
    result matches what the simplify frontend produces, so its captured
    ``multi_search`` carries exactly these filters.
    """
    merged: dict[str, Any] = {**defaults, **search}
    parts: list[str] = []
    for key, value in merged.items():
        if key in _META_KEYS or value is None:
            continue
        if isinstance(value, bool):
            if value:
                parts.append(f"{key}={quote('true', safe='')}")
            continue
        if isinstance(value, list):
            joined = ";".join(str(v) for v in cast("list[Any]", value))
        else:
            joined = str(value)
        if joined:
            parts.append(f"{key}={quote(joined, safe='')}")
    return f"{SIMPLIFY_JOBS_URL}?{'&'.join(parts)}"


def describe_search(search: SearchSpec, defaults: SearchSpec) -> str:
    """One-line human summary of a search's effective filters (for the run log)."""
    merged: dict[str, Any] = {**defaults, **search}
    name = str(merged.get("name") or "search")
    bits: list[str] = []
    for key in ("state", "country", "seasons", "jobType"):
        val = merged.get(key)
        if val:
            shown = ", ".join(cast("list[str]", val)) if isinstance(val, list) else str(val)
            bits.append(f"{key}={shown}")
    cats = merged.get("category")
    ncat = len(cast("list[str]", cats)) if isinstance(cats, list) else 0
    bits.append(f"{ncat} categories")
    return f"[{name}] " + "; ".join(bits)


# --------------------------------------------------------------------------- #
# HTML/text helpers
# --------------------------------------------------------------------------- #
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_FP_WS = re.compile(r"\s+")


def html_to_text(raw: str) -> str:
    """Minimal HTML -> readable text (fallback only, when no parsed lists exist)."""
    if not raw:
        return ""
    raw = re.sub(r"(?i)</(p|div|li|tr|h[1-6]|ul|ol)>", "\n", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)<li[^>]*>", "• ", raw)
    text = html.unescape(_TAG_RE.sub("", raw))
    text = _WS_RE.sub(" ", text)
    return "\n".join(ln.strip() for ln in text.splitlines() if ln.strip())


def clean_lines(items: object) -> list[str]:
    """Coerce a JSON array of strings into trimmed non-empty lines.

    Non-string elements (JSON ``null`` / number / object) are DROPPED, never
    stringified -- so a JSON ``null`` can't become the literal word "None" in the
    JD body or its content fingerprint. Anything that is not a list -> [].
    """
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for it in cast("list[Any]", items):
        if not isinstance(it, str):
            continue
        s = it.strip()
        if s:
            out.append(s)
    return out


def extract_keywords(detail: dict[str, Any]) -> list[str]:
    """First populated keyword-ish field (strings, or dicts with name/label/value).

    simplify's v2 field name is unverified offline, so we probe several aliases
    and degrade quietly to [] -- the tailor LLM simply gets no keyword block.
    """
    for field in _KEYWORD_FIELDS:
        raw = detail.get(field)
        if not isinstance(raw, list):
            continue
        kws: list[str] = []
        for it in cast("list[Any]", raw):
            if isinstance(it, str):
                s = it.strip()
            elif isinstance(it, dict):
                d = cast("dict[str, Any]", it)
                s = str(d.get("name") or d.get("label") or d.get("value") or "").strip()
            else:
                s = str(it).strip()
            if s:
                kws.append(s)
        if kws:
            # de-dup case-insensitively, keep first-seen order
            seen: set[str] = set()
            uniq: list[str] = []
            for k in kws:
                if k.lower() not in seen:
                    seen.add(k.lower())
                    uniq.append(k)
            return uniq
    return []


def _first_url(detail: dict[str, Any], fields: tuple[str, ...]) -> str:
    """First http(s) value among ``fields``, checking the top level and a nested
    ``company`` object. Probes aliases because the exact key is unverified."""
    pools: list[dict[str, Any]] = [detail]
    comp = detail.get("company")
    if isinstance(comp, dict):
        pools.append(cast("dict[str, Any]", comp))
    for pool in pools:
        for field in fields:
            val = pool.get(field)
            if isinstance(val, str) and val.startswith("http"):
                return val.strip()
    return ""


def extract_links(detail: dict[str, Any], job_id: str) -> tuple[str, str]:
    """(company_url, job_post_url). Job post falls back to the simplify permalink."""
    company = _first_url(detail, _COMPANY_URL_FIELDS)
    job = _first_url(detail, _JOB_URL_FIELDS) or JOB_POST_URL.format(job_id=job_id)
    return company, job


def format_job_text(detail: dict[str, Any], job_id: str) -> str:
    """Enriched body: Requirements + Responsibilities (verbatim), a keyword block
    the LLM reads, then an ignore-marked footer with the two links.

    Only the sections ABOVE the marker feed tailoring; the links sit below it so
    the LLM never mistakes a URL for résumé content.
    """
    reqs = clean_lines(detail.get("requirements"))
    resps = clean_lines(detail.get("responsibilities"))
    sections: list[str] = []
    if reqs:
        sections.append("Requirements\n" + "\n".join(reqs))
    if resps:
        sections.append("Responsibilities\n" + "\n".join(resps))
    if not sections:
        body = html_to_text(str(detail.get("description") or "")).strip()
        if body:
            sections.append("Description\n" + body)

    keywords = extract_keywords(detail)
    if keywords:
        sections.append("Keywords (prefer where truthful)\n" + ", ".join(keywords))

    company_url, job_url = extract_links(detail, job_id)
    footer = [_IGNORE_MARKER]
    if company_url:
        footer.append(f"Company: {company_url}")
    footer.append(f"Job post: {job_url}")
    sections.append("\n".join(footer))

    return "\n".join(sections).strip() + "\n"


def content_fingerprint(detail: dict[str, Any]) -> str:
    """Hash of (Requirements+Responsibilities) AND the full description; two
    postings are duplicates only when BOTH match."""
    summary = "\n".join(
        clean_lines(detail.get("requirements")) + clean_lines(detail.get("responsibilities"))
    )
    full = html_to_text(str(detail.get("description") or ""))

    def norm(t: str) -> str:
        return _FP_WS.sub(" ", t).strip().lower()

    return hashlib.sha1(f"{norm(summary)}||{norm(full)}".encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Filename (descriptive <Company>_<Role> stem)
# --------------------------------------------------------------------------- #
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
    """Descriptive ``<Company>_<Role>`` stem, e.g. Tesla_Industrial_Design_Studio."""
    comp = _word_slug(company, max_words=4) or "Company"
    role = _word_slug(title, max_words=7)
    stem = f"{comp}_{role}".strip("_") if role else comp
    return stem or "job"


# --------------------------------------------------------------------------- #
# Browser + login
# --------------------------------------------------------------------------- #
def detect_logged_in(page: Page) -> bool:
    """simplify keeps a JWT (eyJ…) once signed in -- scan the client-side stores."""
    try:
        return bool(page.evaluate(
            "() => { const jwt = /eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\./;"
            " try {"
            "  for (const s of [localStorage, sessionStorage]) {"
            "    for (const v of Object.values(s)) if (jwt.test(v||'')) return true; }"
            "  if (jwt.test(document.cookie||'')) return true;"
            " } catch(e){}"
            " return false; }"
        ))
    except Exception:
        return False


def wait_for_login(page: Page, max_wait: int) -> bool:
    """Give the user a window to log in. Returns True once a session is detected."""
    if max_wait <= 0:
        return detect_logged_in(page)
    print(f"\n=== Log into simplify.jobs in the open window (up to {max_wait}s).        ===\n"
          "=== This applies excludeApplied + your personalized view. Already logged ===\n"
          "=== in? It continues immediately. Don't need it? It proceeds anyway.     ===\n",
          flush=True)
    deadline = time.time() + max_wait
    while time.time() < deadline:
        if detect_logged_in(page):
            print("Login detected.", flush=True)
            return True
        time.sleep(2)
    print("No login detected — proceeding anonymously (excludeApplied not personalized).",
          flush=True)
    return False


# --------------------------------------------------------------------------- #
# List (Typesense multi_search) + detail
# --------------------------------------------------------------------------- #
def capture_list_query(page: Page, url: str) -> tuple[str, dict[str, Any]]:
    """Navigate the built URL and grab the page's own multi_search POST.

    Returns (typesense_url_with_api_key, search0_body) -- the first of the
    multi_search 'searches', i.e. the job-list query with filters baked in.
    """
    with page.expect_response(
        lambda r: "multi_search" in r.url and r.request.method == "POST",
        timeout=45000,
    ) as info:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
    resp = info.value
    body: dict[str, Any] = json.loads(resp.request.post_data or "{}")
    searches = cast("list[Any]", body.get("searches") or [])
    if not searches:
        raise RuntimeError("multi_search captured but had no 'searches' body.")
    return resp.url, cast("dict[str, Any]", searches[0])


def fetch_list(ctx: BrowserContext, ts_url: str, search0: dict[str, Any],
               limit: int) -> list[dict[str, Any]]:
    """Replay the job-list query with pagination until we have ``limit`` docs."""
    docs: list[dict[str, Any]] = []
    per_page = min(max(limit, 1), 100)
    page_n = 1
    found: int | None = None
    while len(docs) < limit:
        s = dict(search0)
        s["per_page"] = per_page
        s["page"] = page_n
        r = ctx.request.post(ts_url, data=json.dumps({"searches": [s]}),
                             headers={"content-type": "text/plain"})
        if r.status != 200:
            print(f"  list page {page_n}: HTTP {r.status} — stopping pagination.", flush=True)
            break
        payload = cast("dict[str, Any]", r.json())
        results = cast("list[Any]", payload.get("results") or [{}])
        res = cast("dict[str, Any]", results[0])
        hits = cast("list[Any]", res.get("hits") or [])
        fval = res.get("found")
        if isinstance(fval, int):
            found = fval
        for h in hits:
            if isinstance(h, dict):
                doc = cast("dict[str, Any]", h).get("document")
                if isinstance(doc, dict):
                    docs.append(cast("dict[str, Any]", doc))
        if not hits or (found is not None and len(docs) >= found):
            break
        page_n += 1
    return docs[:limit]


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


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _build_browser(p: Any, headless: bool) -> BrowserContext:
    SCRAPE_PROFILE.mkdir(parents=True, exist_ok=True)
    return cast("BrowserContext", p.chromium.launch_persistent_context(
        user_data_dir=str(SCRAPE_PROFILE),
        headless=headless,
        viewport={"width": 1500, "height": 1000},
        args=["--disable-blink-features=AutomationControlled"],
    ))


def _collect_docs(ctx: BrowserContext, page: Page, cfg: ScrapeConfig
                  ) -> list[SearchBatch]:
    """Run every search, returning one ``SearchBatch`` per search (NOT a merged
    pool). Each over-fetches (3x its limit) and id-dedups WITHIN itself, so a job
    both searches return survives in both batches -- the write loop then writes it
    once but lets the losing search backfill from its remaining candidates.
    """
    defaults = cfg.get("defaults", SearchSpec())
    default_limit = int(cfg.get("limit", 15))
    batches: list[SearchBatch] = []
    for search in cfg["searches"]:
        limit = int(search.get("limit", default_limit))
        name = str(search.get("name") or "search")
        url = build_url(search, defaults)
        print(f"\n{describe_search(search, defaults)} (limit {limit})", flush=True)
        ts_url, search0 = capture_list_query(page, url)
        excl = ":!=" in str(search0.get("filter_by", ""))
        print(f"  excludeApplied applied: {'yes' if excl else 'no (full filtered list)'}",
              flush=True)
        pool_size = min(max(limit * 3, limit + 20), 300)
        docs = fetch_list(ctx, ts_url, search0, pool_size)
        seen: set[str] = set()
        uniq: list[dict[str, Any]] = []
        for doc in docs:
            jid = str(doc.get("id") or "")
            if jid and jid not in seen:
                seen.add(jid)
                uniq.append(doc)
        print(f"  {len(docs)} candidates fetched, {len(uniq)} unique by id.", flush=True)
        batches.append({"name": name, "limit": limit, "docs": uniq})
    return batches


def run_scrape(config_path: Path = SCRAPE_CONFIG, headless: bool = False,
               login_wait: int = 150, force_overwrite: bool | None = None) -> int:
    """Scrape every configured search into ``jobDescription/<Company>_<Role>.txt``.

    Returns the number of files written. ``force_overwrite`` overrides the config
    ``force`` flag when given (so the CLI ``--force`` reaches both halves).
    """
    from playwright.sync_api import sync_playwright   # lazy: only when scraping

    cfg = load_config(config_path)
    force = cfg.get("force", False) if force_overwrite is None else force_overwrite
    do_login = cfg.get("login", True)
    JOBDESC.mkdir(parents=True, exist_ok=True)

    print(f"Scraping {len(cfg['searches'])} search(es) → {JOBDESC}/", flush=True)
    written: list[dict[str, str]] = []
    n_dup = n_exist = n_fail = 0
    with sync_playwright() as p:
        ctx = _build_browser(p, headless=headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            print("Opening simplify.jobs in the window ...", flush=True)
            page.goto(SIMPLIFY_JOBS_URL, wait_until="domcontentloaded", timeout=60000)
            wait_for_login(page, login_wait if do_login else 0)

            batches = _collect_docs(ctx, page, cfg)
            if not any(b["docs"] for b in batches):
                print("No jobs returned from any search.", flush=True)
                return 0

            pre_existing = {f.name for f in JOBDESC.glob("*.txt")}
            seen_fps: set[str] = set()
            used_names: set[str] = set()
            handled_ids: set[str] = set()           # ids already written/dup/failed once
            for batch in batches:
                n_written_this = 0                  # this search fills its OWN quota
                for doc in batch["docs"]:
                    if n_written_this >= batch["limit"]:
                        break                        # this search hit its per-search cap
                    job_id = str(doc.get("id") or "")
                    if not job_id or job_id in handled_ids:
                        continue                     # blank, or another search already took it
                    handled_ids.add(job_id)
                    company = str(doc.get("company_name") or "").strip() or "Unknown"
                    title = str(doc.get("title") or "").strip()

                    detail = fetch_detail(ctx, job_id)
                    if not detail:
                        n_fail += 1
                        print(f"  {company} — {title[:55]}: detail fetch failed.", flush=True)
                        continue

                    fp = content_fingerprint(detail)
                    if fp in seen_fps:
                        n_dup += 1                   # same posting via another board/search ...
                        continue                     # ... so it does NOT spend this search's quota
                    seen_fps.add(fp)

                    stem = make_filename(company, title)
                    fname = f"{stem}.txt"
                    if fname in pre_existing and not force:
                        n_exist += 1
                        continue
                    n = 2
                    while fname in used_names:
                        fname = f"{stem}_{n}.txt"
                        n += 1
                    used_names.add(fname)

                    (JOBDESC / fname).write_text(format_job_text(detail, job_id), encoding="utf-8")
                    nkw = len(extract_keywords(detail))
                    print(f"[{len(written) + 1}] {company} — {title[:46]}  →  {fname}  "
                          f"({len(clean_lines(detail.get('requirements')))} req, "
                          f"{len(clean_lines(detail.get('responsibilities')))} resp, {nkw} kw)",
                          flush=True)
                    written.append({"company": company, "title": title, "id": job_id,
                                    "file": fname})
                    n_written_this += 1
        finally:
            ctx.close()

    SCRAPE_LAST_RUN.parent.mkdir(parents=True, exist_ok=True)
    SCRAPE_LAST_RUN.write_text(json.dumps(
        {"searches": [describe_search(s, cfg.get("defaults", SearchSpec()))
                      for s in cfg["searches"]],
         "written": written,
         "skipped": {"duplicate": n_dup, "exists": n_exist, "detail_failed": n_fail}},
        indent=2), encoding="utf-8")
    print(f"\nDone: {len(written)} written; skipped {n_dup} duplicate, "
          f"{n_exist} existing, {n_fail} failed → {JOBDESC}/", flush=True)
    return len(written)
