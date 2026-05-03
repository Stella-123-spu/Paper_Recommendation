# Daily Paper Recommendation Skills

[![Codex Skills](https://img.shields.io/badge/Codex-Skills-black)](#what-it-includes)
[![Obsidian](https://img.shields.io/badge/Obsidian-Native-7C3AED)](#obsidian-native-workflow)
[![Focus](https://img.shields.io/badge/Focus-Healthcare%20AI-0F766E)](#configuration)
[![Pipeline](https://img.shields.io/badge/Pipeline-3%20Stages-2563EB)](#pipeline-overview)
[![Sources](https://img.shields.io/badge/Sources-6-orange)](#sources)

An opinionated, production-ready Codex skill suite for discovering, filtering, reviewing, and note-taking on new research papers with a strong focus on **Healthcare AI**.

It turns a single natural-language request into a full literature workflow:

1. Fetch and rank candidate papers from multiple research sources
2. Generate sharp recommendation writeups for an Obsidian research vault
3. Produce full paper notes and concept links for the strongest papers

Built for people who want more than a paper dump, the workflow emphasizes **topic relevance**, **cross-source deduplication**, **time-window-aware retrieval**, **history-aware recommendations**, and **structured downstream note generation**.

## Table of Contents

- [Quick Start](#quick-start)
- [At a Glance](#at-a-glance)
- [Adapting to Another Research Domain](#adapting-to-another-research-domain)
- [Architecture](#architecture)
- [Why This Project](#why-this-project)
- [Launch Highlights](#launch-highlights)
- [What It Includes](#what-it-includes)
- [Pipeline Overview](#pipeline-overview)
- [Sources](#sources)
- [Time Windows and Retrieval Behavior](#time-windows-and-retrieval-behavior)
- [Ranking and Deduplication](#ranking-and-deduplication)
- [History Awareness](#history-awareness)
- [Metadata Enrichment](#metadata-enrichment)
- [Configuration](#configuration)
- [Obsidian-Native Workflow](#obsidian-native-workflow)
- [Repo Layout](#repo-layout)
- [Typical Usage](#typical-usage)
- [Operational Notes](#operational-notes)
- [Local Sync Model](#local-sync-model)
- [Upstream Acknowledgement](#upstream-acknowledgement)
- [Status](#status)

## Quick Start

This section is written for a non-technical researcher who wants a working paper recommendation setup first and deeper customization second.

### 1. Install Codex

Install Codex on your computer first.

If you are starting from scratch, the simplest path is:

- download Codex
- complete its setup on your machine
- confirm it can open and edit a local project folder

If you prefer another AI coding assistant, you can also use **Claude Code** to help edit the config. This repository is still designed to run most naturally with **Codex**.

### 2. Download This Repository

Get this repository onto your computer in a place you can find easily, such as your Documents folder.

You can do that by:

- cloning it with Git, or
- downloading it as a ZIP and extracting it

Then open the repository folder in Codex.

### 3. Prepare Your Obsidian Vault

This project writes outputs into **Obsidian**, so you should have:

- an existing Obsidian vault for your research, or
- a new Obsidian vault created just for this project

You do not need to build the whole folder structure by hand before starting. The key thing is knowing where your vault lives on disk.

### 4. Install the Skills into Codex and Keep Them Synced

For Codex to use these skills directly, the skill folders need to exist under:

- `~/.codex/skills/`

The best setup is to create **symbolic links** from the folders in this repository into your Codex skills folder so they stay synced all the time.

That way:

- when you edit the files in this repository, Codex sees the changes immediately
- when Codex updates the linked skill files, the changes are still reflected in this repository
- you do not have to manually copy files back and forth

At minimum, the linked skill folders should include:

- `skills/_shared`
- `skills/daily-papers`
- `skills/daily-papers-fetch`
- `skills/daily-papers-review`
- `skills/daily-papers-notes`
- `skills/paper-reader`

If you are not comfortable creating symbolic links yourself, ask Codex to help you set them up from this repository into `~/.codex/skills/`.

### 5. Ask Codex to Set Up the Config for You

The most important setup file is:

- `skills/_shared/user-config.json`

Open that file in Codex and ask it to adapt the project to:

- your research domain
- your Obsidian vault path
- your folder names for daily recommendations, paper notes, and concept notes

Example prompt you can paste into Codex:

> Update `skills/_shared/user-config.json` for my setup. My research domain is computational neuroscience. My Obsidian vault is at `/path/to/my/vault`. Please rewrite the domain description, focus themes, related themes, exclusions, ranking keywords, arXiv categories, and note taxonomy for this field. Also update the Obsidian folder paths and names so the outputs go into my vault. Keep the rest of the pipeline structure unchanged.

If your field is different, replace `computational neuroscience` and the vault path with your own information.

### 6. Check the Config Before Running Anything

Before you run the pipeline, quickly confirm that `user-config.json` matches your real setup:

- the vault path is correct
- the folder names look right
- the domain is your domain, not Healthcare AI
- the keywords match the papers you want
- the negative keywords block the noise you do not want

### 7. Run Your First Recommendation

In Codex, try one of these prompts:

- `今日论文推荐`
- `过去3天论文推荐`
- `过去一周论文推荐`

For a first test, `过去3天论文推荐` is often a good starting point because it gives the system a slightly larger pool than a single-day run.

### 8. Open Obsidian and Inspect the Output

After the run finishes, open your Obsidian vault and look for:

- a daily recommendation note
- generated paper notes for stronger papers
- concept notes or updated concept folders
- refreshed index or MOC pages, if enabled

If the results are off-topic, go back to `user-config.json` and ask Codex to tighten the keywords, exclusions, categories, or taxonomy.

### 9. Tune Once, Then Use Daily

Treat your first run as calibration.

A practical setup loop is:

1. run a 1-day or 3-day recommendation
2. inspect the results in Obsidian
3. ask Codex to improve the config
4. run it again

Usually one or two iterations is enough to make the recommendations feel much more natural for your field.

## At a Glance

- One-command daily paper pipeline for Codex
- Six-source retrieval across ML, biomedical, and medical preprint ecosystems
- Rolling time windows such as today, last 3 days, and last week
- History-aware recommendations to reduce repetition
- Obsidian-native outputs for daily reviews, concept notes, and paper notes
- Shared-config architecture with domain tuning in one file

## Adapting to Another Research Domain

This repository ships with a strong `Healthcare AI` preset, but the core system is reusable for other research areas.

If you work in another domain, treat this repo as:

- reusable pipeline infrastructure
- a domain-specific config preset that you should replace
- a set of review and note-writing behaviors that should be retuned to your literature

### Fastest Path

The fastest way to adapt this project is to use an AI coding assistant such as **Codex** or **Claude Code** to rewrite `skills/_shared/user-config.json` for your field.

Do not feel like you need to hand-edit every keyword and taxonomy entry from scratch.

A good workflow is:

1. Open `skills/_shared/user-config.json`.
2. Tell Codex or Claude Code your research domain.
3. Ask it to rewrite the domain, keyword, exclusion, and taxonomy sections for that field.
4. Review the result and then test with a 1-day and 3-day run.

Example prompt:

> Adapt this repository from Healthcare AI to computational neuroscience. Update `skills/_shared/user-config.json` so the Obsidian vault paths and folder names, domain summary, focus themes, related themes, out-of-scope examples, ranking keywords, negative keywords, domain boost keywords, arXiv categories, and paper note taxonomy all match that field. Keep the pipeline structure unchanged.

### What You Should Change First

Start with `skills/_shared/user-config.json`. That is the main adaptation surface.

Update at least these sections:

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

In practice:

- Point the vault path and folder names at your own Obsidian setup
- Replace the healthcare description with your own field definition
- Rewrite the ranking keywords around your actual research vocabulary
- Add negative keywords for adjacent areas you do not want flooding results
- Change arXiv categories to match your field
- Rewrite the note taxonomy so generated notes land in sensible folders

### What You Usually Do Not Need to Rewrite

Most of the machinery is domain-agnostic:

- multi-source fetching
- rolling time windows
- deduplication across sources
- history tracking
- metadata enrichment
- Obsidian output flow

That means the first pass should be configuration-heavy, not code-heavy.

### Recommended Adaptation Workflow

1. Duplicate the current `user-config.json` and rewrite it for your field.
2. Narrow `daily_papers.keywords` to terms that real papers in your area actually use.
3. Expand `negative_keywords` aggressively so near-neighbor noise does not dominate.
4. Adjust `arxiv_categories` and decide whether your field depends more on arXiv, PubMed, or preprints.
5. Rewrite the `paper_notes_taxonomy` so note placement matches how you think about the field.
6. Run a 1-day test and inspect the top results.
7. Run a 3-day or 7-day test and look for drift, repetition, and irrelevant clusters.
8. Tighten the config again before trusting the pipeline for daily use.

### How to Know Your Adaptation Is Working

Your config is in good shape when:

- the top recommendations mostly belong to your real research area
- obvious off-topic papers are filtered out early
- the review stage uses language and comparisons that fit your field
- concept notes and paper notes fall into folders that make sense
- a 3-day or 7-day run still feels coherent instead of noisy

### Common Mistake

Do not only change `domain.name` and `domain.summary`.

If you leave the healthcare keywords, taxonomy, exclusion lists, or Obsidian path settings in place, the pipeline will still behave like a healthcare-focused recommender and may write outputs into the wrong vault even if the title says otherwise.

## Architecture

```mermaid
flowchart LR
    A["User Prompt<br/>今日论文推荐"] --> B["daily-papers<br/>entry skill"]
    B --> C["Stage 1<br/>Fetch + Score + Enrich"]
    C --> C1["Sources<br/>HF Daily, HF Trending, arXiv, PubMed, bioRxiv, medRxiv"]
    C --> C2["Outputs<br/>/tmp/daily_papers_top30.json<br/>/tmp/daily_papers_enriched.json"]
    B --> D["Stage 2<br/>Review + Save"]
    D --> D1["Obsidian DailyPapers<br/>YYYY-MM-DD-论文推荐.md"]
    D --> D2["History<br/>.history.json"]
    B --> E["Stage 3<br/>Notes + Concepts + Backfill"]
    E --> E1["PaperNotes"]
    E --> E2["Concept Notes"]
    E --> E3["MOCs / Indexes"]
```

## Why This Project

Most "daily papers" setups stop at scraping headlines. This one is built to support an actual research routine:

- Multi-source paper intake instead of a single feed
- Domain-specific ranking instead of generic popularity sorting
- Rolling windows for `today`, `last 3 days`, `last week`, and similar requests
- Cross-day recommendation memory to avoid repeating the same papers
- Obsidian-native outputs for recommendations, notes, concepts, and MOCs
- Full-skill pipeline orchestration from a single user-facing command

The current shared configuration targets:

- Clinical foundation models
- Longitudinal EHR modeling
- Patient trajectory modeling
- Clinical LLMs
- Multimodal clinical modeling
- Causal and intervention modeling in healthcare
- Medical world models and virtual patients

## Launch Highlights

- Multi-source retrieval with domain-aware ranking instead of one-feed scraping
- Better coverage for healthcare research by combining ML feeds, biomedical indexing, and medical preprints
- Practical support for sparse days and weekends through source-aware fallback behavior
- Recommendation memory that tracks prior appearances and supports re-recommendation labeling
- Downstream note generation that turns selection into a reusable knowledge system

## What It Includes

Tracked skill directories:

- `skills/_shared`
- `skills/daily-papers`
- `skills/daily-papers-fetch`
- `skills/daily-papers-review`
- `skills/daily-papers-notes`
- `skills/paper-reader`

Core scripts and logic:

- `skills/daily-papers/fetch_and_score.py`
- `skills/daily-papers/enrich_papers.py`
- `skills/daily-papers-review/update_history.py`
- `skills/_shared/user-config.json`

## Pipeline Overview

### Stage 1. Fetch + Score + Enrich

The fetch stage is orchestrated by the `daily-papers` entry skill and implemented primarily through:

- `fetch_and_score.py`
- `enrich_papers.py`

It performs:

- Multi-source ingestion
- Keyword and domain-aware scoring
- Cross-source entity merging
- Historical deduplication
- Metadata enrichment for downstream review

### Stage 2. Review + Save

The review stage reads the enriched candidate set and produces a recommendation file in Obsidian with:

- A high-signal editorial summary
- Tiered paper triage
- Source attribution
- Re-recommendation markers
- Existing-note linking
- Strong-paper prioritization for note generation

### Stage 3. Notes + Concepts + Backfill

The notes stage generates deep paper notes for top picks and expands the concept library by:

- Creating or updating concept notes
- Generating full paper notes via `paper-reader`
- Backfilling note links into the daily recommendation file
- Refreshing MOC pages when enabled

## Sources

This version pulls from a broader source mix than the original lightweight setup.

Primary sources:

- Hugging Face Daily
- Hugging Face Trending
- arXiv
- PubMed
- bioRxiv
- medRxiv

Why this matters:

- `Hugging Face Daily` helps surface fresh applied ML releases
- `Hugging Face Trending` adds community momentum, especially useful on weekends
- `arXiv` covers core ML and AI categories via configurable category filters
- `PubMed` improves biomedical and clinically grounded coverage
- `bioRxiv` and `medRxiv` expand access to preprints relevant to translational and medical AI

## Time Windows and Retrieval Behavior

The workflow is not limited to "today only." It supports rolling windows through natural-language requests and `--days N`.

Examples:

- `今日论文推荐`
- `过去3天论文推荐`
- `过去一周论文推荐`
- `最近5天论文`

Current behavior:

- Default mode: fetch papers for the current day
- Multi-day mode: fetch an inclusive rolling window ending on the target date
- Supported patterns in the skills currently map common phrases to values like `3`, `7`, and `14` days
- `top_n` is multiplied by the requested number of days, so larger windows return larger candidate sets

Important constraints:

- Hugging Face Trending does **not** expose a historical trending endpoint, so historical multi-day runs cannot reconstruct past trending states
- Weekend behavior is intentionally different because arXiv updates are weaker and Hugging Face Daily is often sparse on weekends
- History deduplication is relaxed for strong weekend trending papers so genuinely hot papers can resurface when appropriate

## Ranking and Deduplication

Paper selection is not random and not just "latest first."

The current pipeline combines:

- Positive keyword matches
- Negative keyword filtering
- Domain boost keywords
- Trending upvote boosts for relevant Hugging Face papers
- Source-priority-based field merging

Cross-source deduplication uses multiple identifiers when available:

- `paper_id`
- DOI
- arXiv ID
- PubMed ID
- Title hashing fallback

This helps collapse the same work when it appears across:

- arXiv and Hugging Face
- preprint servers and PubMed
- multiple source URLs with slightly different metadata

## History Awareness

The repo keeps recommendation memory through:

- `DailyPapers/.history.json` inside the configured vault

That history is used to:

- Avoid recommending the same paper repeatedly across days
- Mark re-recommended papers with prior recommendation dates
- Backfill older strong papers if the current day is too sparse
- Retain a rolling recent history window

This makes the workflow substantially more usable than a stateless scraper.

## Metadata Enrichment

After ranking, papers are enriched in batch to support better review quality.

The enrichment layer extracts or infers fields such as:

- `figure_url`
- `authors`
- `affiliations`
- `section_headers`
- `captions`
- `has_real_world`
- `method_names`
- `method_summary`

Implementation notes:

- Concurrent fetching via `asyncio`
- `curl` subprocesses for HTTP retrieval
- HTML parsing through lightweight regex-based extractors
- PDF text fallback for affiliation extraction
- Source-aware fallback logic when one extraction route fails

This extra structure is what allows the review stage to produce more specific commentary than generic abstract summaries.

## Configuration

There is one shared source of truth:

- `skills/_shared/user-config.json`

This file currently controls:

- Obsidian vault and folder paths
- Domain name and domain summary
- Focus themes and related themes
- Positive and negative ranking keywords
- Domain boost keywords
- arXiv categories
- `min_score`
- `top_n`
- Frontmatter tags
- Paper note taxonomy
- Automation toggles such as index refresh and git behavior

Current domain preset:

- `Healthcare AI`

Current default ranking posture:

- `min_score = 1`
- `top_n = 40`

Current automation defaults:

- `auto_refresh_indexes = true`
- `git_commit = false`
- `git_push = false`

## Obsidian-Native Workflow

This repo is built around an Obsidian research vault, not just a terminal output.

Outputs include:

- Daily recommendation files in `DailyPapers/`
- Paper notes in `PaperNotes/`
- Concept notes under the configured concepts folder
- MOC refresh support for concepts and paper collections

The result is a loop where paper discovery feeds directly into a navigable personal research system.

## Repo Layout

```text
skills/
  _shared/
    user-config.json
  daily-papers/
    fetch_and_score.py
    enrich_papers.py
    SKILL.md
  daily-papers-fetch/
    SKILL.md
  daily-papers-review/
    SKILL.md
    update_history.py
  daily-papers-notes/
    SKILL.md
  paper-reader/
    SKILL.md
```

## Typical Usage

From the user side, the top-level interface is intentionally simple:

- `今日论文推荐`
- `过去3天论文推荐`
- `过去一周论文推荐`

Internally, that single request chains:

1. `daily-papers-fetch`
2. `daily-papers-review`
3. `daily-papers-notes`

The user does not need to manually orchestrate the three stages unless debugging a specific step.

## Operational Notes

A few behaviors are deliberate and worth knowing:

- The fetch stage is designed to minimize token usage by pushing source collection and ranking into Python scripts
- The review and notes stages are tuned for stronger editorial quality and richer vault integration
- Multi-day retrieval is supported, but some sources are inherently better for current-day freshness than historical reconstruction
- The workflow is domain-configurable, but this repo currently ships with a strong healthcare AI bias in its shared config

## Local Sync Model

This repository is also used as a live development source for local Codex skills.

Current sync model:

- The corresponding directories under `~/.codex/skills/` are symbolic links to this repository
- Editing either location updates the same underlying files
- New files added in the linked directories are immediately visible from both paths

That makes this repo both:

- A versioned skill source
- A live local skill workspace

## Upstream Acknowledgement

This skill set is derived from [huangkiki/dailypaper-skills](https://github.com/huangkiki/dailypaper-skills), with substantial local adaptation for:

- multi-source retrieval
- healthcare-focused ranking
- richer metadata enrichment
- Obsidian vault integration
- rolling-window recommendation workflows
- stronger note-generation orchestration

## Status

This version is no longer just a mirror. It is a customized research workflow layer for paper discovery, triage, and note production.

If you are building a serious literature routine around Codex + Obsidian, this is the version meant to hold up under daily use.
