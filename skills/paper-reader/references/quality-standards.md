# Paper Note Quality Standards

These standards define what a complete paper note must contain. They are stricter than a normal summary because the note should be useful for future research work.

## Zero-Omission Principle

Every paper note must include all important technical artifacts from the paper:

- every figure
- every formula
- every table
- the core algorithm or training/inference procedure
- key baselines and evaluation metrics

Do not replace these with vague prose.

## Figures

**Every paper note must contain all figures from the paper. Do not omit any.**

For each figure:

- include the image itself
- include the figure number or title when available
- explain what the figure shows
- explain why it matters for the paper's claim

## Formulas

Every central formula must include:

- a descriptive name linked to a concept when appropriate, such as `[[Contrastive Loss|Contrastive Loss]]`
- a LaTeX `$$` block
- an explanation of what the formula means
- a symbol list

Make sure there is a blank line before and after every `$$` block so Obsidian renders it.

## Tables

All important tables must be preserved or summarized faithfully. If a table is too large, keep the key rows and columns and explain what was omitted.

## Self-Check

**Zero omissions: all figures, all formulas, and all tables must appear in the note.**

- [ ] How many figures are in the paper? Are all included in the note?
- [ ] How many formulas are in the paper? Are all included in the note?
- [ ] How many tables are in the paper? Are all included or faithfully summarized?
- [ ] Are formulas named, explained, and rendered as LaTeX?
- [ ] Are technical terms linked inline with `[[Concept]]` links?
- [ ] Are all image links reachable or localized?
- [ ] Does the note have enough detail to reconstruct the method without rereading the full paper?
