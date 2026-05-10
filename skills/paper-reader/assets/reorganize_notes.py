#!/usr/bin/env python3
"""
Automatic paper-note categorization tool
Automatically categorize paper notes by tags and content, and synchronize Zotero collections
"""

import os
import csv
import re
import sys
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Optional, Dict, List

_SHARED_DIR = Path(__file__).resolve().parents[2] / "_shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from user_config import (
    paper_notes_dir,
    paper_notes_taxonomy_categories,
    paper_notes_taxonomy_fallback_category,
    paths_config,
    zotero_db_path,
)

# Config
PAPER_NOTES_ROOT = paper_notes_dir()
ZOTERO_DB = zotero_db_path()
CONCEPTS_DIR_NAME = paths_config()["concepts_folder"]

_TAXONOMY_CATEGORIES = paper_notes_taxonomy_categories()
FALLBACK_CATEGORY = paper_notes_taxonomy_fallback_category()
CATEGORY_RULES = {
    item["name"]: item.get("keywords", [])
    for item in _TAXONOMY_CATEGORIES
}
ZOTERO_COLLECTION_MAP = {
    item["name"]: item.get("zotero_collection_id")
    for item in _TAXONOMY_CATEGORIES
}


def parse_frontmatter(filepath: Path) -> Optional[Dict]:
    """Parse YAML frontmatter from a Markdown file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        if not content.startswith('---'):
            return None

        # Find the second ---
        end_idx = content.find('---', 3)
        if end_idx == -1:
            return None

        yaml_str = content[3:end_idx].strip()
        return parse_simple_frontmatter(yaml_str)
    except Exception as e:
        print(f"  Parse failed: {e}")
        return None


def parse_simple_frontmatter(frontmatter: str) -> Dict[str, Any]:
    """Parse the simple YAML frontmatter used by this project, supporting only top-level scalars and lists."""
    parsed: Dict[str, Any] = {}
    current_list_key: Optional[str] = None

    for raw_line in frontmatter.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith('#'):
            continue

        if raw_line.startswith((' ', '\t')):
            stripped = raw_line.strip()
            if current_list_key and stripped.startswith('- '):
                parsed[current_list_key].append(parse_frontmatter_value(stripped[2:].strip()))
            continue

        current_list_key = None
        if ':' not in raw_line:
            continue

        key, raw_value = raw_line.split(':', 1)
        key = key.strip()
        value = raw_value.strip()
        if not key:
            continue

        if not value:
            parsed[key] = []
            current_list_key = key
            continue

        parsed[key] = parse_frontmatter_value(value)

    return parsed


def parse_frontmatter_value(raw_value: str) -> Any:
    value = strip_inline_comment(raw_value).strip()
    if not value:
        return ""

    if value.startswith('[') and value.endswith(']'):
        inner = value[1:-1].strip()
        if not inner:
            return []
        items = next(csv.reader([inner], skipinitialspace=True))
        return [parse_frontmatter_scalar(item) for item in items if item.strip()]

    return parse_frontmatter_scalar(value)


def parse_frontmatter_scalar(raw_value: str) -> Any:
    value = raw_value.strip()
    if not value:
        return ""

    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]

    lowered = value.lower()
    if lowered == 'true':
        return True
    if lowered == 'false':
        return False

    if re.fullmatch(r'-?\d+', value):
        return int(value)
    if re.fullmatch(r'-?\d+\.\d+', value):
        return float(value)

    return value


def strip_inline_comment(raw_value: str) -> str:
    in_single_quote = False
    in_double_quote = False

    for idx, char in enumerate(raw_value):
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif char == '#' and not in_single_quote and not in_double_quote:
            return raw_value[:idx].rstrip()

    return raw_value.rstrip()


def determine_category(tags: List[str], title: str = "") -> str:
    """Determine which collection a paper belongs to from tags"""
    if not tags:
        return FALLBACK_CATEGORY

    # Ensure all tags are strings
    tags_lower = [str(t).lower() for t in tags]
    title_lower = title.lower()

    # Compute each category match score while considering priority
    scores = {}
    priority_bonus = len(CATEGORY_RULES)  # priority bonus base

    for idx, (category, keywords) in enumerate(CATEGORY_RULES.items()):
        score = 0
        for keyword in keywords:
            keyword_lower = keyword.lower()
            # Check tags
            for tag in tags_lower:
                if keyword_lower in tag or tag in keyword_lower:
                    score += 2
            # Check title
            if keyword_lower in title_lower:
                score += 1

        # Add priority bonus, so earlier categories win ties
        if score > 0:
            score = score * 100 + (priority_bonus - idx)

        scores[category] = score

    # Return the highest-scoring category
    best_category = max(scores, key=scores.get)
    if scores[best_category] > 0:
        return best_category
    return FALLBACK_CATEGORY


def get_all_notes() -> List[Path]:
    """Get all paper notes"""
    notes = []
    for root, dirs, files in os.walk(PAPER_NOTES_ROOT):
        # Skip concept directory
        if CONCEPTS_DIR_NAME in Path(root).parts:
            continue
        for f in files:
            if f.endswith('.md'):
                note_path = Path(root) / f
                if note_path.name == "_index.md":
                    continue
                if note_path.parent == PAPER_NOTES_ROOT and note_path.stem == PAPER_NOTES_ROOT.name:
                    continue
                if note_path.parent.name == note_path.stem:
                    continue
                notes.append(note_path)
    return notes


def reorganize_notes(dry_run: bool = True):
    """Reorganize paper notes"""
    notes = get_all_notes()
    print(f"Found {len(notes)} paper notes\n")

    moves = []  # (old path, new path, category, zotero_item_id, current Zotero category)

    for note in notes:
        fm = parse_frontmatter(note)
        if not fm:
            print(f"Skip (no frontmatter): {note.name}")
            continue

        tags = fm.get('tags', [])
        title = fm.get('title', note.stem)
        zotero_item_id = fm.get('zotero_item_id')
        current_collection = fm.get('zotero_collection', '')

        # Prefer the zotero_collection path declared in frontmatter
        declared_collection = str(current_collection).strip() if current_collection else ""
        if declared_collection and declared_collection != "_inbox":
            new_category = declared_collection
        else:
            new_category = determine_category(tags, title)

        # Current directory
        current_rel = note.relative_to(PAPER_NOTES_ROOT)
        current_dir = str(current_rel.parent)

        # Skip if already in the correct category
        if current_dir.startswith(new_category):
            print(f"✓ Already correctly categorized: {note.name} -> {new_category}")
            continue

        # new path
        new_path = PAPER_NOTES_ROOT / new_category / note.name

        moves.append((note, new_path, new_category, zotero_item_id, current_collection))
        print(f"→ Needs move: {note.name}")
        print(f"  From: {current_dir}")
        print(f"  To: {new_category}")
        print(f"  tags: {tags[:5]}...")
        print()

    print(f"\ntotal notes to move: {len(moves)} notes")

    if dry_run:
        print("\n[DRY RUN] No moves executed; add --execute to apply changes")
        return moves

    # Execute moves
    for old_path, new_path, category, zotero_id, current_collection in moves:
        # Create target directory
        new_path.parent.mkdir(parents=True, exist_ok=True)

        # Move file
        shutil.move(str(old_path), str(new_path))
        print(f"✓ Moved: {old_path.name} -> {category}/")

        # Update Zotero category
        zotero_collection_value = category
        if zotero_id:
            synced_collection = update_zotero_collection(zotero_id, category, current_collection)
            if synced_collection:
                zotero_collection_value = synced_collection

        # Update zotero_collection in frontmatter
        update_frontmatter_collection(new_path, zotero_collection_value)

    return moves


def update_frontmatter_collection(filepath: Path, new_collection: str):
    """Update the note zotero_collection field"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Replace zotero_collection
        if 'zotero_collection:' in content:
            content = re.sub(
                r'^zotero_collection:.*$',
                f'zotero_collection: {new_collection}',
                content,
                flags=re.MULTILINE,
            )
        elif content.startswith('---'):
            end_idx = content.find('---', 3)
            if end_idx != -1:
                content = content[:end_idx] + f"zotero_collection: {new_collection}\n" + content[end_idx:]

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        print(f"  Failed to update frontmatter: {e}")


def get_collection_path(collections: Dict[int, Dict[str, Optional[int]]], collection_id: int) -> str:
    """Get full category path, such as top-level/subtopic/theme"""
    path_parts = []
    current = collection_id
    while current:
        info = collections.get(current)
        if not info:
            break
        path_parts.insert(0, info['name'])
        current = info['parent']
    return '/'.join(path_parts)


def resolve_collection_id(
    collection_ref: str,
    collections: Dict[int, Dict[str, Optional[int]]],
    path_to_id: Dict[str, int],
    name_to_ids: Dict[str, List[int]],
) -> Optional[int]:
    """Resolve collection ID by full path, ID, or unique leaf category name."""
    if not collection_ref:
        return None

    ref = str(collection_ref).strip()
    if not ref:
        return None

    if ref.isdigit():
        cid = int(ref)
        return cid if cid in collections else None

    if ref in path_to_id:
        return path_to_id[ref]

    leaf_name = ref.split('/')[-1]
    matched_ids = name_to_ids.get(leaf_name, [])
    if len(matched_ids) == 1:
        return matched_ids[0]

    return None


def update_zotero_collection(item_id: int, new_category: str, current_collection: str = "") -> Optional[str]:
    """Update paper category in Zotero"""
    collection_id = ZOTERO_COLLECTION_MAP.get(new_category)
    if not collection_id:
        print(f"  Zotero category is not configured: {new_category}")
        return None

    if not ZOTERO_DB.exists():
        print(f"  Zotero database does not exist: {ZOTERO_DB}")
        return None

    conn = None
    try:
        conn = sqlite3.connect(ZOTERO_DB, timeout=10)
        cursor = conn.cursor()

        cursor.execute("SELECT collectionID, collectionName, parentCollectionID FROM collections")
        collections = {
            row[0]: {'name': row[1], 'parent': row[2]}
            for row in cursor.fetchall()
        }
        path_to_id = {get_collection_path(collections, cid): cid for cid in collections}
        name_to_ids: Dict[str, List[int]] = {}
        for cid, info in collections.items():
            name_to_ids.setdefault(info['name'], []).append(cid)

        target_path = get_collection_path(collections, collection_id)
        previous_collection_id = resolve_collection_id(current_collection, collections, path_to_id, name_to_ids)

        cursor.execute(
            """
            SELECT 1 FROM collectionItems
            WHERE collectionID = ? AND itemID = ?
            """,
            (collection_id, item_id),
        )
        already_in_target = cursor.fetchone() is not None
        if not already_in_target:
            cursor.execute(
                """
                INSERT INTO collectionItems (collectionID, itemID, orderIndex)
                VALUES (?, ?, 0)
                """,
                (collection_id, item_id),
            )
            print(f"  Added Zotero item {item_id} to collection {target_path}")
        else:
            print(f"  Zotero item {item_id} is already in collection {target_path}")

        if previous_collection_id and previous_collection_id != collection_id:
            cursor.execute(
                """
                DELETE FROM collectionItems
                WHERE collectionID = ? AND itemID = ?
                """,
                (previous_collection_id, item_id),
            )
            if cursor.rowcount > 0:
                print(f"  Removed Zotero item {item_id} from previous category {get_collection_path(collections, previous_collection_id)}")

        conn.commit()
        return target_path
    except Exception as e:
        if conn is not None:
            conn.rollback()
        print(f"  Failed to update Zotero: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def analyze_current_distribution():
    """Analyze current note distribution"""
    notes = get_all_notes()

    category_count = {}
    for note in notes:
        fm = parse_frontmatter(note)
        if not fm:
            continue

        tags = fm.get('tags', [])
        title = fm.get('title', note.stem)
        category = determine_category(tags, title)

        category_count[category] = category_count.get(category, 0) + 1

    print("=== Counts by New Category ===")
    for cat, count in sorted(category_count.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count} papers")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--analyze":
        analyze_current_distribution()
    elif len(sys.argv) > 1 and sys.argv[1] == "--execute":
        reorganize_notes(dry_run=False)
    else:
        reorganize_notes(dry_run=True)
