---
name: daily-papers-fetch
description: |
  Paper fetching, step 1 of the three-step pipeline. Fetches recent papers from arXiv,
  Hugging Face, PubMed, bioRxiv, and medRxiv, scores and filters them, enriches metadata,
  and writes `/tmp/daily_papers_enriched.json` for downstream skills.

  Trigger phrases: "fetch papers", "run paper fetching".
  Supports multi-day requests such as "paper recommendations from the last 3 days",
  "paper recommendations from the last week", "fetch papers from the last 3 days", and "recent papers from the last 5 days".
---

> **Before starting**: say "Starting paper fetch" and state today's date. For multi-day mode, also state the fetch range.

# Paper Fetching (Fetch + Score + Enrich)

You are the user's paper fetching system, step 1 of the three-step pipeline. Fetch recent papers -> score and filter -> enrich metadata -> save to a temporary file.

## Step 0: Read Shared Config

First read the only shared config file: `../_shared/user-config.json`. Do not search for or assume a second override config file.

Explicitly create and use these variables throughout the rest of the workflow:

- `VAULT_PATH`
- `DAILY_PAPERS_PATH`
- `DOMAIN_NAME`
- `DOMAIN_SUMMARY`
- `DOMAIN_FOCUS_THEMES`
- `KEYWORDS`
- `NEGATIVE_KEYWORDS`
- `DOMAIN_BOOST_KEYWORDS`
- `ARXIV_CATEGORIES`
- `MIN_SCORE`
- `TOP_N`

Where:

- `DAILY_PAPERS_PATH = {VAULT_PATH}/{daily_papers_folder}`
- `DOMAIN_NAME / DOMAIN_SUMMARY / DOMAIN_FOCUS_THEMES` come from the `domain` section of the shared config
- all keywords, categories, and thresholds come from the shared config
- do not add stale default domain preferences; the active research direction is the one in the shared config

Use the shared config and the variables above for all subsequent steps.

## Parse Number of Days

Parse a `--days N` argument from the user request. Matching rules:

- "last week", "recent 7 days", "papers from the last week" -> `--days 7`
- "last 3 days", "recent three days", "fetch 3 days" -> `--days 3`
- "last two weeks" -> `--days 14`
- no special range / "fetch papers" -> omit `--days` and use the script default of today

Store the parsed value as `DAYS_ARG` and use it in later script calls.

## Config Source

- Single config file: `../_shared/user-config.json`
- to switch domain, keywords, themes, or paths, edit only this file
- Do not maintain another keyword table in skill text, script arguments, or temporary prompts

## Workflow

### Phase 1+2: Fetch + Score + Merge/Deduplicate (Pure Python Script)

Use `fetch_and_score.py` to perform Hugging Face + arXiv + PubMed + bioRxiv + medRxiv fetching, scoring, merging, deduplication, history deduplication, and top N selection from config in one step. This costs zero model tokens.

```bash
# Default: today
python3 ../daily-papers/fetch_and_score.py > /tmp/daily_papers_top30.json

# Multi-day mode, replacing N with the parsed number of days
python3 ../daily-papers/fetch_and_score.py --days N > /tmp/daily_papers_top30.json
```

Based on `DAYS_ARG`, add `--days N` only when the user specified a range.

The script automatically handles:

- parallel fetching from Hugging Face Daily + Trending API, arXiv API, PubMed, bioRxiv, and medRxiv
- keyword scoring with positive, negative, domain-boost, and trending signals
- cross-source deduplication by `paper_id`, DOI, arXiv ID, and title hash
- cross-day deduplication against `.history.json`, including relaxed weekend rules
- history backfill when fewer than 20 papers are available
- selecting results by descending score using `top_n` from shared config

Progress logs go to stderr. JSON results go to stdout.

**Check output**: confirm `/tmp/daily_papers_top30.json` exists and contains a valid JSON array. If it is missing or an empty array, inspect stderr for diagnostics.

### Phase 3: Batch Enrichment (`enrich_papers.py` Script)

Use `enrich_papers.py` to enrich all papers in one batch. The script uses `asyncio` plus concurrent `curl` subprocesses and regex-based HTML parsing, without WebFetch.

**First save the Phase 2 top 30 results to the temporary file**, then run:

```bash
cat /tmp/daily_papers_top30.json | python3 ../daily-papers/enrich_papers.py /tmp/daily_papers_enriched.json
```

Important: use a **file path argument** rather than stdout redirection, so stdout and stderr do not get mixed in sandboxed environments.

The script automatically performs the following work with `Semaphore(10)` concurrency and a 30-second timeout per paper:

- fetches HTML pages and PDF pages in parallel
- extracts from HTML: `figure_url`, `authors`, `affiliations`, `section_headers`, `captions`, `has_real_world`, `method_names`, `method_summary`
- extracts from PDF: `affiliations` via `pdftotext | extract_affiliations.py`
- falls back to `<meta>` tags on the abstract page for authors and affiliations when HTML authors are empty
- merges fields with these internal priorities:
  - `figure_url`: HTML curl
  - `affiliations`: PDF > HTML > abstract fallback > Phase 1 data
  - `authors`: HTML > abstract fallback > Phase 1 data
  - other fields: HTML regex extraction

**Output format**: same JSON array as input, with these fields added to each paper:

- `figure_url` (string): first figure URL
- `affiliations` (string): comma-separated institution list
- `authors` (string): author list, possibly overwritten by a more complete source
- `section_headers` (array): section headings
- `captions` (array): figure/table captions
- `has_real_world` (bool): whether real-world experiments are detected
- `method_names` (array): method names
- `method_summary` (string): method description, 300-500 words

## Output

After completion, verify `/tmp/daily_papers_enriched.json` exists and contains a valid JSON array. Tell the user:

- how many papers were fetched
- how many papers were enriched successfully
- to run the next step: `review papers`

## Notes

- Phase 1+2 uses `fetch_and_score.py` and is run directly by the current Claude Code session, with zero model-token cost
- Phase 3 uses `enrich_papers.py` and is also run directly by the current Claude Code session
- If a script fails, inspect stderr for diagnostics
- If arXiv API fetching fails, the script automatically falls back to Hugging Face-only sources
- If medRxiv fetching fails through Python SSL, the script automatically falls back to `curl`
- If fewer than 20 papers are available, process however many exist
- **Weekend strategy**: arXiv does not update on weekends, Hugging Face Daily is usually sparse, but Hugging Face Trending keeps updating. On weekends, rely mainly on trending sources
- **Do not perform git operations**, do not generate the recommendation file, and only output temporary JSON
