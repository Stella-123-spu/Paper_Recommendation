#!/usr/bin/env python3
from __future__ import annotations

"""
fetch_and_score.py — Phase 1+2: Fetch, score, merge, dedup, select top papers.

Usage:
    python3 fetch_and_score.py > /tmp/daily_papers_top.json
    python3 fetch_and_score.py --date 2026-02-25 > /tmp/daily_papers_top.json
    python3 fetch_and_score.py --days 7 > /tmp/daily_papers_top.json

Stderr: progress logs. Stdout: JSON array of top papers (`top_n * days`).
"""

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_SHARED_DIR = Path(__file__).resolve().parent.parent / "_shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from user_config import daily_papers_config, daily_papers_dir

# ── Configuration ──────────────────────────────────────────────────────────

_CONFIG = daily_papers_config()

KEYWORDS = _CONFIG["keywords"]
NEGATIVE_KEYWORDS = _CONFIG["negative_keywords"]
DOMAIN_BOOST_KEYWORDS = _CONFIG["domain_boost_keywords"]
ARXIV_CATEGORIES = _CONFIG["arxiv_categories"]
MIN_SCORE = _CONFIG["min_score"]
TOP_N = _CONFIG["top_n"]

DAILYPAPERS_DIR = daily_papers_dir()
HISTORY_PATH = DAILYPAPERS_DIR / ".history.json"

ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

SOURCE_PRIORITY = {
    "hf-trending": 5,
    "hf-daily": 4,
    "arxiv": 3,
    "medrxiv": 2,
    "biorxiv": 2,
    "pubmed": 1,
}

AI_SIGNAL_KEYWORDS = [
    "machine learning",
    "deep learning",
    "artificial intelligence",
    "large language model",
    "language model",
    "foundation model",
    "transformer",
    "neural network",
    "graph neural network",
    "representation learning",
    "self-supervised",
    "self supervised",
    "multimodal",
    "retrieval-augmented",
    "retrieval augmented",
    "generative ai",
    "diffusion model",
    "reinforcement learning",
    "embedding model",
    "llm",
]

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


# ── Text helpers ───────────────────────────────────────────────────────────


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_text(title).lower()).strip()


def build_title_key(title: str) -> str:
    normalized = normalize_title(title)
    if len(normalized.split()) < 5:
        return ""
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    return f"title:{digest}"


def normalize_doi(raw: str) -> str:
    text = clean_text(raw).strip(" .;,)")
    if not text:
        return ""
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.IGNORECASE)
    match = re.search(r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)", text)
    return match.group(1).rstrip(" .;,)").lower() if match else ""


def extract_doi(text: str) -> str:
    return normalize_doi(text)


def extract_arxiv_id(text: str) -> str:
    match = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?", text, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b", text)
    return match.group(1) if match else ""


def extract_pubmed_id(text: str) -> str:
    match = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"\bpmid[:\s]+(\d+)\b", text, re.IGNORECASE)
    return match.group(1) if match else ""


def parse_loose_date(text: str) -> str:
    value = clean_text(text)
    if not value:
        return ""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y %m %d", "%Y %m", "%Y %b %d", "%Y %B %d", "%Y %b", "%Y %B", "%Y"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.date().isoformat()
        except ValueError:
            continue

    match = re.match(r"(\d{4})\s+([A-Za-z]{3,9})(?:\s+(\d{1,2}))?", value)
    if not match:
        return ""
    year = int(match.group(1))
    month = MONTHS.get(match.group(2)[:3].lower(), 1)
    day = int(match.group(3) or "1")
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return ""


def unique_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def parse_iso_date(value: str):
    text = clean_text(value)
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def is_within_date_window(date_text: str, start_date=None, end_date=None) -> bool:
    if start_date is None or end_date is None:
        return True
    parsed = parse_iso_date(date_text)
    if parsed is None:
        return False
    return start_date <= parsed <= end_date


# ── Scoring ────────────────────────────────────────────────────────────────


def score_paper(paper: dict, is_trending: bool = False) -> int:
    text = (paper["title"] + " " + paper["abstract"]).lower()
    title_lower = paper["title"].lower()

    for neg in NEGATIVE_KEYWORDS:
        if neg in text:
            return -999

    score = 0

    keyword_hits = 0
    for kw in KEYWORDS:
        if kw in title_lower:
            score += 3
            keyword_hits += 1
        elif kw in text:
            score += 1
            keyword_hits += 1

    domain_hits = sum(1 for kw in DOMAIN_BOOST_KEYWORDS if kw in text)
    if domain_hits >= 2:
        score += 2
    elif domain_hits == 1:
        score += 1

    has_relevance = keyword_hits > 0 or domain_hits > 0
    if is_trending:
        upvotes = paper.get("hf_upvotes", 0) or 0
        if has_relevance:
            if upvotes >= 10:
                score += 3
            elif upvotes >= 5:
                score += 2
            elif upvotes >= 2:
                score += 1
        elif upvotes >= 20:
            score += 1

    return score


def paper_keyword_hits(paper: dict) -> int:
    text = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()
    title_lower = paper.get("title", "").lower()
    hits = 0
    for kw in KEYWORDS:
        if kw in title_lower or kw in text:
            hits += 1
    return hits


def has_ai_signal(paper: dict) -> bool:
    text = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()
    if any(term in text for term in AI_SIGNAL_KEYWORDS):
        return True
    return bool(re.search(r"\b(?:llm|ehrm|bert|gpt|transformer|diffusion)\b", text))


def should_keep_biomed_source_paper(paper: dict) -> bool:
    return has_ai_signal(paper) and paper_keyword_hits(paper) > 0


# ── Fetch helpers ──────────────────────────────────────────────────────────


def fetch_url_curl(url: str, timeout: int = 30) -> str:
    try:
        proc = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout), url],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout
    except Exception as e:
        print(f"  [WARN] curl failed {url}: {e}", file=sys.stderr)
    return ""


def fetch_url(url: str, timeout: int = 30, allow_curl_fallback: bool = False) -> str:
    try:
        req = Request(url, headers={"User-Agent": "daily-papers-bot/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [WARN] fetch failed {url}: {e}", file=sys.stderr)
        if allow_curl_fallback:
            return fetch_url_curl(url, timeout=timeout)
        return ""


# ── Identity and merge helpers ─────────────────────────────────────────────


def ensure_identity_fields(paper: dict) -> dict:
    result = dict(paper)
    url = result.get("url", "")
    arxiv_id = result.get("arxiv_id") or extract_arxiv_id(url)
    pubmed_id = result.get("pubmed_id") or extract_pubmed_id(url)
    doi = normalize_doi(result.get("doi", "") or result.get("preprint_doi", "") or url)
    title_key = build_title_key(result.get("title", ""))

    if arxiv_id:
        result["arxiv_id"] = arxiv_id
    if pubmed_id:
        result["pubmed_id"] = pubmed_id
    if doi:
        result["doi"] = doi

    if not result.get("paper_id"):
        if title_key:
            result["paper_id"] = title_key
        elif arxiv_id:
            result["paper_id"] = f"arxiv:{arxiv_id}"
        elif doi:
            result["paper_id"] = f"doi:{doi}"
        elif pubmed_id:
            result["paper_id"] = f"pubmed:{pubmed_id}"
        else:
            result["paper_id"] = f"title-fallback:{hashlib.sha1((result.get('title') or url).encode('utf-8')).hexdigest()[:16]}"

    source = result.get("source", "")
    source_list = result.get("all_sources") or []
    if isinstance(source_list, str):
        source_list = [source_list]
    result["all_sources"] = unique_preserve_order(
        sorted(
            [*(source_list or []), source],
            key=lambda name: (-SOURCE_PRIORITY.get(name, 0), name),
        )
    )
    return result


def identity_keys(paper: dict) -> list[str]:
    result = ensure_identity_fields(paper)
    keys = []
    if result.get("arxiv_id"):
        keys.append(f"arxiv:{result['arxiv_id']}")
    if result.get("doi"):
        keys.append(f"doi:{result['doi']}")
    if result.get("pubmed_id"):
        keys.append(f"pubmed:{result['pubmed_id']}")
    title_key = build_title_key(result.get("title", ""))
    if title_key:
        keys.append(title_key)
    keys.append(result["paper_id"])
    return unique_preserve_order(keys)


def paper_rank(paper: dict) -> tuple[int, int, int, int, int]:
    return (
        int(paper.get("score", 0) or 0),
        SOURCE_PRIORITY.get(paper.get("source", ""), 0),
        len(paper.get("abstract", "")),
        len(paper.get("affiliations", "")),
        len(paper.get("authors", "")),
    )


def merge_two_papers(left: dict, right: dict) -> dict:
    left = ensure_identity_fields(left)
    right = ensure_identity_fields(right)
    primary, secondary = (left, right) if paper_rank(left) >= paper_rank(right) else (right, left)
    merged = dict(primary)

    for field in ("title", "authors", "affiliations", "abstract", "url", "pdf", "date", "category", "jatsxml"):
        current = clean_text(str(merged.get(field, "")))
        candidate = clean_text(str(secondary.get(field, "")))
        if not current and candidate:
            merged[field] = secondary.get(field)
        elif field in {"authors", "affiliations", "abstract"} and len(candidate) > len(current):
            merged[field] = secondary.get(field)

    for field in ("arxiv_id", "doi", "pubmed_id"):
        if not merged.get(field) and secondary.get(field):
            merged[field] = secondary[field]

    merged["score"] = max(int(left.get("score", 0) or 0), int(right.get("score", 0) or 0))
    merged["hf_upvotes"] = max(int(left.get("hf_upvotes", 0) or 0), int(right.get("hf_upvotes", 0) or 0))
    merged["all_sources"] = unique_preserve_order(
        sorted(
            [*(left.get("all_sources") or []), *(right.get("all_sources") or []), left.get("source", ""), right.get("source", "")],
            key=lambda name: (-SOURCE_PRIORITY.get(name, 0), name),
        )
    )

    title_key = build_title_key(merged.get("title", ""))
    if title_key:
        merged["paper_id"] = title_key
    elif merged.get("paper_id"):
        merged["paper_id"] = merged["paper_id"]
    elif merged.get("arxiv_id"):
        merged["paper_id"] = f"arxiv:{merged['arxiv_id']}"
    elif merged.get("doi"):
        merged["paper_id"] = f"doi:{merged['doi']}"
    elif merged.get("pubmed_id"):
        merged["paper_id"] = f"pubmed:{merged['pubmed_id']}"

    return merged


def consolidate_papers(papers: list[dict]) -> list[dict]:
    canonical: dict[str, dict] = {}
    key_to_canonical: dict[str, str] = {}
    counter = 0

    for paper in papers:
        current = ensure_identity_fields(paper)
        keys = identity_keys(current)
        existing_ids = unique_preserve_order([key_to_canonical[k] for k in keys if k in key_to_canonical])

        if not existing_ids:
            cid = f"paper-{counter}"
            counter += 1
            canonical[cid] = current
        else:
            cid = existing_ids[0]
            for other_id in existing_ids[1:]:
                if other_id == cid or other_id not in canonical:
                    continue
                canonical[cid] = merge_two_papers(canonical[cid], canonical[other_id])
                for key, mapped in list(key_to_canonical.items()):
                    if mapped == other_id:
                        key_to_canonical[key] = cid
                del canonical[other_id]
            canonical[cid] = merge_two_papers(canonical[cid], current)

        for key in identity_keys(canonical[cid]):
            key_to_canonical[key] = cid

    return [ensure_identity_fields(paper) for paper in canonical.values()]


# ── Hugging Face fetcher ───────────────────────────────────────────────────


def _parse_hf_item(item: dict, source: str) -> dict | None:
    p = item.get("paper", {})
    arxiv_id = p.get("id", "")
    if not arxiv_id:
        return None

    authors_raw = p.get("authors", [])
    if isinstance(authors_raw, list):
        names = []
        for author in authors_raw:
            if isinstance(author, dict):
                names.append(author.get("name", ""))
            elif isinstance(author, str):
                names.append(author)
        authors = ", ".join(name for name in names if name)
    else:
        authors = str(authors_raw)

    paper = ensure_identity_fields({
        "title": clean_text(p.get("title", "")),
        "authors": clean_text(authors),
        "affiliations": "",
        "abstract": clean_text(p.get("summary", "")),
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf": f"https://arxiv.org/pdf/{arxiv_id}",
        "date": (p.get("publishedAt") or "")[:10],
        "score": 0,
        "category": "",
        "source": source,
        "hf_upvotes": p.get("upvotes", 0) or 0,
        "arxiv_id": arxiv_id,
    })

    paper["score"] = score_paper(paper, is_trending=(source == "hf-trending"))
    return paper if paper["score"] >= 0 else None


def fetch_hf_papers(start_date=None, end_date=None) -> list[dict]:
    papers = []

    if start_date and end_date:
        current = start_date
        while current <= end_date:
            date_str = current.isoformat()
            endpoint = f"https://huggingface.co/api/daily_papers?date={date_str}&limit=100"
            print(f"  Fetching hf-daily {date_str}...", file=sys.stderr)
            raw = fetch_url(endpoint)
            if raw:
                try:
                    items = json.loads(raw)
                except json.JSONDecodeError:
                    items = []
                    print(f"  [WARN] bad JSON from hf-daily {date_str}", file=sys.stderr)
                for item in items:
                    paper = _parse_hf_item(item, "hf-daily")
                    if paper:
                        papers.append(paper)
            current += timedelta(days=1)
    else:
        endpoint = "https://huggingface.co/api/daily_papers?limit=50"
        print("  Fetching hf-daily...", file=sys.stderr)
        raw = fetch_url(endpoint)
        if raw:
            try:
                items = json.loads(raw)
            except json.JSONDecodeError:
                items = []
                print("  [WARN] bad JSON from hf-daily", file=sys.stderr)
            for item in items:
                paper = _parse_hf_item(item, "hf-daily")
                if paper:
                    papers.append(paper)

    today = datetime.now().date()
    include_trending = end_date is None or end_date >= today
    if include_trending:
        endpoint = "https://huggingface.co/api/daily_papers?sort=trending&limit=50"
        print("  Fetching hf-trending...", file=sys.stderr)
        raw = fetch_url(endpoint)
        if raw:
            try:
                items = json.loads(raw)
            except json.JSONDecodeError:
                items = []
                print("  [WARN] bad JSON from hf-trending", file=sys.stderr)
            for item in items:
                paper = _parse_hf_item(item, "hf-trending")
                if paper:
                    papers.append(paper)
    else:
        print(
            f"  Skipping hf-trending for historical window ending {end_date}; API has no historical trending endpoint",
            file=sys.stderr,
        )

    result = consolidate_papers(papers)
    print(f"  HF: {len(result)} papers after scoring", file=sys.stderr)
    return result


# ── arXiv fetcher ──────────────────────────────────────────────────────────


def adaptive_arxiv_fetch_limits(days: int) -> tuple[int, int]:
    window_days = max(1, days)
    if window_days == 1:
        return 800, 800
    fetch_budget = min(max(2400, window_days * 1200), 12000)
    batch_size = min(2000, max(800, window_days * 250))
    return batch_size, fetch_budget


def build_arxiv_search_query(start_date=None, end_date=None) -> str:
    category_clause = "(" + " OR ".join(f"cat:{category}" for category in ARXIV_CATEGORIES) + ")"
    if start_date is None or end_date is None:
        return category_clause

    date_clause = (
        f"submittedDate:[{start_date.strftime('%Y%m%d')}0000 TO "
        f"{end_date.strftime('%Y%m%d')}2359]"
    )
    return f"{category_clause} AND {date_clause}"


def fetch_arxiv_papers(start_date=None, end_date=None, days: int = 1) -> list[dict]:
    batch_size, fetch_budget = adaptive_arxiv_fetch_limits(days)
    timeout = max(60, 30 * days)
    search_query = build_arxiv_search_query(start_date, end_date)

    papers = []
    filtered_by_date = 0
    fetched_entries = 0
    print(
        f"  Fetching arXiv (batch_size={batch_size}, fetch_budget={fetch_budget}, timeout={timeout}s)...",
        file=sys.stderr,
    )

    for start in range(0, fetch_budget, batch_size):
        current_max = min(batch_size, fetch_budget - start)
        url = "https://export.arxiv.org/api/query?" + urlencode({
            "search_query": search_query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "start": start,
            "max_results": current_max,
        })

        print(f"    arXiv page start={start}, max_results={current_max}...", file=sys.stderr)
        xml_text = fetch_url(url, timeout=timeout)
        if not xml_text:
            break

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            print(f"  [WARN] arXiv XML parse error: {e}", file=sys.stderr)
            break

        entries = root.findall("atom:entry", ATOM_NS)
        if not entries:
            break

        fetched_entries += len(entries)
        page_oldest_date = None

        for entry in entries:
            title_el = entry.find("atom:title", ATOM_NS)
            summary_el = entry.find("atom:summary", ATOM_NS)
            published_el = entry.find("atom:published", ATOM_NS)
            id_el = entry.find("atom:id", ATOM_NS)
            if title_el is None or summary_el is None:
                continue

            title = clean_text(title_el.text or "")
            abstract = clean_text(summary_el.text or "")
            entry_url = clean_text(id_el.text if id_el is not None else "")
            date = (published_el.text or "")[:10] if published_el is not None else ""
            arxiv_id = entry_url.split("/abs/")[-1] if "/abs/" in entry_url else ""

            pub_date = None
            if date:
                try:
                    pub_date = datetime.strptime(date, "%Y-%m-%d").date()
                    if page_oldest_date is None or pub_date < page_oldest_date:
                        page_oldest_date = pub_date
                except ValueError:
                    pub_date = None

            if days > 1 and start_date and end_date and pub_date is not None:
                if pub_date < start_date or pub_date > end_date:
                    filtered_by_date += 1
                    continue

            author_els = entry.findall("atom:author", ATOM_NS)
            names = []
            affiliations = set()
            for author in author_els:
                name_el = author.find("atom:name", ATOM_NS)
                if name_el is not None and name_el.text:
                    names.append(name_el.text.strip())
                for aff_el in author.findall("arxiv:affiliation", ATOM_NS):
                    if aff_el.text and aff_el.text.strip():
                        affiliations.add(aff_el.text.strip())

            cat_el = entry.find("arxiv:primary_category", ATOM_NS)
            paper = ensure_identity_fields({
                "title": title,
                "authors": ", ".join(names),
                "affiliations": ", ".join(sorted(affiliations)) if affiliations else "",
                "abstract": abstract,
                "url": entry_url,
                "pdf": f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else "",
                "date": date,
                "score": 0,
                "category": cat_el.get("term", "") if cat_el is not None else "",
                "source": "arxiv",
                "arxiv_id": arxiv_id,
            })
            paper["score"] = score_paper(paper)
            if paper["score"] >= 0:
                papers.append(paper)

        if len(entries) < current_max:
            break

        if days > 1 and start_date and page_oldest_date and page_oldest_date <= start_date:
            print(
                f"    arXiv coverage reached start_date={start_date} (oldest page date {page_oldest_date})",
                file=sys.stderr,
            )
            break

    result = consolidate_papers(papers)
    print(
        f"  arXiv: {len(result)} papers after scoring (from {len(papers)} parsed across {fetched_entries} fetched entries, {filtered_by_date} filtered by date)",
        file=sys.stderr,
    )
    return result


# ── PubMed fetcher ─────────────────────────────────────────────────────────


def build_pubmed_query(max_terms: int = 24) -> str:
    focus_terms = []
    seen_focus = set()
    for term in KEYWORDS:
        normalized = clean_text(term).lower()
        if not normalized or normalized in seen_focus:
            continue
        if any(marker in normalized for marker in ("ai", "model", "learning", "retrieval", "question answering", "reasoning", "multimodal", "forecasting")):
            seen_focus.add(normalized)
            focus_terms.append(f"\"{term}\"[Title/Abstract]")
        if len(focus_terms) >= max_terms // 2:
            break

    ai_terms = [f"\"{term}\"[Title/Abstract]" for term in AI_SIGNAL_KEYWORDS[:10]]
    domain_terms = [
        "\"healthcare\"[Title/Abstract]",
        "\"clinical\"[Title/Abstract]",
        "\"medical\"[Title/Abstract]",
        "\"patient\"[Title/Abstract]",
        "\"hospital\"[Title/Abstract]",
        "\"electronic health record\"[Title/Abstract]",
        "\"ehr\"[Title/Abstract]",
    ]

    ai_clause = "(" + " OR ".join(ai_terms) + ")"
    domain_clause = "(" + " OR ".join(domain_terms) + ")"
    if focus_terms:
        return "(" + " OR ".join(focus_terms) + f" OR ({ai_clause} AND {domain_clause}))"
    return f"({ai_clause} AND {domain_clause})"


def parse_pubmed_date(article: ET.Element) -> str:
    candidates = [
        article.find(".//ArticleDate"),
        article.find(".//PubMedPubDate[@PubStatus='pubmed']"),
        article.find(".//JournalIssue/PubDate"),
    ]
    for node in candidates:
        if node is None:
            continue
        year = clean_text(node.findtext("Year", ""))
        month = clean_text(node.findtext("Month", ""))
        day = clean_text(node.findtext("Day", ""))
        if year:
            return parse_loose_date(" ".join(part for part in (year, month, day) if part))
        medline = clean_text(node.findtext("MedlineDate", ""))
        if medline:
            parsed = parse_loose_date(medline)
            if parsed:
                return parsed
    return ""


def parse_pubmed_article(article: ET.Element) -> dict | None:
    pmid = clean_text(article.findtext(".//PMID", ""))
    title_el = article.find(".//ArticleTitle")
    title = clean_text("".join(title_el.itertext()) if title_el is not None else "")
    if not pmid or not title:
        return None

    authors = []
    affiliations = set()
    for author in article.findall(".//AuthorList/Author"):
        collective = clean_text(author.findtext("CollectiveName", ""))
        if collective:
            authors.append(collective)
        else:
            fore = clean_text(author.findtext("ForeName", "") or author.findtext("Initials", ""))
            last = clean_text(author.findtext("LastName", ""))
            name = clean_text(" ".join(part for part in (fore, last) if part))
            if name:
                authors.append(name)
        for aff in author.findall(".//AffiliationInfo/Affiliation"):
            text = clean_text("".join(aff.itertext()))
            if text:
                affiliations.add(text)

    abstract_parts = []
    for abstract in article.findall(".//Abstract/AbstractText"):
        text = clean_text("".join(abstract.itertext()))
        if not text:
            continue
        label = clean_text(abstract.attrib.get("Label", "") or abstract.attrib.get("NlmCategory", ""))
        abstract_parts.append(f"{label}: {text}" if label and not text.lower().startswith(label.lower()) else text)
    abstract = " ".join(abstract_parts)

    doi = ""
    for path in (".//ArticleId[@IdType='doi']", ".//ELocationID[@EIdType='doi']"):
        el = article.find(path)
        if el is not None and clean_text(el.text or ""):
            doi = normalize_doi(el.text or "")
            if doi:
                break

    paper = ensure_identity_fields({
        "title": title,
        "authors": ", ".join(unique_preserve_order(authors)),
        "affiliations": ", ".join(sorted(affiliations)),
        "abstract": abstract,
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "pdf": f"https://doi.org/{doi}" if doi else "",
        "date": parse_pubmed_date(article),
        "score": 0,
        "category": "pubmed",
        "source": "pubmed",
        "pubmed_id": pmid,
        "doi": doi,
    })
    if not should_keep_biomed_source_paper(paper):
        return None
    paper["score"] = score_paper(paper)
    return paper if paper["score"] >= 0 else None


def fetch_pubmed_papers(start_date, end_date, days: int = 1) -> list[dict]:
    if start_date is None or end_date is None:
        return []

    query = build_pubmed_query()
    retmax = min(max(TOP_N * days * 3, 80), 240)
    params = urlencode({
        "db": "pubmed",
        "retmode": "json",
        "sort": "pub+date",
        "retmax": retmax,
        "term": f"({query})",
        "mindate": start_date.strftime("%Y/%m/%d"),
        "maxdate": end_date.strftime("%Y/%m/%d"),
        "datetype": "pdat",
    })
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?{params}"
    timeout = max(60, 30 * days)
    print(f"  Fetching PubMed (retmax={retmax})...", file=sys.stderr)
    raw = fetch_url(url, timeout=timeout)
    if not raw:
        return []

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        print("  [WARN] bad JSON from PubMed esearch", file=sys.stderr)
        return []

    ids = payload.get("esearchresult", {}).get("idlist", []) or []
    if not ids:
        print("  PubMed: 0 papers after scoring", file=sys.stderr)
        return []

    papers = []
    for start in range(0, len(ids), 100):
        batch_ids = ids[start:start + 100]
        batch_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
            + urlencode({
                "db": "pubmed",
                "id": ",".join(batch_ids),
                "retmode": "xml",
            })
        )
        xml_text = fetch_url(batch_url, timeout=timeout)
        if not xml_text:
            continue
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            print(f"  [WARN] PubMed XML parse error: {e}", file=sys.stderr)
            continue
        for article in root.findall(".//PubmedArticle"):
            paper = parse_pubmed_article(article)
            if paper:
                papers.append(paper)

    result = consolidate_papers(papers)
    print(f"  PubMed: {len(result)} papers after scoring", file=sys.stderr)
    return result


# ── bioRxiv / medRxiv fetchers ─────────────────────────────────────────────


def build_preprint_url(server: str, doi: str, version: str) -> str:
    if not doi:
        return ""
    suffix = f"v{version}" if version else ""
    return f"https://www.{server}.org/content/{doi}{suffix}"


def fetch_preprint_server_papers(server: str, start_date, end_date, days: int = 1) -> list[dict]:
    if start_date is None or end_date is None:
        return []

    cursor = 0
    total = None
    papers = []
    timeout = max(60, 30 * days)
    fetch_budget = min(max(TOP_N * days * 3, 240), 600)

    while (total is None or cursor < total) and cursor < fetch_budget:
        url = f"https://api.biorxiv.org/details/{server}/{start_date.isoformat()}/{end_date.isoformat()}/{cursor}"
        print(f"  Fetching {server} cursor={cursor}...", file=sys.stderr)
        raw = fetch_url(url, timeout=timeout, allow_curl_fallback=True)
        if not raw:
            break
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            print(f"  [WARN] bad JSON from {server}", file=sys.stderr)
            break

        messages = payload.get("messages", [{}])
        message = messages[0] if messages else {}
        try:
            total = int(message.get("total", 0) or 0)
        except (TypeError, ValueError):
            total = 0

        collection = payload.get("collection", []) or []
        if not collection:
            break

        for item in collection:
            title = clean_text(item.get("title", ""))
            doi = normalize_doi(item.get("doi", ""))
            version = clean_text(item.get("version", ""))
            url = build_preprint_url(server, doi, version)
            paper = ensure_identity_fields({
                "title": title,
                "authors": clean_text(item.get("authors", "")).replace(";", ","),
                "affiliations": clean_text(item.get("author_corresponding_institution", "")),
                "abstract": clean_text(item.get("abstract", "")),
                "url": url,
                "pdf": f"{url}.full.pdf" if url else "",
                "date": clean_text(item.get("date", "")),
                "score": 0,
                "category": clean_text(item.get("category", "")),
                "source": server,
                "doi": doi,
                "preprint_doi": doi,
                "jatsxml": clean_text(item.get("jatsxml", "")),
            })
            if not should_keep_biomed_source_paper(paper):
                continue
            paper["score"] = score_paper(paper)
            if paper["score"] >= 0:
                papers.append(paper)

        cursor += len(collection)
        if len(collection) == 0 or cursor >= total or cursor >= fetch_budget:
            break

    result = consolidate_papers(papers)
    print(f"  {server}: {len(result)} papers after scoring", file=sys.stderr)
    return result


# ── History helpers ────────────────────────────────────────────────────────


def canonicalize_history_id(raw_id: str, title: str = "") -> str:
    value = clean_text(raw_id)
    if not value and title:
        return build_title_key(title)
    if value.startswith(("title:", "arxiv:", "doi:", "pubmed:", "title-fallback:")):
        return value
    title_key = build_title_key(title)
    if title_key:
        return title_key
    arxiv_id = extract_arxiv_id(value)
    if arxiv_id:
        return f"arxiv:{arxiv_id}"
    pubmed_id = extract_pubmed_id(value)
    if pubmed_id:
        return f"pubmed:{pubmed_id}"
    doi = extract_doi(value)
    if doi:
        return f"doi:{doi}"
    return value


def load_history() -> list[dict]:
    if HISTORY_PATH.exists():
        try:
            return json.loads(HISTORY_PATH.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return []


def extract_paper_ids_from_text(text: str) -> set[str]:
    ids = set()
    for match in re.finditer(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?", text, re.IGNORECASE):
        ids.add(f"arxiv:{match.group(1)}")
    for match in re.finditer(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", text, re.IGNORECASE):
        ids.add(f"pubmed:{match.group(1)}")
    for match in re.finditer(r"https?://(?:dx\.)?doi\.org/([^\s)\]|]+)", text, re.IGNORECASE):
        doi = normalize_doi(match.group(1))
        if doi:
            ids.add(f"doi:{doi}")
    for match in re.finditer(r"https?://(?:www\.)?(?:bio|med)rxiv\.org/content/([^\s)\]|]+)", text, re.IGNORECASE):
        content_id = match.group(1).split("?")[0].strip("/")
        doi = normalize_doi(re.sub(r"v\d+$", "", content_id))
        ids.add(f"doi:{doi}" if doi else content_id.lower())
    for match in re.finditer(r"^### \d+\. (.+)$", text, re.MULTILINE):
        title_key = build_title_key(match.group(1))
        if title_key:
            ids.add(title_key)
    return ids


def load_fallback_ids(days: int = 7) -> set[str]:
    ids: set[str] = set()
    today = datetime.now().date()
    for day in range(1, days + 1):
        fpath = DAILYPAPERS_DIR / f"{(today - timedelta(days=day)).isoformat()}-paper-recommendations.md"
        if not fpath.exists():
            continue
        try:
            ids.update(extract_paper_ids_from_text(fpath.read_text()))
        except IOError:
            continue
    return ids


# ── Final merge & ranking ──────────────────────────────────────────────────


def merge_and_dedup(
    source_papers: list[dict],
    target_date,
    days: int = 1,
    top_n: int = TOP_N,
) -> list[dict]:
    is_weekend = target_date.weekday() >= 5
    merged = consolidate_papers(source_papers)
    by_id = {paper["paper_id"]: paper for paper in merged}
    print(f"  Merged: {len(by_id)} unique papers", file=sys.stderr)

    if days > 1:
        print(f"  Multi-day mode (days={days}): skipping history dedup", file=sys.stderr)
        candidates = [paper for paper in by_id.values() if paper["score"] >= MIN_SCORE]
        candidates.sort(key=lambda paper: paper["score"], reverse=True)
        top = candidates[:top_n]
        print(f"  Final: {len(top)} papers (top_n={top_n})", file=sys.stderr)
        return top

    history = load_history()
    history_ids: dict[str, str] = {}
    for entry in history:
        hid = canonicalize_history_id(entry.get("id", ""), entry.get("title", ""))
        hdate = clean_text(entry.get("date", ""))
        if hid and hdate and (hid not in history_ids or hdate < history_ids[hid]):
            history_ids[hid] = hdate

    if len(history) < 10:
        for fallback_id in load_fallback_ids():
            history_ids.setdefault(fallback_id, "unknown")

    deduped: dict[str, dict] = {}
    removed = 0
    for paper_id, paper in by_id.items():
        if paper_id in history_ids:
            if is_weekend and paper.get("source") == "hf-trending" and (paper.get("hf_upvotes") or 0) >= 5:
                paper["is_re_recommend"] = True
                paper["last_recommend_date"] = history_ids[paper_id]
                deduped[paper_id] = paper
            else:
                removed += 1
        else:
            deduped[paper_id] = paper

    for paper_id, paper in deduped.items():
        if paper_id in history_ids and not paper.get("is_re_recommend"):
            paper["is_re_recommend"] = True
            paper["last_recommend_date"] = history_ids[paper_id]

    print(f"  After history dedup: {len(deduped)} (removed {removed})", file=sys.stderr)

    candidates = [paper for paper in deduped.values() if paper["score"] >= MIN_SCORE]
    candidates.sort(key=lambda paper: paper["score"], reverse=True)

    if len(candidates) < 20 and removed > 0:
        backfill = []
        for paper_id, paper in by_id.items():
            if paper_id not in deduped and paper["score"] >= MIN_SCORE:
                paper["is_re_recommend"] = True
                paper["last_recommend_date"] = history_ids.get(paper_id, "unknown")
                backfill.append(paper)
        backfill.sort(key=lambda paper: paper["score"], reverse=True)
        needed = 20 - len(candidates)
        candidates.extend(backfill[:needed])
        if backfill[:needed]:
            print(f"  Back-filled {min(needed, len(backfill))} from history", file=sys.stderr)

    top = candidates[:top_n]
    print(f"  Final: {len(top)} papers", file=sys.stderr)
    return top


# ── Main ───────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Target date YYYY-MM-DD (default: today)")
    parser.add_argument("--days", type=int, default=1, help="Number of days to fetch (default: 1)")
    args = parser.parse_args()

    target_date = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date
        else datetime.now().date()
    )
    days = max(1, args.days)
    start_date = target_date - timedelta(days=days - 1)
    top_n = TOP_N * days

    is_weekend = target_date.weekday() >= 5
    print(
        f"[fetch_and_score] {target_date} ({'weekend' if is_weekend else 'weekday'})"
        + (f", days={days} [{start_date} ~ {target_date}], top_n={top_n}" if days > 1 else ""),
        file=sys.stderr,
    )

    hf_papers = fetch_hf_papers(start_date, target_date)
    arxiv_papers = fetch_arxiv_papers(start_date, target_date, days)
    pubmed_papers = fetch_pubmed_papers(start_date, target_date, days)
    biorxiv_papers = fetch_preprint_server_papers("biorxiv", start_date, target_date, days)
    medrxiv_papers = fetch_preprint_server_papers("medrxiv", start_date, target_date, days)

    top = merge_and_dedup(
        hf_papers + arxiv_papers + pubmed_papers + biorxiv_papers + medrxiv_papers,
        target_date,
        days=days,
        top_n=top_n,
    )

    json.dump(top, sys.stdout, ensure_ascii=False, indent=2)
    print(file=sys.stdout)


if __name__ == "__main__":
    main()
