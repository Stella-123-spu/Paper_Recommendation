# Shared Terminology

This file is a lightweight entry point for terminology lookup.

The active domain terminology lives in:

- `../_shared/user-config.json`
- section: `domain.terminology`

Use that config as the source of truth for categories, aliases, and short definitions. Do not maintain a second terminology table here.

## Usage

When creating notes:

1. Check whether a term appears in `domain.terminology`.
2. Use the configured English term as the canonical concept-note title.
3. Use aliases for matching only; do not create duplicate concept notes for aliases.
4. If a term is important but missing from the config, create a concept note under the best matching taxonomy category and consider updating config later.
