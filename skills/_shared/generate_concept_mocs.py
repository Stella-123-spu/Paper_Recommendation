#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from pathlib import Path


_SHARED_DIR = Path(__file__).resolve().parent
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from moc_builder import build_tree_mocs
from user_config import concepts_dir, obsidian_vault_path


def main() -> int:
    summary = build_tree_mocs(
        vault_root=obsidian_vault_path(),
        root_dir=concepts_dir(),
        title_prefix="Concept Index",
        intro="Use this page to browse concept notes and category entry points.",
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
