# Paper Recommendation Skills Mirror

This repository is the canonical copy of the paper recommendation skills.

Upstream acknowledgement:

- This skill set is derived from [huangkiki/dailypaper-skills](https://github.com/huangkiki/dailypaper-skills), with local adaptations for this workflow and vault setup.

Tracked skill folders:

- `skills/_shared`
- `skills/daily-papers`
- `skills/daily-papers-fetch`
- `skills/daily-papers-review`
- `skills/daily-papers-notes`
- `skills/paper-reader`

Shared configuration:

- `skills/_shared/user-config.json` is the single source of truth for paths, domain focus, daily-paper scoring keywords, and paper-note taxonomy.

Local sync model:

- The directories under `~/.codex/skills/` for the folders above are symbolic links to this repository.
- Edit either path and you are editing the same underlying files.
- New files added inside these linked directories are immediately visible from both locations.

Backup of the original non-linked skill folders was created locally before switching to this layout.
