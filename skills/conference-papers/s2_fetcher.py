#!/usr/bin/env python3
"""
s2_fetcher.py — Fetch papers from Semantic Scholar by venue + year.

Best for: MICCAI / CHIL / MLHC / AMIA / arbitrary medical-AI venues that aren't on OpenReview.

Usage:
    python3 s2_fetcher.py --venue MICCAI --year 2024 > /tmp/s2_papers.json
    python3 s2_fetcher.py --venue "Machine Learning for Healthcare" --year 2024
    python3 s2_fetcher.py --venue MICCAI --year 2024 --query segmentation

Stderr: progress logs. Stdout: JSON array of papers.

Set SEMANTIC_SCHOLAR_API_KEY env var to bypass anonymous rate limits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

S2_API = "https://api.semanticscholar.org/graph/v1"
BULK_FIELDS = "title,abstract,authors,year,venue,publicationVenue,citationCount,externalIds,openAccessPdf,publicationDate"
SEARCH_FIELDS = BULK_FIELDS
PAGE_SIZE_BULK = 1000  # bulk endpoint max
PAGE_SIZE_SEARCH = 100  # search endpoint max

# Canonical venue strings for popular healthcare-AI venues.
# Semantic Scholar's venue field is fuzzy / partial-match.
VENUE_ALIASES = {
    "miccai": "MICCAI",
    "chil": "Conference on Health, Inference, and Learning",
    "mlhc": "Machine Learning for Healthcare",
    "amia": "American Medical Informatics Association",
    "ipmi": "Information Processing in Medical Imaging",
    "midl": "Medical Imaging with Deep Learning",
    "isbi": "International Symposium on Biomedical Imaging",
}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def title_hash(title: str) -> str:
    norm = re.sub(r"\s+", " ", title.strip().lower())
    return hashlib.md5(norm.encode("utf-8")).hexdigest()[:16]


def http_get_json(url: str, api_key: str | None = None, timeout: int = 30, retries: int = 5) -> dict:
    headers = {"User-Agent": "Mozilla/5.0"}
    if api_key:
        headers["x-api-key"] = api_key

    for attempt in range(retries):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 429:
                wait = min(60, 5 * (2 ** attempt))
                log(f"  429 rate limit, sleeping {wait}s (attempt {attempt+1}/{retries})")
                time.sleep(wait)
                continue
            if attempt == retries - 1:
                raise
            log(f"  HTTP {exc.code}, retrying...")
            time.sleep(2 ** attempt)
        except Exception as exc:
            if attempt == retries - 1:
                raise
            log(f"  error {exc!r}, retrying...")
            time.sleep(2 ** attempt)
    return {}


def fetch_via_bulk_search(
    venue: str,
    year: int,
    query: str | None = None,
    api_key: str | None = None,
    max_results: int = 5000,
) -> list[dict]:
    """
    Use the /paper/search/bulk endpoint — supports token-based pagination
    and is more lenient than /paper/search for venue+year queries.
    """
    all_papers: list[dict] = []
    token = None
    page = 0
    while True:
        params = {
            "venue": venue,
            "year": str(year),
            "fields": BULK_FIELDS,
            "limit": PAGE_SIZE_BULK,
        }
        if query:
            params["query"] = query
        if token:
            params["token"] = token
        url = f"{S2_API}/paper/search/bulk?{urlencode(params)}"
        data = http_get_json(url, api_key=api_key)
        page_papers = data.get("data") or []
        if not page_papers:
            break
        all_papers.extend(page_papers)
        page += 1
        log(f"  bulk page {page}: +{len(page_papers)} (total {len(all_papers)})")
        token = data.get("token")
        if not token or len(all_papers) >= max_results:
            break
        time.sleep(1.0 if not api_key else 0.5)
    return all_papers


def fetch_via_search(
    venue: str,
    year: int,
    query: str | None = None,
    api_key: str | None = None,
    max_results: int = 1000,
) -> list[dict]:
    """Fallback: /paper/search endpoint. Limited offset; no token pagination."""
    all_papers: list[dict] = []
    offset = 0
    while offset < max_results:
        params = {
            "venue": venue,
            "year": str(year),
            "fields": SEARCH_FIELDS,
            "limit": PAGE_SIZE_SEARCH,
            "offset": offset,
        }
        if query:
            params["query"] = query
        else:
            # /paper/search requires a non-empty query; use a generic word.
            params["query"] = venue
        url = f"{S2_API}/paper/search?{urlencode(params)}"
        data = http_get_json(url, api_key=api_key)
        page_papers = data.get("data") or []
        if not page_papers:
            break
        all_papers.extend(page_papers)
        log(f"  search offset {offset}: +{len(page_papers)} (total {len(all_papers)})")
        if len(page_papers) < PAGE_SIZE_SEARCH:
            break
        offset += PAGE_SIZE_SEARCH
        time.sleep(1.0 if not api_key else 0.5)
    return all_papers


def normalize(p: dict, venue_canonical: str, year: int) -> dict | None:
    title = (p.get("title") or "").strip()
    abstract = (p.get("abstract") or "").strip()
    if not title:
        return None
    authors_list = p.get("authors") or []
    authors = ", ".join(a.get("name", "") for a in authors_list if a.get("name"))

    external = p.get("externalIds") or {}
    doi = external.get("DOI", "")
    arxiv = external.get("ArXiv", "")
    pubmed = external.get("PubMed", "")

    s2_id = p.get("paperId", "")
    url = f"https://www.semanticscholar.org/paper/{s2_id}" if s2_id else ""

    pdf_url = ""
    oa = p.get("openAccessPdf") or {}
    if oa.get("url"):
        pdf_url = oa["url"]
    elif arxiv:
        pdf_url = f"https://arxiv.org/pdf/{arxiv}"
    elif doi:
        pdf_url = f"https://doi.org/{doi}"

    venue_str = (p.get("venue") or "") or venue_canonical
    paper_id = f"s2:{s2_id}" if s2_id else f"title:{title_hash(title)}"

    return {
        "paper_id": paper_id,
        "s2_id": s2_id,
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "url": url,
        "pdf": pdf_url,
        "venue": venue_str,
        "venue_canonical": venue_canonical,
        "venue_year": year,
        "citation_count": p.get("citationCount", 0) or 0,
        "doi": doi,
        "arxiv_id": arxiv,
        "pubmed_id": pubmed,
        "publication_date": p.get("publicationDate", ""),
        "source": "semantic_scholar",
        "affiliations": "",
        "score": 0,
    }


def resolve_venue(user_venue: str) -> str:
    """Map short keys (miccai / chil / mlhc) to canonical S2 venue strings."""
    return VENUE_ALIASES.get(user_venue.lower(), user_venue)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--venue", required=True, help="Venue: MICCAI / CHIL / MLHC / AMIA / or full venue string")
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--query", default=None, help="Optional keyword to narrow results")
    parser.add_argument("--max", type=int, default=2000)
    args = parser.parse_args()

    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        log("Using SEMANTIC_SCHOLAR_API_KEY for higher rate limits.")
    else:
        log("No API key — using anonymous rate limits. Set SEMANTIC_SCHOLAR_API_KEY to speed up.")

    canonical = resolve_venue(args.venue)
    log(f"Fetching {canonical} {args.year} from Semantic Scholar (max {args.max})...")

    try:
        raw = fetch_via_bulk_search(canonical, args.year, args.query, api_key, args.max)
    except Exception as exc:
        log(f"bulk search failed ({exc}); falling back to /paper/search")
        raw = fetch_via_search(canonical, args.year, args.query, api_key, args.max)

    log(f"Got {len(raw)} raw results; normalizing...")
    papers = [n for n in (normalize(p, canonical, args.year) for p in raw) if n is not None]
    log(f"Kept {len(papers)} papers after normalization")
    json.dump(papers, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
