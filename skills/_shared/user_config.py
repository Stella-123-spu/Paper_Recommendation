#!/usr/bin/env python3

import copy
import json
from functools import lru_cache
from pathlib import Path


DEFAULT_CONFIG = {
    "paths": {
        "obsidian_vault": "~/ObsidianVault",
        "paper_notes_folder": "论文笔记",
        "daily_papers_folder": "DailyPapers",
        "concepts_folder": "_概念",
        "zotero_db": "~/Zotero/zotero.sqlite",
        "zotero_storage": "~/Zotero/storage",
    },
    "daily_papers": {
        "keywords": [
            "AI for healthcare",
            "Patient trajectory modeling",
            "Longitudinal EHR modeling",
            "Large language models",
            "Clinical LLM",
            "EHR foundation model",
            "Agentic RL",
            "Medical world model",
            "trajectory analysis",
            "electronic health record",
            "temporal reasoning",
        ],
        "negative_keywords": [
            "weather forecast",
            "climate",
            "pet restoration",
            "audio generation",
            "music generation",
            "speech synthesis",
            "text-to-speech",
            "speech recognition",
            "voice cloning",
            "trading",
            "financial",
        ],
        "domain_boost_keywords": [
            "Medical",
            "Trajectory",
            "EHR",
            "Progression",
            "Foundation model",
            "multi-agent",
            "reinforcement learning",
            "World model",
            "Multimodal",
            "Causal",
            "Intervention",
        ],
        "arxiv_categories": ["cs.CL", "cs.MA", "cs.AI", "cs.GR"],
        "min_score": 2,
        "top_n": 30,
    },
    "automation": {
        "auto_refresh_indexes": True,
        "git_commit": False,
        "git_push": False,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


@lru_cache(maxsize=1)
def load_user_config() -> dict:
    config = copy.deepcopy(DEFAULT_CONFIG)
    config_dir = Path(__file__).resolve().parent

    for filename in ("user-config.json", "user-config.local.json"):
        config_path = config_dir / filename
        if not config_path.exists():
            continue
        with config_path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            _deep_merge(config, loaded)

    return config


def _expand(path_value: str) -> Path:
    return Path(path_value).expanduser()


def paths_config() -> dict:
    return load_user_config()["paths"]


def daily_papers_config() -> dict:
    return load_user_config()["daily_papers"]


def automation_config() -> dict:
    config = load_user_config()["automation"]
    if config.get("git_push") and not config.get("git_commit"):
        config = copy.deepcopy(config)
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


def auto_refresh_indexes_enabled() -> bool:
    return bool(automation_config()["auto_refresh_indexes"])


def git_commit_enabled() -> bool:
    return bool(automation_config()["git_commit"])


def git_push_enabled() -> bool:
    return bool(automation_config()["git_push"])
