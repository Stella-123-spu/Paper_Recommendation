# Daily Paper Recommendation Skills

[![Codex Skills](https://img.shields.io/badge/Codex-Skills-black)](#overview)
[![Obsidian](https://img.shields.io/badge/Obsidian-Native-7C3AED)](#quick-start)
[![Focus](https://img.shields.io/badge/Focus-Healthcare%20AI-0F766E)](#adapt-to-your-domain)
[![Pipeline](https://img.shields.io/badge/Pipeline-3%20Stages-2563EB)](#overview)
[![Sources](https://img.shields.io/badge/Sources-6-orange)](#sources)

A Codex-first workflow for discovering, ranking, reviewing, and note-taking on new papers inside **Obsidian**.

Default preset: **Healthcare AI**.  
Core idea: one prompt triggers a full paper pipeline:

1. Fetch and rank papers
2. Write a daily recommendation note
3. Generate deeper notes for the strongest papers

## Table of Contents

- [Quick Start](#quick-start)
- [Adapt to Your Domain](#adapt-to-your-domain)
- [Overview](#overview)
- [Sources](#sources)
- [Configuration](#configuration)
- [Repo Layout](#repo-layout)
- [Notes](#notes)

## Quick Start

This is the shortest path for a non-technical researcher.

1. Install **Codex** on your machine.
   If you prefer, you can also use **Claude Code** to help edit the config, but this project is designed to run most naturally with Codex.
2. Download this repository and open it in Codex.
3. Make sure you have an **Obsidian vault** for your research.
4. Install these skill folders into `~/.codex/skills/`:
   - `skills/_shared`
   - `skills/daily-papers`
   - `skills/daily-papers-fetch`
   - `skills/daily-papers-review`
   - `skills/daily-papers-notes`
   - `skills/paper-reader`
5. Best practice: create **symbolic links** from this repo into `~/.codex/skills/` so the repo and installed skills stay synced automatically.
6. Open `skills/_shared/user-config.json` and ask Codex to adapt it to:
   - your research domain
   - your Obsidian vault path
   - your folder names for daily papers, notes, and concepts
7. In Codex, run one of:
   - `今日论文推荐`
   - `today's paper recommendations`
   - `过去3天论文推荐`
   - `paper recommendations from the last 3 days`
   - `过去一周论文推荐`
   - `paper recommendations from the last week`
8. Open Obsidian and check the outputs:
   - daily recommendation note
   - paper notes
   - concept notes
   - refreshed indexes, if enabled

Good first test: `过去3天论文推荐`.

Example prompt for Codex:

> Update `skills/_shared/user-config.json` for my setup. My research domain is computational neuroscience. My Obsidian vault is at `/path/to/my/vault`. Please rewrite the domain description, focus themes, related themes, exclusions, ranking keywords, arXiv categories, note taxonomy, and Obsidian folder paths. Keep the pipeline structure unchanged.

## Adapt to Your Domain

The infrastructure is reusable. The default config is not.

If you work outside Healthcare AI, start by editing:

- `paths.obsidian_vault`
- `paths.paper_notes_folder`
- `paths.daily_papers_folder`
- `paths.concepts_folder`
- `paths.temp_dir`
- `domain.name`
- `domain.summary`
- `domain.focus_themes`
- `domain.related_themes`
- `domain.out_of_scope_examples`
- `domain.borderline_include_examples`
- `daily_papers.keywords`
- `daily_papers.negative_keywords`
- `daily_papers.domain_boost_keywords`
- `daily_papers.arxiv_categories`
- `paper_notes_taxonomy.categories`

What usually stays the same:

- multi-source fetching
- rolling time windows
- deduplication
- history tracking
- Obsidian output flow

Practical advice:

- Ask Codex or Claude Code to rewrite `user-config.json` for your field.
- Test with a 1-day or 3-day run.
- Tighten keywords and exclusions if results are noisy.

Common mistake:

- Changing only `domain.name` and `domain.summary` is not enough.
- If you leave the old keywords, taxonomy, or Obsidian paths in place, the system will behave like the old domain and may write to the wrong vault.

## Overview

### What It Does

- Fetches papers from multiple sources
- Scores them with domain-aware keywords
- Deduplicates across sources and history
- Enriches metadata for better review quality
- Writes daily recommendations into Obsidian
- Generates deeper notes for selected papers

### Pipeline

```mermaid
flowchart LR
    A["User prompt"] --> B["daily-papers"]
    B --> C["Fetch + Score + Enrich"]
    B --> D["Review + Save"]
    B --> E["Notes + Concepts + Backfill"]
```

### Why It Exists

Most paper feeds stop at "here are links." This project is meant to support a real research routine:

- better source coverage
- domain-aware ranking
- memory across days
- direct integration with a personal knowledge system

## Sources

Current source mix:

- Hugging Face Daily
- Hugging Face Trending
- arXiv
- PubMed
- bioRxiv
- medRxiv

Time-window support:

- today
- last 3 days
- last week
- other rolling windows via `--days N`

Important constraint:

- Hugging Face Trending does not provide a historical trending endpoint, so historical multi-day runs cannot perfectly reconstruct past trending states.

## Configuration

Single source of truth:

- `skills/_shared/user-config.json`

Key settings:

- Obsidian paths and folders
- domain summary and themes
- ranking keywords and exclusions
- arXiv categories
- `min_score`
- `top_n`
- note taxonomy
- automation toggles

Current defaults include:

- domain preset: `Healthcare AI`
- `top_n = 40`
- `min_score = 1`
- automatic index refresh enabled
- git commit and push disabled inside the automation config

## Repo Layout

```text
skills/
  _shared/
  daily-papers/
  daily-papers-fetch/
  daily-papers-review/
  daily-papers-notes/
  paper-reader/
```

Key files:

- `skills/_shared/user-config.json`
- `skills/daily-papers/fetch_and_score.py`
- `skills/daily-papers/enrich_papers.py`
- `skills/daily-papers-review/update_history.py`

## Notes

- The corresponding skill folders under `~/.codex/skills/` should be linked to this repo for live sync.
- This repo is derived from [huangkiki/dailypaper-skills](https://github.com/huangkiki/dailypaper-skills), with substantial local adaptation for multi-source retrieval, Obsidian integration, and healthcare-focused ranking.
