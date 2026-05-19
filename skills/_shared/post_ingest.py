#!/usr/bin/env python3
"""
post_ingest.py — Post-ingest hook for wiki maintenance.

Called by daily-papers-review / daily-papers-notes / conference-papers / paper-reader
after a successful ingest. Does two things:

  1. Append a structured entry to {vault}/log.md
  2. Re-generate {vault}/index.md via generate_wiki_index.py

Usage:
    python3 post_ingest.py <operation> "<details>"

Examples:
    python3 post_ingest.py ingest:daily "3-day window 2026-05-12 → 2026-05-14 → 20 recommendations + 4 notes"
    python3 post_ingest.py ingest:venue:NeurIPS-2024 "4035 raw → 120 top → 20 recommended + 4 notes"
    python3 post_ingest.py ingest:paper "EHR-RAGp deep note generated"
    python3 post_ingest.py review "20-paper review file written to DailyPapers/2026-05-14-..."

If <details> is omitted, the entry is logged with empty details (still parseable).
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from user_config import obsidian_vault_path


def append_log(vault: Path, operation: str, details: str) -> None:
    log_path = vault / "log.md"
    if not log_path.exists():
        log_path.write_text(
            "# Wiki Operation Log\n\n"
            "Append-only journal of all ingest / query / lint / schema operations on this vault.\n\n"
            "Format: `## [YYYY-MM-DD HH:MM] <operation> | <details>`\n\n---\n\n",
            encoding="utf-8",
        )
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"## [{ts}] {operation} | {details}\n"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(entry)
    print(f"  log.md ← {entry.strip()}", file=sys.stderr)


def regenerate_index(vault: Path) -> bool:
    script = _HERE / "generate_wiki_index.py"
    if not script.exists():
        print(f"  index regenerator not found at {script}", file=sys.stderr)
        return False
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=str(_HERE),
    )
    if result.returncode == 0:
        print("  index.md regenerated", file=sys.stderr)
        return True
    print(f"  index regen failed (exit {result.returncode}): {result.stderr}", file=sys.stderr)
    return False


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    operation = sys.argv[1].strip()
    details = sys.argv[2].strip() if len(sys.argv) >= 3 else ""

    vault = obsidian_vault_path()
    if not vault.exists():
        print(f"vault {vault} does not exist", file=sys.stderr)
        return 1

    print(f"post_ingest: operation={operation}", file=sys.stderr)
    append_log(vault, operation, details)
    regenerate_index(vault)
    return 0


if __name__ == "__main__":
    sys.exit(main())
