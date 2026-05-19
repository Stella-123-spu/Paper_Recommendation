---
name: conference-papers
description: |
  Fetch and review papers from a specific conference + year, applying the shared
  Healthcare AI domain filter and the same review + notes pipeline as `daily-papers`.

  Use when the user asks for papers from a named conference (and optionally a year):
  "NeurIPS 2024 healthcare papers", "ICML 2025 papers on medical imaging",
  "papers from MICCAI 2024", "CHIL 2025 papers", "MLHC 2024 papers",
  "papers from ICLR 2024 about EHR foundation models".

  Sources:
  - OpenReview API for NeurIPS / ICML / ICLR / COLM / TMLR (no API key needed)
  - Semantic Scholar API for MICCAI / CHIL / MLHC / AMIA / IPMI / MIDL / ISBI
    (free; recommends setting `SEMANTIC_SCHOLAR_API_KEY` env var)

  After fetching + scoring, hands off to the standard enrich → review → notes pipeline.
---

> **Before starting**: say "Starting conference paper search" and state the parsed venue + year.

# Conference Paper Search

You are the user's conference-specific paper retrieval system. Fetch papers from a
named conference for a specified year, score them with the shared Healthcare AI
keywords, and hand off to the regular review/notes pipeline.

## Step 0: Read Shared Config

Read `../_shared/user-config.json` first. Honor `output.language` for all user-facing prose written by the review/notes downstream steps. Technical terms stay English. Tag taxonomy lives in `{VAULT_PATH}/tag-taxonomy.md` and must be respected by all downstream note writes; downstream skills will add `#venue/{conference}-{year}` automatically for conference-papers ingest. Use the same variables as `daily-papers-fetch`:
`KEYWORDS`, `NEGATIVE_KEYWORDS`, `DOMAIN_BOOST_KEYWORDS`, `MIN_SCORE`, `TOP_N`,
plus the domain themes for the review step.

## Step 1: Parse the User Request

Extract:

- **venue** (required): `NeurIPS` | `ICML` | `ICLR` | `COLM` | `TMLR` | `MICCAI` | `CHIL` | `MLHC` | `AMIA` | `IPMI` | `MIDL` | `ISBI` | or a free-text venue string for Semantic Scholar.
- **year** (required): four-digit year. If the user did not state one, ask once.
- **topic query** (optional): keywords narrowing within the venue, e.g. "medical imaging" or "EHR foundation models". Stored as `QUERY_FILTER`.

Trigger phrases and mapping:

| User phrase | Parsed |
|---|---|
| `NeurIPS 2024 papers` | venue=NeurIPS, year=2024, query=∅ |
| `ICML 2024 papers on medical imaging` | venue=ICML, year=2024, query="medical imaging" |
| `papers from MICCAI 2024` | venue=MICCAI, year=2024, query=∅ |
| `CHIL 2025 papers` | venue=CHIL, year=2025 |
| `ICLR 2024 papers about EHR foundation models` | venue=ICLR, year=2024, query="EHR foundation models" |

## Step 2: Fetch and Score

Run the pipeline script. It routes to OpenReview or Semantic Scholar automatically.

```bash
# For ML conferences (NeurIPS / ICML / ICLR / COLM / TMLR) — defaults to topic-filter on
python3 ../conference-papers/conference_pipeline.py \
    --venue {VENUE} --year {YEAR} \
    > /tmp/daily_papers_top30.json

# For healthcare-specific conferences (MICCAI / CHIL / MLHC / IPMI / MIDL / AMIA / ISBI)
# — defaults to topic-filter off (return the whole venue ranked)
python3 ../conference-papers/conference_pipeline.py \
    --venue {VENUE} --year {YEAR} \
    > /tmp/daily_papers_top30.json

# With an optional topic query (passes through to Semantic Scholar):
python3 ../conference-papers/conference_pipeline.py \
    --venue {VENUE} --year {YEAR} --query "{QUERY_FILTER}" \
    > /tmp/daily_papers_top30.json
```

The script's defaults:

- **ML conferences** → apply `min_score` filter (default config) on top of keyword scoring.
  Returns top `3 * top_n` papers — the user's domain filter trims a 4k-paper venue to ~120 healthcare-relevant ones.
- **Healthcare-specific venues** → skip `min_score` filter; return up to 150 ranked papers.
  These venues are already on-topic; the score is for ranking, not gating.

If the user explicitly wants every paper (no domain filter) on an ML conference, pass `--no-topic-filter`.

### Scoring signals applied

In addition to the standard keyword + domain-boost scoring shared with `daily-papers`:

- **OpenReview tier** (NeurIPS/ICML/ICLR/COLM): oral +3, spotlight +2, poster +1.
- **Citation count** (Semantic Scholar): ≥100 cites +3, ≥25 cites +2, ≥5 cites +1.

For a one-year-old conference, citation counts will be sparse; the keyword score
still dominates. For older years (e.g., NeurIPS 2022), citations become a strong
signal of which papers actually mattered.

## Step 3: Enrich

Same as `daily-papers-fetch` step 3. The fetcher writes the same JSON shape that
`enrich_papers.py` accepts.

```bash
cat /tmp/daily_papers_top30.json | python3 ../daily-papers/enrich_papers.py /tmp/daily_papers_enriched.json
```

Enrichment is best-effort: PubMed-side venues sometimes won't yield arXiv HTML
hits, in which case the abstract + venue metadata is what the review step has.

## Step 4: Review and Notes

Hand off to the standard skills — no special handling required:

1. `daily-papers-review` — produces a recommendation file in `DailyPapers/`.
2. `daily-papers-notes` — produces deep notes for Must Read papers in `PaperNotes/`.

Use a date-stamped filename that reflects the venue + year, *not* today's date.
Suggested filename: `{YYYY-MM-DD}-{VENUE}-{YEAR}-paper-recommendations.md` where
`{YYYY-MM-DD}` is today and `{VENUE}` / `{YEAR}` are the conference parameters.

For the recommendation file:

- Title: `# {VENUE} {YEAR} — Sharp Review (Healthcare AI Slice)` instead of "Today's Sharp Review"
- Opening paragraph: state how many candidates came back, what tier of papers dominate (orals vs posters), and which themes are heavily represented in the venue's healthcare slice
- Triage table and per-paper sections: standard format

## Wiki Maintenance Hook (Required)

After all downstream steps complete, issue a venue-scoped summary entry to `log.md` (overriding the more generic ones the leaf skills wrote). This makes it easy to grep for `venue:` ingests later:

```bash
python3 ../_shared/post_ingest.py "ingest:venue:{VENUE}-{YEAR}" "<N_raw> raw → <N_candidates> healthcare-keyword pass → <N_top> top → <N_recommended> recommended (<M>m / <W>w / <S>s) + <K> deep notes"
```

This also re-runs the index regeneration so the new venue recommendation file appears in `index.md` immediately.

## Output

When everything is complete, tell the user:

- venue + year that was processed
- how many candidate papers passed scoring
- file path of the recommendation file
- how many Must Read / Worth Reading / Skippable

## Constraints and Caveats

- **OpenReview** has no rate limit problems in practice; one venue's whole accepted
  set fits in a few requests.
- **Semantic Scholar without API key** is throttled to ~100 requests / 5 minutes.
  For MICCAI 2024 (700 papers, bulk page=1000) one bulk page is enough — but if
  the user runs several venues back-to-back, recommend setting
  `SEMANTIC_SCHOLAR_API_KEY=<your-key>` in the shell before running.
- **For very large venues** (NeurIPS = ~4000 papers), the LLM review step is what's
  expensive, not fetching. Domain filtering before review is essential — let the
  default `--topic-filter` do its job.
- **TMLR is rolling**, not annual; the fetcher filters by publication year using
  `cdate`. Expect lower precision on the year boundary.
- **Older years** are typically more interesting because citation signals have matured;
  for NeurIPS 2022 / 2023, the citation boost meaningfully reranks the top.
