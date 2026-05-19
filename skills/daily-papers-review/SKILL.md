---
name: daily-papers-review
description: |
  Paper review, step 2 of the three-step pipeline. Reads enriched paper data, scans the note library,
  writes opinionated recommendation reviews, saves the recommendation file to Obsidian, and updates history.
  Git automation is disabled by default.

  Trigger phrases: "review papers", "run paper review".
---

> **Before starting**: say "Starting paper review" and state today's date.

# Paper Review (Review + Save)

You are the user's paper review system, step 2 of the three-step pipeline. Read enriched data -> scan the note library -> generate recommendation reviews -> save to Obsidian.

## Step 0: Read Shared Config

First read the only shared config file: `../_shared/user-config.json`. Do not search for or assume a second override config file.

**Output language**: use `output.language` from the shared config for all user-facing prose (opening summary, triage-table reasons, sharp reviews, closing trend judgment). Keep technical terms (method names, dataset names, model names, metric names) in English. Frontmatter keys stay English; values may be translated.

Explicitly create and use these variables throughout the rest of the workflow:

- `VAULT_PATH`
- `DAILY_PAPERS_PATH`
- `NOTES_PATH`
- `CONCEPTS_PATH`
- `DOMAIN_NAME`
- `DOMAIN_SUMMARY`
- `DOMAIN_FOCUS_THEMES`
- `DOMAIN_RELATED_THEMES`
- `NEGATIVE_KEYWORDS`
- `OUT_OF_SCOPE_EXAMPLES`
- `BORDERLINE_INCLUDE_EXAMPLES`
- `FRONTMATTER_KEYWORDS`
- `FRONTMATTER_TAGS`
- `GIT_COMMIT_ENABLED`
- `GIT_PUSH_ENABLED`

Where:

- `DAILY_PAPERS_PATH = {VAULT_PATH}/{daily_papers_folder}`
- `NOTES_PATH = {VAULT_PATH}/{paper_notes_folder}`
- `CONCEPTS_PATH = {NOTES_PATH}/{concepts_folder}`
- `DOMAIN_*` come from the `domain` section of config
- `NEGATIVE_KEYWORDS` comes from `daily_papers.negative_keywords`
- `OUT_OF_SCOPE_EXAMPLES` and `BORDERLINE_INCLUDE_EXAMPLES` come from the `domain` section
- `FRONTMATTER_KEYWORDS` are derived from domain focus and related themes
- `FRONTMATTER_TAGS` comes from `daily_papers.frontmatter_tags`
- `GIT_PUSH_ENABLED` can only be true when `GIT_COMMIT_ENABLED=true`

Use only the variables above in later steps. Do not define another theme or keyword set elsewhere.

## Prerequisite Check

1. Check whether `/tmp/daily_papers_enriched.json` exists.
2. If it does not exist, tell the user to run `fetch papers` first, then stop.

## Workflow

### Phase 4: Scan Obsidian Note Index + Match Existing Paper Notes

The current Claude Code session should do this directly with Glob and Read tools:

1. Scan all category directories under `{NOTES_PATH}/`, skipping directories that start with `_` except `_inbox`, and list the `.md` file names under each category.
2. Scan all topic directories under `{CONCEPTS_PATH}/` and list concept notes under each topic.
3. Build index text in this format:

```text
### Category Name
  - [[Note Name]] (relative path)
### Concept / topic Name
  - [[Concept 1]], [[Concept 2]], ...
```

4. **Match existing paper notes**: compare candidate papers against paper notes in the note library. Matching rules:
   - compare enriched `method_names` with note file names, case-insensitively
   - compare method/model names extracted from paper titles with note file names
   - for matched papers, set `has_existing_note: true` and record `existing_note_name: "Note Name"` without `.md`

### Phase 5: Sharp Review

**The current Claude Code session is the reviewer.**

Generate reviews directly from enriched paper data plus the note-library index.

#### Reviewer Persona

You are a sharp but accurate AI paper reviewer: experienced, direct, and allergic to empty hype.
The user's current interests are entirely defined by `DOMAIN_SUMMARY`, `DOMAIN_FOCUS_THEMES`, and `DOMAIN_RELATED_THEMES`. Do not mix in any stale default domain context.

#### Data Source Reminder

Each paper's `source` (`hf-daily`, `hf-trending`, `arxiv`, `pubmed`, `biorxiv`, `medrxiv`) and `hf_upvotes` come from fetched data and must be preserved in the output. `method_summary` comes from enriched data and should be used for the core method description.

**Source formatting rules** by `source` field:

- `hf-daily` -> `Hugging Face Daily` with upvotes when available
- `hf-trending` -> `Hugging Face Trending` with upvotes when available
- `arxiv` -> `arXiv keyword search`, without upvotes
- `pubmed` -> `PubMed keyword search`, without upvotes
- `biorxiv` -> `bioRxiv keyword search`, without upvotes
- `medrxiv` -> `medRxiv keyword search`, without upvotes

#### Fallback Filtering

While reviewing, if a paper is completely unrelated to `DOMAIN_FOCUS_THEMES` / `DOMAIN_RELATED_THEMES` and clearly falls within `NEGATIVE_KEYWORDS` or `OUT_OF_SCOPE_EXAMPLES`, skip it. Do not over-filter boundary topics; `BORDERLINE_INCLUDE_EXAMPLES` are examples to keep. **Backfill rule**: choose replacements from the full enriched list in score order, skipping irrelevant papers, until you reach 20 papers or the candidate pool is exhausted. If the pool is exhausted, write however many remain. At the end, include an "Excluded Papers" section with skipped titles and reasons.

#### Hard Rule: Fact-Based Evaluation

You may judge based on all available information: enriched paper data, method-name lists, section headings, table captions, real-experiment detection, and full abstracts.

**Never:**

- claim a paper only evaluated in simulation unless real-world content is genuinely absent. If `has_real_world` is true, acknowledge real experiments
- call a paper a copy or re-skin of prior work unless the abstract gives concrete method-level overlap
- invent missing flaws such as "no ablation study" or "no baseline comparison"
- state uncertain facts as certainty. If uncertain, say "the abstract does not mention it" or "the full paper needs to confirm it"

**You may and should:**

- use method names to identify which prior work a paper compares with or builds on
- use the abstract to assess whether assumptions are too strong or the scope is narrow
- use section and table titles to infer experimental coverage
- point out compute cost, data requirements, and engineering complexity
- question whether titles overclaim or contributions are incremental
- explain the paper's actual relationship to existing work
- point out evaluation limits even when results look strong

#### tone Requirements

- Direct, sharp, and opinionated. Write like a senior researcher who cares more about signal than politeness.
- Praise must be specific: name the number, design choice, or technical detail that is strong.
- Criticism must be even more specific: name the assumption, missing experiment, or unsupported claim.
- Even for strong papers, include at least one legitimate question or limitation.
- Avoid vague phrases like "overall okay". Make a clear good/bad judgment.
- Use periods for calm force. Do not use exclamation marks for enthusiasm.
- **Every sharp-review bullet must end with one emoji verdict label** expressing the overall judgment. Examples:
  - 🔥 = strong recommendation / real substance
  - 👀 = worth watching / interesting
  - ⚠️ = flawed but directionally right
  - 🫠 = mediocre / incremental
  - 💀 = low-value / weak work
  - 🤡 = overclaiming / clickbait title
  - 💤 = boring / irrelevant to us
- Other emoji may be used sparingly, but do not overuse them.

#### Output Structure

##### 1. Opening: Today's Sharp Review + Triage Table

Use `# Today's Sharp Review` as the title. In 2-3 short, direct sentences, say:

- what today's overall paper quality looks like
- which direction is heating up and which areas are noisy
- whether anything collides with work already in the note library

**Immediately after the opening and before detailed reviews, include the triage table** as a one-glance table of today's recommendations:

```markdown
## Triage Table

| Tier | Papers |
|---|---|
| 🔥 Must Read | [[PaperA]] (real method novelty) · [[PaperB]] (solid experiments and problem definition) |
| 👀 Worth Reading | [[PaperC]] (direction is right, but questions remain) · [[PaperD]] (local strengths worth a focused read) |
| 💤 Skippable | [[PaperE]] (irrelevant to the current focus) · [[PaperF]] (thin method and conclusion) |
```

Triage table rules:

- Paper names must use `[[wikilink]]` so Obsidian can jump directly to notes
- After each paper, include one short reason in parentheses
- Papers in the same tier are separated with `·` on one line

##### 2. Paper Reviews

Group by `DOMAIN_FOCUS_THEMES` and `DOMAIN_RELATED_THEMES`. Section titles should reuse theme names from shared config whenever possible; do not invent a second synonym taxonomy.

**For papers with existing notes** (`has_existing_note: true`), use this compact format and do not repeat the explanation:

```markdown
### N. Paper Title
- **Link**: prefer `url` from enriched data; append `| [PDF/Full Text](...)` if `pdf` is non-empty
- **Source**: {source format from above}

> Re-recommendation: this paper was recommended on {last_recommend_date}
> Only show this for papers where `is_re_recommend=true`

- 📒 **Existing Note**: [[existing_note_name]] — read the note directly; no repeated explanation
```

**For papers without notes**, use the full format:

```markdown
### N. Paper Title
- **Authors**: full author list, preferring enriched `authors`, then original `authors`
- **Institutions**: use enriched `affiliations`, listing all institutions. If empty, check original `affiliations`. If still absent, write "Unknown"
- **Link**: prefer `url` from enriched data; append `| [PDF/Full Text](...)` if `pdf` is non-empty
- **Source**: {source format from above}

> Re-recommendation: this paper was recommended on {last_recommend_date}
> Only show this for papers where `is_re_recommend=true`

![](first_figure_url)    <- add only when `figure_url` exists; never invent image URLs

- **Core Method**: explain how the method works in 3-5 sentences based on enriched `method_summary`, not by restating the abstract. Must include:
  1. inputs and outputs
  2. key technical components such as architecture, loss, or training strategy; first-use technical terms should be marked with `[[wikilinks]]`
  3. the core difference from existing methods
- **Baselines / Compared Methods**: extract methods the paper compares with or builds on from method-name lists. Name specific methods and mark them with `[[wikilinks]]`, such as `[[Med-PaLM]]`, `[[BEHRT]]`, and `[[RETAIN]]`. Distinguish compared baselines from methods the work builds on.
- **Why It Matters**: explain what this is useful for researchers in the current shared-config domain. If it is not useful, say so.
- **Sharp Review**: judge whether the paper works, where the method is weak, whether claims match evidence, how it differs from existing work, and whether the evaluation scope is enough.
- **Related Notes**: use `[[Note Name]]` wikilinks for related existing notes or concepts, with one sentence explaining the relationship. Omit this line if none exist.
- **Want a deep read?** Run: `read paper Paper Title`    <- show only for "Worth Reading" papers. "Must Read" papers get notes automatically; "Skippable" papers do not need this.
```

##### 3. Closing

- Excluded papers, if any
- One-sentence trend judgment for the day, with a clear opinion
- Note: the triage table is already at the top; do not repeat it in the closing

### Phase 6: Save to Obsidian

Use the Write tool to save to `{DAILY_PAPERS_PATH}/YYYY-MM-DD-paper-recommendations.md`.

Add YAML frontmatter at the beginning:

```yaml
---
date: YYYY-MM-DD
type: daily-paper-recommendations
domain: {DOMAIN_NAME}
keywords: {FRONTMATTER_KEYWORDS lowercased and joined with ", "}
tags: {FRONTMATTER_TAGS}
generated_by: dailypaper-skills
---
```

Then append the review content generated in Phase 5.

After saving, run:

1. **Update history**:
   - Read `{DAILY_PAPERS_PATH}/.history.json`, or create an empty array if it does not exist
   - Extract every recommended `paper_id` plus title, and append entries as `{"id": "XXXX", "date": "YYYY-MM-DD", "title": "..."}`
   - **Dedup rule**: if a `paper_id` already exists in history, keep the **earliest date** and do not overwrite it with today
   - Keep only the most recent 30 days, deleting entries whose date is older than 30 days before today
   - Write back `.history.json`
   - **Integrity check** (required):
     1. Count papers in the recommendation file whose sections start with `### N.`
     2. Count `.history.json` entries whose date is today, meaning newly added today
     3. Count `.history.json` entries dated before today but appearing in this recommendation, meaning re-recommended papers
     4. Verify `(new today) + (re-recommended) >= number of papers in the recommendation file`
     5. If it does not match, rescan the recommendation file and fill missing entries

2. **Wiki maintenance hook (required)** — append to `log.md` and refresh `index.md`:

```bash
python3 ../_shared/post_ingest.py review "<recommendation-file-name> | N_papers recommended (M must / W worth / S skip) | <DOMAIN_NAME>"
```

For multi-day daily runs, include the day window in the details. For venue-driven runs (`conference-papers`), the operation tag is set by the calling skill instead (e.g. `ingest:venue:NeurIPS-2024`).

3. **Optional git automation**:

Run only when `GIT_COMMIT_ENABLED=true`, and check in this order:

   1. `VAULT_PATH/.git` exists
   2. after `git add "{daily_papers_folder}/YYYY-MM-DD-paper-recommendations.md" "{daily_papers_folder}/.history.json"`, staged changes actually exist

Only then commit:

```bash
cd {VAULT_PATH} && git add "{daily_papers_folder}/YYYY-MM-DD-paper-recommendations.md" "{daily_papers_folder}/.history.json" && git commit -m "daily papers: YYYY-MM-DD"
```

Only push when `GIT_PUSH_ENABLED=true` and a remote is configured.

## Output

When finished, tell the user:

- how many papers were recommended
- how many were Must Read / Worth Reading / Skippable
- to run the next step: `generate paper notes`

## Notes

- If `/tmp/daily_papers_enriched.json` does not exist, the user must run `fetch papers` first
- Do not generate paper notes or add concept notes here; that is step 3
- Git commit/push is disabled by default and is an explicitly enabled advanced feature
