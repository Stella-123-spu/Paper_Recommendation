#!/usr/bin/env python3
"""
openreview_fetcher.py — Fetch accepted papers from OpenReview for a given conference + year.

Supports: NeurIPS / ICML / ICLR / COLM / TMLR.

Usage:
    python3 openreview_fetcher.py --venue NeurIPS --year 2024 > /tmp/openreview_papers.json
    python3 openreview_fetcher.py --venue ICLR --year 2025 --keyword-filter > /tmp/openreview_papers.json

Stdout: JSON array of papers, each with the same shape downstream skills expect
(title, abstract, authors, url, pdf, paper_id, score, source, etc.).
Stderr: progress logs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_SHARED_DIR = Path(__file__).resolve().parent.parent / "_shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

OPENREVIEW_API = "https://api2.openreview.net"
OPENREVIEW_WEB = "https://openreview.net"
PAGE_SIZE = 1000

# venueid patterns to try for each conference (most specific first)
VENUE_PATTERNS = {
    "neurips": [
        "NeurIPS.cc/{year}/Conference",
        "NeurIPS.cc/{year}/Datasets_and_Benchmarks_Track",
    ],
    "icml": ["ICML.cc/{year}/Conference"],
    "iclr": ["ICLR.cc/{year}/Conference"],
    "colm": [
        "COLM/{year}/Conference",
        "colmweb.org/COLM/{year}/Conference",
    ],
    "tmlr": ["TMLR"],  # rolling; year filtered later via cdate
}

# accepted-status tier markers in the "venue" field
ACCEPTED_TIER_PATTERNS = [
    (re.compile(r"oral", re.I), 3),
    (re.compile(r"spotlight", re.I), 2),
    (re.compile(r"poster", re.I), 1),
]


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def http_get_json(url: str, timeout: int = 30, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            if attempt == retries - 1:
                raise
            wait = 2 ** attempt
            log(f"  retry {attempt+1}/{retries} after {wait}s: {exc}")
            time.sleep(wait)
    return {}


def fetch_venue_notes(venueid: str) -> list[dict]:
    """Paginate through all notes for one venueid."""
    all_notes: list[dict] = []
    offset = 0
    while True:
        params = {"content.venueid": venueid, "limit": PAGE_SIZE, "offset": offset}
        url = f"{OPENREVIEW_API}/notes?{urlencode(params)}"
        data = http_get_json(url)
        notes = data.get("notes", []) or []
        if not notes:
            break
        all_notes.extend(notes)
        log(f"  {venueid}: fetched {len(all_notes)} so far")
        if len(notes) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.5)
    return all_notes


def fetch_tmlr_for_year(year: int) -> list[dict]:
    """TMLR is rolling — fetch all and filter by cdate year."""
    start_ms = int(time.mktime(time.strptime(f"{year}-01-01", "%Y-%m-%d")) * 1000)
    end_ms = int(time.mktime(time.strptime(f"{year+1}-01-01", "%Y-%m-%d")) * 1000)
    # TMLR uses a different venueid scheme; try the most-current first
    all_notes = fetch_venue_notes("TMLR")
    return [n for n in all_notes if start_ms <= (n.get("cdate") or 0) < end_ms]


def cv(content: dict, key: str, default=None):
    """OpenReview v2 wraps content values as {'value': ...}; unwrap defensively."""
    v = content.get(key)
    if isinstance(v, dict) and "value" in v:
        return v["value"]
    return v if v is not None else default


def accepted_tier(venue_str: str) -> int | None:
    """Return tier (1=poster, 2=spotlight, 3=oral) or None if not an accepted-paper marker."""
    if not venue_str:
        return None
    for pat, tier in ACCEPTED_TIER_PATTERNS:
        if pat.search(venue_str):
            return tier
    return None


def title_hash(title: str) -> str:
    norm = re.sub(r"\s+", " ", title.strip().lower())
    return hashlib.md5(norm.encode("utf-8")).hexdigest()[:16]


def normalize_note(note: dict, venue_canonical: str, year: int) -> dict | None:
    content = note.get("content") or {}
    title = (cv(content, "title", "") or "").strip()
    abstract = (cv(content, "abstract", "") or "").strip()
    if not title or not abstract:
        return None
    authors = cv(content, "authors", []) or []
    venue_str = cv(content, "venue", "") or ""
    pdf_rel = cv(content, "pdf", "") or ""
    keywords = cv(content, "keywords", []) or []
    primary_area = cv(content, "primary_area", "") or ""
    tldr = cv(content, "TLDR", "") or ""

    note_id = note.get("id", "")
    pdf_url = ""
    if pdf_rel:
        if pdf_rel.startswith("http"):
            pdf_url = pdf_rel
        else:
            pdf_url = f"{OPENREVIEW_WEB}{pdf_rel}" if pdf_rel.startswith("/") else f"{OPENREVIEW_WEB}/pdf?id={note_id}"
    else:
        pdf_url = f"{OPENREVIEW_WEB}/pdf?id={note_id}"

    url = f"{OPENREVIEW_WEB}/forum?id={note_id}"

    tier = accepted_tier(venue_str)
    paper_id = f"title:{title_hash(title)}"

    return {
        "paper_id": paper_id,
        "openreview_id": note_id,
        "title": title,
        "abstract": abstract,
        "authors": ", ".join(authors) if isinstance(authors, list) else str(authors),
        "url": url,
        "pdf": pdf_url,
        "venue": venue_str,
        "venue_canonical": venue_canonical,
        "venue_year": year,
        "tier": tier,
        "tldr": tldr,
        "openreview_keywords": keywords,
        "primary_area": primary_area,
        "source": "openreview",
        "affiliations": "",
        "score": 0,  # filled by scorer downstream
    }


def fetch_papers(venue_key: str, year: int, accepted_only: bool = True) -> list[dict]:
    venue_key_norm = venue_key.lower()
    if venue_key_norm == "tmlr":
        log(f"Fetching TMLR papers from {year} (rolling, filtered by cdate)...")
        raw_notes = fetch_tmlr_for_year(year)
    else:
        patterns = VENUE_PATTERNS.get(venue_key_norm)
        if not patterns:
            log(f"Unknown venue: {venue_key}")
            return []
        raw_notes = []
        for pat in patterns:
            venueid = pat.format(year=year)
            log(f"Fetching venueid={venueid}...")
            notes = fetch_venue_notes(venueid)
            raw_notes.extend(notes)
            if notes:
                # First pattern that returns results is usually the right one
                break

    log(f"Got {len(raw_notes)} raw notes; normalizing...")
    papers = []
    for n in raw_notes:
        p = normalize_note(n, venue_canonical=venue_key.upper(), year=year)
        if p is None:
            continue
        if accepted_only and p["tier"] is None:
            continue
        papers.append(p)
    log(f"Kept {len(papers)} accepted papers (after tier filter)")
    return papers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--venue", required=True, help="Conference key: NeurIPS / ICML / ICLR / COLM / TMLR")
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--all", action="store_true", help="Include withdrawn/rejected (default: accepted only)")
    args = parser.parse_args()

    papers = fetch_papers(args.venue, args.year, accepted_only=not args.all)
    json.dump(papers, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
