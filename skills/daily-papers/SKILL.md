---
name: daily-papers
description: |
  One-prompt entry point for daily paper recommendations. Use when the user asks for
  "today's paper recommendations", "paper recommendations from the last 3 days",
  "paper recommendations from the last week", "recent papers", or "what papers are worth reading this week".

  Internally chains the three-step pipeline: paper fetching, recommendation review,
  and focused paper-note generation. The user does not need to run each step manually.
  Default sources cover Hugging Face, arXiv, PubMed, bioRxiv, and medRxiv, with unified deduplication before review.
---

# Daily Paper Recommendations

This is the user-facing one-prompt entry point. Normally, the user only needs to ask once:

- `today's paper recommendations`
- `paper recommendations from the last 3 days`
- `paper recommendations from the last week`

## Execution Rules

1. First identify the time range:
   - `today's paper recommendations`, `daily paper recommendations`, `today's papers` -> today
   - `paper recommendations from the last 3 days`, `recent papers from the last 3 days` -> 3 days
   - `paper recommendations from the last week`, `what papers are worth reading this week` -> 7 days
2. Automatically invoke the `daily-papers-fetch` skill.
3. After step 1 completes, automatically invoke the `daily-papers-review` skill.
4. After step 2 completes, automatically invoke the `daily-papers-notes` skill.
5. When everything is complete, tell the user in one sentence:
   - the recommendation file was generated
   - how many focused paper notes were generated
   - whether index pages were refreshed automatically
6. Paper topics, filtering direction, and review emphasis must all come from the single config file `../_shared/user-config.json`. Do not maintain a second research-topic definition in any skill.

## Important Constraints

- Do not ask the user to manually run `fetch papers / review papers / generate paper notes` first.
- Those three prompts are internal pipeline and debugging entry points, not the main home interaction.
- If the user explicitly wants to run only one step, hand off to the corresponding skill.

## Automation

- This skill is itself the "run the full pipeline in one step" entry point.
- If the user wants a local scheduled task, default to triggering this one prompt rather than hard-coding the three internal commands.
