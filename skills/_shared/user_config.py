#!/usr/bin/env python3

import json
from functools import lru_cache
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().with_name("user-config.json")


@lru_cache(maxsize=1)
def load_user_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
    if not isinstance(loaded, dict):
        raise ValueError(f"Config file must contain a JSON object: {CONFIG_PATH}")
    return loaded


def _expand(path_value: str) -> Path:
    return Path(path_value).expanduser()


def paths_config() -> dict:
    return load_user_config()["paths"]


def domain_config() -> dict:
    return load_user_config()["domain"]


def daily_papers_config() -> dict:
    return load_user_config()["daily_papers"]


def paper_notes_taxonomy_config() -> dict:
    return load_user_config()["paper_notes_taxonomy"]


def automation_config() -> dict:
    config = load_user_config()["automation"]
    if config.get("git_push") and not config.get("git_commit"):
        config = dict(config)
        config["git_push"] = False
    return config


def obsidian_vault_path() -> Path:
    return _expand(paths_config()["obsidian_vault"])


def paper_notes_dir() -> Path:
    return obsidian_vault_path() / paths_config()["paper_notes_folder"]


def daily_papers_dir() -> Path:
    return obsidian_vault_path() / paths_config()["daily_papers_folder"]


def concepts_dir() -> Path:
    return paper_notes_dir() / paths_config()["concepts_folder"]


def zotero_db_path() -> Path:
    return _expand(paths_config()["zotero_db"])


def zotero_storage_dir() -> Path:
    return _expand(paths_config()["zotero_storage"])


def temp_dir() -> Path:
    return _expand(paths_config()["temp_dir"])


def temp_file_path(filename: str) -> Path:
    return temp_dir() / filename


def focus_themes() -> list[str]:
    return list(domain_config().get("focus_themes", []))


def related_themes() -> list[str]:
    return list(domain_config().get("related_themes", []))


def terminology_config() -> list[dict]:
    return list(domain_config().get("terminology", []))


def frontmatter_keywords() -> list[str]:
    ordered = []
    seen = set()
    for theme in focus_themes() + related_themes():
        normalized = str(theme).strip()
        if not normalized:
            continue
        dedupe_key = normalized.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        ordered.append(normalized)
    return ordered


def frontmatter_keywords_csv() -> str:
    return ", ".join(keyword.lower() for keyword in frontmatter_keywords())


def frontmatter_tags() -> list[str]:
    return list(daily_papers_config().get("frontmatter_tags", []))


def paper_notes_taxonomy_categories() -> list[dict]:
    return list(paper_notes_taxonomy_config().get("categories", []))


def paper_notes_taxonomy_fallback_category() -> str:
    return str(paper_notes_taxonomy_config().get("fallback_category", "_inbox"))


def concept_taxonomy_fallback_category() -> str:
    return str(paper_notes_taxonomy_config().get("concept_fallback_category", "0-uncategorized"))


def auto_refresh_indexes_enabled() -> bool:
    return bool(automation_config()["auto_refresh_indexes"])


def git_commit_enabled() -> bool:
    return bool(automation_config()["git_commit"])


def git_push_enabled() -> bool:
    return bool(automation_config()["git_push"])
