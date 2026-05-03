#!/usr/bin/env python3
"""
update_history.py - Update the recommendation history file.

This script is part of daily-papers-review (Phase 6).

Usage:
    python3 update_history.py --paper-ids ID1 ID2 ... --date YYYY-MM-DD
    python3 update_history.py --arxiv-ids ID1 ID2 ... --date YYYY-MM-DD
    python3 update_history.py --from-enriched /tmp/daily_papers_enriched.json --date YYYY-MM-DD
    python3 update_history.py --from-recommendation YYYY-MM-DD-论文推荐.md --date YYYY-MM-DD

    # Cross-platform (auto-detect paths)
    python3 update_history.py --date 2026-03-17

The script:
1. Reads existing history from {vault}/DailyPapers/.history.json
2. Adds new entries for papers not already in history
3. Preserves the earliest date for papers that are re-recommended
4. Removes entries older than 30 days
5. Writes back to .history.json
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

_SHARED_DIR = Path(__file__).resolve().parent.parent / "_shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from user_config import daily_papers_dir, temp_file_path

HISTORY_FILE = daily_papers_dir() / ".history.json"
DAYS_TO_KEEP = 30


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def title_to_paper_id(title: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", clean_text(title).lower()).strip()
    if len(normalized.split()) < 5:
        return ""
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    return f"title:{digest}"


def extract_arxiv_id(text: str) -> str:
    match = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", text)
    if match:
        return match.group(1)
    match = re.search(r"\b(\d{4}\.\d{4,5})\b", text)
    return match.group(1) if match else ""


def extract_pubmed_id(text: str) -> str:
    match = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", text)
    if match:
        return match.group(1)
    match = re.search(r"\bpmid[:\s]+(\d+)\b", text, re.IGNORECASE)
    return match.group(1) if match else ""


def extract_doi(text: str) -> str:
    value = clean_text(text)
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.IGNORECASE)
    match = re.search(r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)", value)
    return match.group(1).rstrip(" .;,)").lower() if match else ""


def normalize_paper_id(raw_id: str, title: str = "") -> str:
    value = clean_text(raw_id)
    if value.startswith(("title:", "arxiv:", "doi:", "pubmed:", "title-fallback:")):
        return value

    title_key = title_to_paper_id(title)
    if title_key:
        return title_key

    if value:
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


def extract_paper_ids(text: str) -> set[str]:
    ids = set()

    for match in re.finditer(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", text):
        ids.add(f"arxiv:{match.group(1)}")
    for match in re.finditer(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", text):
        ids.add(f"pubmed:{match.group(1)}")
    for match in re.finditer(r"https?://(?:dx\.)?doi\.org/([^\s)\]|]+)", text, re.IGNORECASE):
        doi = extract_doi(match.group(1))
        if doi:
            ids.add(f"doi:{doi}")
    for match in re.finditer(r"https?://(?:www\.)?(?:bio|med)rxiv\.org/content/([^\s)\]|]+)", text, re.IGNORECASE):
        content_id = match.group(1).split("?")[0].strip("/")
        doi = extract_doi(re.sub(r"v\d+$", "", content_id))
        ids.add(f"doi:{doi}" if doi else content_id.lower())
    for match in re.finditer(r"^### \d+\. (.+)$", text, re.MULTILINE):
        title_key = title_to_paper_id(match.group(1))
        if title_key:
            ids.add(title_key)

    return ids


def dedup_entries(entries: list[dict]) -> list[dict]:
    deduped = {}
    for entry in entries:
        paper_id = normalize_paper_id(entry.get("id", ""), entry.get("title", ""))
        if not paper_id:
            continue
        if paper_id not in deduped:
            deduped[paper_id] = {
                "id": paper_id,
                "title": entry.get("title", ""),
                "score": entry.get("score", 0),
            }
        else:
            if not deduped[paper_id].get("title") and entry.get("title"):
                deduped[paper_id]["title"] = entry["title"]
            deduped[paper_id]["score"] = max(deduped[paper_id].get("score", 0), entry.get("score", 0))
    return list(deduped.values())


def load_history() -> list:
    """Load existing history or return empty list."""
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def save_history(history: list):
    """Save history to file."""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def load_from_enriched(path: str) -> list:
    """Load papers from enriched JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        papers = json.load(f)

    entries = []
    for paper in papers:
        paper_id = normalize_paper_id(paper.get("paper_id", ""), paper.get("title", ""))
        if not paper_id:
            paper_id = normalize_paper_id(paper.get("url", ""), paper.get("title", ""))
        if paper_id:
            entries.append({
                "id": paper_id,
                "title": paper.get("title", "")[:200],
                "score": paper.get("score", 0),
            })
    return dedup_entries(entries)


def load_from_recommendation(path: str) -> list:
    """Load papers from recommendation markdown file."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    entries = [{"id": paper_id, "title": ""} for paper_id in sorted(extract_paper_ids(content))]
    for match in re.finditer(r"^### \d+\. (.+)$", content, re.MULTILINE):
        title = match.group(1).strip()
        paper_id = title_to_paper_id(title)
        if paper_id:
            entries.append({"id": paper_id, "title": title})
    return dedup_entries(entries)


def update_history(entries: list, date: str, preserve_earliest: bool = True):
    """Update history with new entries."""
    history = load_history()
    existing_ids = {
        normalize_paper_id(item.get("id", ""), item.get("title", ""))
        for item in history
        if item.get("id")
    }

    added = 0
    for entry in dedup_entries(entries):
        paper_id = normalize_paper_id(entry.get("id", ""), entry.get("title", ""))
        if not paper_id:
            continue

        if paper_id not in existing_ids:
            history.append({
                "id": paper_id,
                "date": date,
                "title": entry.get("title", ""),
            })
            existing_ids.add(paper_id)
            added += 1
        elif preserve_earliest:
            for item in history:
                existing_id = normalize_paper_id(item.get("id", ""), item.get("title", ""))
                if existing_id == paper_id and item.get("date", "") > date:
                    item["date"] = date
                    break

    cutoff_date = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=DAYS_TO_KEEP)).strftime("%Y-%m-%d")
    history = [item for item in history if item.get("date", "") >= cutoff_date]

    save_history(history)
    return added


def main():
    parser = argparse.ArgumentParser(description="Update recommendation history")
    parser.add_argument("--paper-ids", nargs="+", help="Generic paper IDs to add")
    parser.add_argument("--arxiv-ids", nargs="+", help="Legacy arXiv IDs to add")
    parser.add_argument("--from-enriched", help="Path to enriched JSON file")
    parser.add_argument("--from-recommendation", help="Path to recommendation markdown file")
    parser.add_argument("--date", required=True, help="Date (YYYY-MM-DD)")

    args = parser.parse_args()

    if args.paper_ids:
        entries = [{"id": paper_id, "title": ""} for paper_id in args.paper_ids]
    elif args.arxiv_ids:
        entries = [{"id": f"arxiv:{arxiv_id}", "title": ""} for arxiv_id in args.arxiv_ids]
    elif args.from_enriched:
        entries = load_from_enriched(args.from_enriched)
    elif args.from_recommendation:
        entries = load_from_recommendation(args.from_recommendation)
    else:
        auto_enriched = temp_file_path("daily_papers_enriched.json")
        if auto_enriched.exists():
            print(f"[update_history] Auto-detected input: {auto_enriched}", file=sys.stderr)
            entries = load_from_enriched(str(auto_enriched))
        else:
            print("Error: Must specify --paper-ids, --arxiv-ids, --from-enriched, or --from-recommendation", file=sys.stderr)
            print(f"  Or ensure {temp_file_path('daily_papers_enriched.json')} exists", file=sys.stderr)
            sys.exit(1)

    added = update_history(entries, args.date)
    print(f"Added {added} new entries to history")


if __name__ == "__main__":
    main()
