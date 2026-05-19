#!/usr/bin/env python3
"""
conference_pipeline.py — Orchestrate conference-paper fetch + score + select.

Routes (venue, year) to the right fetcher (OpenReview or Semantic Scholar),
applies the shared config's keyword scoring, and writes top-N JSON to a path
matching what enrich_papers.py downstream expects.

Usage:
    python3 conference_pipeline.py --venue NeurIPS --year 2024 \
        --topic-filter > /tmp/daily_papers_top30.json
    python3 conference_pipeline.py --venue MICCAI --year 2024 \
        --no-topic-filter > /tmp/daily_papers_top30.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DAILY = _HERE.parent / "daily-papers"
_SHARED = _HERE.parent / "_shared"
for p in (_SHARED, _DAILY):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from user_config import daily_papers_config

# Reuse the shared scoring function so behavior matches the daily pipeline.
import fetch_and_score as fas  # noqa: E402

OPENREVIEW_VENUES = {"neurips", "icml", "iclr", "colm", "tmlr"}
S2_VENUES_DEFAULT_NO_FILTER = {
    "miccai", "chil", "mlhc", "amia", "ipmi", "midl", "isbi",
}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def run_fetcher(venue: str, year: int, extra_args: list[str]) -> list[dict]:
    venue_key = venue.lower()
    if venue_key in OPENREVIEW_VENUES:
        script = _HERE / "openreview_fetcher.py"
    else:
        script = _HERE / "s2_fetcher.py"

    cmd = [sys.executable, str(script), "--venue", venue, "--year", str(year)] + extra_args
    log(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stderr:
        sys.stderr.write(result.stderr)
    if result.returncode != 0:
        log(f"Fetcher failed with exit {result.returncode}")
        return []
    try:
        return json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError as exc:
        log(f"Fetcher produced invalid JSON: {exc}")
        log(f"First 500 chars of stdout: {result.stdout[:500]}")
        return []


def score_papers(papers: list[dict], apply_min_filter: bool) -> list[dict]:
    """Apply shared-config keyword scoring + venue-tier and citation boosts."""
    config = daily_papers_config()
    min_score = config.get("min_score", 1)

    scored = []
    for p in papers:
        base = fas.score_paper(p, is_trending=False)
        if base < -100:  # negative-keyword rejection
            continue
        keyword_score = max(base, 0)

        # Topic-filter gate uses keyword score only — tier and citations are
        # ranking signals, not topic-relevance signals. Otherwise every NeurIPS
        # spotlight passes the filter regardless of healthcare relevance.
        if apply_min_filter and keyword_score < min_score:
            continue

        score = keyword_score

        # OpenReview tier ranking boost
        tier = p.get("tier")
        if tier == 3:
            score += 3  # oral
        elif tier == 2:
            score += 2  # spotlight
        elif tier == 1:
            score += 1  # poster

        # S2 citation ranking boost (log-scaled, capped)
        cites = p.get("citation_count", 0) or 0
        if cites >= 100:
            score += 3
        elif cites >= 25:
            score += 2
        elif cites >= 5:
            score += 1

        p["score"] = score
        p["keyword_score"] = keyword_score
        scored.append(p)

    scored.sort(key=lambda x: -x["score"])
    return scored


def select_top(papers: list[dict], top_n: int) -> list[dict]:
    return papers[:top_n]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--venue", required=True)
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--query", default=None, help="Optional S2 query filter")
    parser.add_argument("--top-n", type=int, default=None,
                        help="Override config top_n (default: from shared config)")
    parser.add_argument("--topic-filter", action="store_true",
                        help="Apply shared-config min_score filter (good for big ML conferences)")
    parser.add_argument("--no-topic-filter", action="store_true",
                        help="Skip min_score filter (good for healthcare-specific venues)")
    parser.add_argument("--max", type=int, default=5000,
                        help="Max raw papers to fetch before scoring (S2 only)")
    args = parser.parse_args()

    venue_key = args.venue.lower()
    if args.topic_filter and args.no_topic_filter:
        log("--topic-filter and --no-topic-filter both set; using topic-filter")
        apply_filter = True
    elif args.topic_filter:
        apply_filter = True
    elif args.no_topic_filter:
        apply_filter = False
    else:
        # Default: filter ML conferences (big, off-topic noise); don't filter healthcare-specific
        apply_filter = venue_key not in S2_VENUES_DEFAULT_NO_FILTER

    fetcher_extra: list[str] = []
    if args.query:
        fetcher_extra += ["--query", args.query]
    if venue_key not in OPENREVIEW_VENUES:
        fetcher_extra += ["--max", str(args.max)]

    log(f"=== Conference papers: {args.venue} {args.year} (topic_filter={apply_filter}) ===")

    raw = run_fetcher(args.venue, args.year, fetcher_extra)
    log(f"Got {len(raw)} raw papers from fetcher")
    if not raw:
        json.dump([], sys.stdout)
        return

    scored = score_papers(raw, apply_min_filter=apply_filter)
    log(f"After scoring + filter: {len(scored)} papers")

    config = daily_papers_config()
    default_top = config.get("top_n", 40)
    # For multi-day / large-pool runs, the daily pipeline uses top_n*N. Mirror that idea:
    # for big conferences (filtered), allow up to 3x default; for small healthcare confs, keep more.
    if args.top_n is not None:
        top_n = args.top_n
    elif apply_filter:
        top_n = default_top * 3
    else:
        top_n = max(default_top * 3, min(150, len(scored)))

    top = select_top(scored, top_n)
    log(f"Final: {len(top)} papers (top_n={top_n})")
    json.dump(top, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
