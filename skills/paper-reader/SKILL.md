---
name: paper-reader
description: |
  Use when the user asks to "read paper", "analyze paper", "summarize paper",
  "generate paper note", "quick paper read", "critique this paper", or provides a PDF file
  that appears to be an academic paper. Default to the shared domain focus in config,
  but still handle explicitly user-specified papers outside that focus.

  Also supports Zotero integration: "read this Zotero paper", "quick read a Zotero paper",
  "critically analyze this Zotero paper", "read the papers in this Zotero collection",
  and "batch-read papers under a Zotero collection".

  Important trigger phrases: "read paper ...", "read this paper", "help me read this paper".
---

> **Before starting**: greet the user briefly.

# Academic Paper Reader

Default to the current research domain in the shared config, with Zotero integration and Obsidian note saving. If the user explicitly specifies one paper, follow the paper itself and do not let old domain examples constrain the analysis.

## Step 0: Read Shared Config

First read the only shared config file: `../_shared/user-config.json`. Do not search for or assume a second override config file.

Explicitly create and use these variables throughout the rest of the workflow:

- `VAULT_PATH`
- `NOTES_PATH`
- `CONCEPTS_PATH`
- `ZOTERO_DB`
- `ZOTERO_STORAGE`
- `DOMAIN_NAME`
- `DOMAIN_SUMMARY`
- `DOMAIN_FOCUS_THEMES`
- `DOMAIN_RELATED_THEMES`
- `PAPER_NOTES_TAXONOMY`
- `AUTO_REFRESH_INDEXES`
- `GIT_COMMIT_ENABLED`
- `GIT_PUSH_ENABLED`

Where:

- `NOTES_PATH = {VAULT_PATH}/{paper_notes_folder}`
- `CONCEPTS_PATH = {NOTES_PATH}/{concepts_folder}`
- `DOMAIN_*` come from the `domain` section of config
- `PAPER_NOTES_TAXONOMY` comes from the `paper_notes_taxonomy` section of config
- `GIT_PUSH_ENABLED` can only be true when `GIT_COMMIT_ENABLED=true`

Use the variables above for all subsequent steps.

If the user does not specify a domain context, default to `DOMAIN_SUMMARY`, `DOMAIN_FOCUS_THEMES`, and `DOMAIN_RELATED_THEMES`. If the user gives a specific paper, follow the paper content.

## 1. Receive a Paper

| Input Type | Example | Handling |
|---|---|---|
| PDF path | `/path/to/paper.pdf` | Read directly |
| arXiv link | `https://arxiv.org/abs/xxxx` | WebFetch |
| Zotero collection | "papers in this Zotero collection" | query database -> list papers -> user selects |
| Zotero search | "the Zotero paper titled π0.5" | search title -> find PDF |
| no PDF | Zotero item has no attachment | fetch from the web, see below |

### Fetch Flow When No PDF Exists

1. Run `python3 assets/zotero_helper.py info {item_id}` to get paper metadata.
2. Fetch in priority order: arXiv HTML > arXiv PDF > DOI > WebSearch title.
3. Identify arXiv ID from URL, Zotero `extra`, or title search.
4. Prefer WebFetch on `https://arxiv.org/html/{arxiv_id}` without downloading.
5. Skip only when there is neither a PDF nor an online source, or when the content is not a paper.

> Detailed Zotero operations are in `references/zotero-guide.md`.

## 2. Reading Modes

| Mode | Trigger Phrases | Output |
|---|---|---|
| **Quick Summary** | "quick read", "quick" | 3-5 sentences on the core contribution |
| **Full Analysis** | "detailed analysis", default | structured note using the template |
| **Critical Analysis** | "critique", "critical analysis" | methodological strengths and weaknesses |
| **Knowledge Extraction** | "extract formulas", "technical details" | formulas plus algorithm pseudocode |

## 3. Note Generation

**Template**: strictly follow `assets/paper-note-template.md`; do not simplify it yourself.

### Core Quality Rules

1. **Zero omissions**: every figure, formula, and table in the paper must appear in the note.
2. **Inline concept links**: the first occurrence of technical terms in the body must use `[[Concept]]` links, not only a list at the end.
3. **No ASCII flowcharts**: describe architecture with structured Markdown lists plus `$math symbols$`.
4. **Formula completeness**: every formula needs a name (`[[Concept|Name]]`), LaTeX formula, meaning, and symbol explanation.
5. **Prefer external image links**: use arXiv HTML, project pages, or GitHub first; download locally only when unavailable.

> Detailed quality rules for formulas, images, and tables are in `references/quality-standards.md`.

### Figure Retrieval Flow (Multi-Source Fallback)

**Goal**: ensure the note includes **every figure** in the paper. Count the paper's total figures first, then retrieve them one by one.

1. WebSearch `"{paper title} arxiv"` to find the arXiv ID.
2. **Source A: arXiv HTML** (preferred):
   - WebFetch `https://arxiv.org/html/{arxiv_id}` and extract every `<figure>` caption and image `src` URL.
   - Count the paper's total figures and confirm extraction is complete.
3. **Source B: project page** when HTML is 404 or incomplete:
   - Find the project-page URL in the abstract/HTML, using common patterns such as `project page`, `github.io`, or `our website`.
   - WebFetch the project page and extract displayed images, usually teaser or demo figures.
4. **Source C: PDF extraction** when both earlier sources fail:
   - run `pdfimages -png` on the PDF and keep valid images larger than 10 KB.
5. Embed images in notes as `![Figure X](url)`.
6. Verify that external links load or local files are larger than 10 KB.
7. **URL deduplication**: before writing, check whether the URL repeats an arXiv ID path segment, such as `2603.05312v1/2603.05312v1/`, and remove the duplicate segment. See `references/image-troubleshooting.md`.

> ar5iv numbering does not always match figure numbering. See `references/image-troubleshooting.md` for debugging.

### Image Reliability After Generation

After saving the note, run the image reachability script. It downloads unreachable external images into local storage automatically:

```bash
python3 ../daily-papers/download_note_images.py "{full note path}"
```

- Reachable external links stay unchanged. Unreachable images are downloaded to `assets/` and replaced with Obsidian wikilinks.
- If localization occurs, frontmatter `image_source` is updated to `mixed`.

### Formula Format

Every formula must include: name (`[[Concept|Name]]`), a LaTeX `$$` block with blank lines before and after it, meaning, and symbol list.
`$$` blocks **must have blank lines around them** or Obsidian will not render them. Split long formulas with `aligned`.

## 4. Obsidian Saving

### File Naming

Use only the **method/model name**: `{MethodName}.md`, for example `Pi05.md`, with no year prefix.
Derive the method name from the title before the colon, from "We propose XXX" in the abstract, or by converting Greek letters to ASCII.
If uncertain, save to `_inbox/`.

### Save Path

Use the Zotero collection hierarchy: `{NOTES_PATH}/{zotero_collection_path}/{MethodName}.md`.

### YAML Frontmatter

```yaml
---
title: "Paper Title"
method_name: "MethodName"
authors: [Author1, Author2]
year: 2025
venue: arXiv
tags: [tag1, tag2]  # lowercase hyphenated tags, 3-8 tags
zotero_collection: top-level/subtopic/topic
image_source: online
created: YYYY-MM-DD
---
```

Choose tags from Related Work headings, the abstract, the paper's central problem, and the current domain in shared config. The first tag is the core theme; do not mechanically copy stale domain tags.

### After Saving

1. Refresh index pages only when `AUTO_REFRESH_INDEXES=true`:

   ```bash
   python3 ../_shared/generate_concept_mocs.py
   python3 ../_shared/generate_paper_mocs.py
   ```

2. Run git only when `GIT_COMMIT_ENABLED=true`:
   - first confirm `VAULT_PATH/.git` exists
   - after `git add {new file} {paper_notes_folder}/`, staged changes must actually exist
   - only then run:

   ```bash
   cd {VAULT_PATH} && git add {new file} {paper_notes_folder}/ && git commit -m "add paper note: {MethodName}"
   ```

   - push only when `GIT_PUSH_ENABLED=true` and a remote is configured

## 5. Concept Library Maintenance (Required for Every Paper)

Concept library location: `{CONCEPTS_PATH}`.

### Flow

1. **Scan** every `[[Concept]]` link in the paper note.
2. **Check** whether a corresponding concept note exists for each link with `ls` and `find`.
3. **Create** missing concepts without skipping any, automatically categorizing them into the appropriate subdirectory.

> Categorization rules and template are in `references/concept-categories.md`.

### Self-Check

- [ ] Does every `[[Concept]]` link in the note have a concept note?
- [ ] Does each concept note include this paper as a representative work?

## 6. Final Self-Check

- [ ] Are all figures included in the note, matching the paper's count?
- [ ] Are all formulas included, with consistent variables and no conflicts?
- [ ] Are all tables fully preserved with all rows and columns?
- [ ] Are technical terms linked inline with `[[Concept]]` links?
- [ ] Has the concept library been updated with missing concepts?
- [ ] Are images usable, either as reachable external links or local files larger than 10 KB?

## 7. Interactive Follow-Ups

After analysis, ask whether the user wants a deeper explanation, comparison with other papers, or saving to Obsidian.
After saving, automatically create missing concept notes and report how many concepts were added.

## 8. Batch processing

Supports batch processing for Zotero collections, recursively including child collections by default. Flow: recursively fetch papers -> deduplicate -> skip existing notes -> process one by one -> summarize.

When this skill is invoked by `daily-papers-notes`, it acts as a **single-paper executor**. Parallel splitting, subagent orchestration, retries, and aggregation are owned by the parent skill; do not take over batch scheduling here.

## Reference Files (Read as Needed)

- **`references/zotero-guide.md`**: Zotero querying, classification, PDF path retrieval, and intelligent categorization
- **`references/image-troubleshooting.md`**: ar5iv figure-number mapping and PDF extraction fallback
- **`references/concept-categories.md`**: concept auto-categorization rules and template; actual directories come from shared config
- **`references/cv-dl-terminology.md`**: shared terminology entry point; actual terminology lives in `domain.terminology` inside `../_shared/user-config.json`
- **`references/quality-standards.md`**: detailed quality rules for formulas, images, and tables, plus self-checks
