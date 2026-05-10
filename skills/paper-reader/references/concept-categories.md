# Concept Categorization

Read the `paper_notes_taxonomy` section in `../_shared/user-config.json` first. **Directory names, keywords, priority, and Zotero mapping all come from that one config.**

## Categorization Rules

1. Run `ls {CONCEPTS_PATH}` to inspect existing subdirectories.
2. Match concepts against `paper_notes_taxonomy.categories[*].keywords`.
3. If a concept matches multiple categories, choose the earliest category in config order.
4. If no category matches, use `concept_fallback_category` from config.
5. Do not create ad hoc top-level categories unless the user explicitly requests a taxonomy change.

to quickly inspect the current taxonomy, open `../_shared/user-config.json` and check:

- `paper_notes_taxonomy.categories[].name`
- `paper_notes_taxonomy.categories[].keywords`
- `paper_notes_taxonomy.concept_fallback_category`

## Concept Note Template

```markdown
---
type: concept
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: [concept]
---

# Concept Name

## Definition

Explain the concept in 2-4 precise sentences.

## Why It Matters

Explain why this concept matters for the current shared-config domain.

## Representative Works

- [[Paper Note]]: one sentence explaining why the paper represents this concept.

## Related Concepts

- [[Related Concept]]:
```

## Quality Requirements

- Keep concept notes concise and reusable.
- Link representative paper notes with `[[wikilinks]]`.
- Avoid duplicating a whole paper summary inside a concept note.
- Prefer the most specific category that matches the concept's primary use.
