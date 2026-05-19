#!/usr/bin/env python3
"""
Zotero database query helper script
Used by the paper-reader skill for Zotero integration
"""

import sqlite3
import os
import shutil
import argparse
import sys
import json
import re
import datetime
from pathlib import Path

_SHARED_DIR = Path(__file__).resolve().parents[2] / "_shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from user_config import zotero_db_path, zotero_storage_dir

# Default config — env vars override for sandbox / non-standard installs
ZOTERO_DB = Path(os.environ["ZOTERO_DB"]).expanduser() if os.environ.get("ZOTERO_DB") else zotero_db_path()
STORAGE_DIR = Path(os.environ["ZOTERO_STORAGE"]).expanduser() if os.environ.get("ZOTERO_STORAGE") else zotero_storage_dir()
ZOTERO_DIR = ZOTERO_DB.parent
TEMP_DB = Path("/tmp/zotero_readonly.sqlite")


def copy_db():
    """Copy the database to avoid locking"""
    shutil.copy(ZOTERO_DB, TEMP_DB)
    return sqlite3.connect(TEMP_DB)


def get_all_child_collections(conn, collection_id: int) -> list[int]:
    """Recursively get all child collection IDs, including itself"""
    cursor = conn.cursor()
    cursor.execute("SELECT collectionID, parentCollectionID FROM collections")
    all_collections = cursor.fetchall()

    # Build parent-child relationship map
    children_map = {}
    for cid, parent_id in all_collections:
        if parent_id not in children_map:
            children_map[parent_id] = []
        children_map[parent_id].append(cid)

    # Recursively collect all child collections
    result = [collection_id]
    def collect_children(cid):
        if cid in children_map:
            for child_id in children_map[cid]:
                result.append(child_id)
                collect_children(child_id)

    collect_children(collection_id)
    return result


def list_collections(conn):
    """List all collections"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.collectionID, c.collectionName, c.parentCollectionID,
               COUNT(ci.itemID) as item_count
        FROM collections c
        LEFT JOIN collectionItems ci ON c.collectionID = ci.collectionID
        GROUP BY c.collectionID
        ORDER BY c.parentCollectionID NULLS FIRST, c.collectionName
    """)

    print("ID\t| Collection Name\t\t\t| Parent\t| Item Count")
    print("-" * 70)
    for row in cursor.fetchall():
        parent = str(row[2]) if row[2] else "Root directory"
        name = row[1][:24] if row[1] else ""
        print(f"{row[0]}\t| {name:24}\t| {parent:8}\t| {row[3]}")


def list_papers_in_collection(conn, collection_id, recursive=False):
    """List papers under a collection, optionally including child collections recursively"""
    cursor = conn.cursor()

    if recursive:
        collection_ids = get_all_child_collections(conn, collection_id)
        placeholders = ','.join('?' * len(collection_ids))
        query = f"""
            SELECT DISTINCT i.itemID, idv.value as title,
                   (SELECT value FROM itemData id2
                    JOIN itemDataValues idv2 ON id2.valueID = idv2.valueID
                    JOIN fields f2 ON id2.fieldID = f2.fieldID
                    WHERE id2.itemID = i.itemID AND f2.fieldName = 'date' LIMIT 1) as date
            FROM items i
            JOIN collectionItems ci ON i.itemID = ci.itemID
            JOIN itemData id ON i.itemID = id.itemID
            JOIN itemDataValues idv ON id.valueID = idv.valueID
            JOIN fields f ON id.fieldID = f.fieldID
            WHERE ci.collectionID IN ({placeholders})
              AND f.fieldName = 'title'
              AND i.itemTypeID != 14
            ORDER BY date DESC
        """
        cursor.execute(query, collection_ids)
        print(f"(Recursive query including {len(collection_ids)} collections)")
    else:
        cursor.execute("""
            SELECT i.itemID, idv.value as title,
                   (SELECT value FROM itemData id2
                    JOIN itemDataValues idv2 ON id2.valueID = idv2.valueID
                    JOIN fields f2 ON id2.fieldID = f2.fieldID
                    WHERE id2.itemID = i.itemID AND f2.fieldName = 'date' LIMIT 1) as date
            FROM items i
            JOIN collectionItems ci ON i.itemID = ci.itemID
            JOIN itemData id ON i.itemID = id.itemID
            JOIN itemDataValues idv ON id.valueID = idv.valueID
            JOIN fields f ON id.fieldID = f.fieldID
            WHERE ci.collectionID = ?
              AND f.fieldName = 'title'
              AND i.itemTypeID != 14
            ORDER BY date DESC
        """, (collection_id,))

    print("ItemID\t| Date\t\t| Title")
    print("-" * 80)
    for row in cursor.fetchall():
        title = row[1][:50] if row[1] else ""
        date = row[2][:10] if row[2] else "N/A"
        print(f"{row[0]}\t| {date}\t| {title}")


def search_paper(conn, keyword):
    """Search paper titles"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT i.itemID, idv.value as title,
               (SELECT value FROM itemData id2
                JOIN itemDataValues idv2 ON id2.valueID = idv2.valueID
                JOIN fields f2 ON id2.fieldID = f2.fieldID
                WHERE id2.itemID = i.itemID AND f2.fieldName = 'date' LIMIT 1) as date
        FROM items i
        JOIN itemData id ON i.itemID = id.itemID
        JOIN itemDataValues idv ON id.valueID = idv.valueID
        JOIN fields f ON id.fieldID = f.fieldID
        WHERE f.fieldName = 'title'
          AND i.itemTypeID != 14
          AND idv.value LIKE ?
        ORDER BY date DESC
        LIMIT 20
    """, (f"%{keyword}%",))

    print(f"Search: '{keyword}'")
    print("ItemID\t| Date\t\t| Title")
    print("-" * 80)
    for row in cursor.fetchall():
        title = row[1][:50] if row[1] else ""
        date = row[2][:10] if row[2] else "N/A"
        print(f"{row[0]}\t| {date}\t| {title}")


def get_pdf_path(conn, item_id):
    """Get paper PDF path"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ia.path, items.key,
               (SELECT value FROM itemData id
                JOIN itemDataValues idv ON id.valueID = idv.valueID
                JOIN fields f ON id.fieldID = f.fieldID
                WHERE id.itemID = ia.parentItemID AND f.fieldName = 'title') as title
        FROM itemAttachments ia
        JOIN items ON ia.itemID = items.itemID
        WHERE ia.parentItemID = ? AND ia.contentType = 'application/pdf'
    """, (item_id,))

    row = cursor.fetchone()
    if row:
        path, key, title = row
        if path and path.startswith('storage:'):
            filename = path.replace('storage:', '')
            full_path = STORAGE_DIR / key / filename
            print(f"Title: {title}")
            print(f"PDF path: {full_path}")
            if full_path.exists():
                print(f"File exists: Yes")
                return str(full_path)
            else:
                print(f"File exists: No")
    else:
        print(f"No PDF attachment found for itemID={item_id}")
    return None


def get_collection_path(conn, collection_id):
    """Get the full collection path"""
    cursor = conn.cursor()
    cursor.execute("SELECT collectionID, collectionName, parentCollectionID FROM collections")
    collections = {row[0]: {'name': row[1], 'parent': row[2]} for row in cursor.fetchall()}

    path_parts = []
    current = collection_id
    while current:
        if current in collections:
            path_parts.insert(0, collections[current]['name'])
            current = collections[current]['parent']
        else:
            break
    return '/'.join(path_parts)


def get_item_collections(conn, item_id):
    """Get all collections containing the paper"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.collectionID, c.collectionName
        FROM collections c
        JOIN collectionItems ci ON c.collectionID = ci.collectionID
        WHERE ci.itemID = ?
    """, (item_id,))
    return cursor.fetchall()


def add_to_collection_db(item_id, collection_id):
    """Add a paper to a collection, directly modifying the original database"""
    # Warning: this directly modifies the Zotero database
    conn = sqlite3.connect(ZOTERO_DB)
    cursor = conn.cursor()
    try:
        # Check whether the item already exists
        cursor.execute("""
            SELECT 1 FROM collectionItems
            WHERE collectionID = ? AND itemID = ?
        """, (collection_id, item_id))
        if cursor.fetchone():
            print(f"Paper {item_id} is already in collection {collection_id}")
            return False

        # Add to collection
        cursor.execute("""
            INSERT INTO collectionItems (collectionID, itemID, orderIndex)
            VALUES (?, ?, 0)
        """, (collection_id, item_id))
        conn.commit()
        print(f"Added paper {item_id} to collection {collection_id}")
        return True
    except Exception as e:
        print(f"Add failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def remove_from_collection_db(item_id, collection_id):
    """Remove a paper from a collection"""
    conn = sqlite3.connect(ZOTERO_DB)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            DELETE FROM collectionItems
            WHERE collectionID = ? AND itemID = ?
        """, (collection_id, item_id))
        if cursor.rowcount > 0:
            conn.commit()
            print(f"Removed paper {item_id} from collection {collection_id}")
            return True
        else:
            print(f"Paper {item_id} is not in collection {collection_id}")
            return False
    except Exception as e:
        print(f"Remove failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def move_to_collection(item_id, new_collection_id, old_collection_id=None):
    """Move a paper to a new collection by adding it to the new one and removing it from the old one"""
    # Add to the new collection first
    add_to_collection_db(item_id, new_collection_id)

    # If an old collection is specified, remove it from that collection
    if old_collection_id:
        remove_from_collection_db(item_id, old_collection_id)


def find_collection_by_name(conn, name):
    """Find collections by name"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT collectionID, collectionName, parentCollectionID
        FROM collections
        WHERE collectionName LIKE ?
    """, (f"%{name}%",))
    results = cursor.fetchall()
    for r in results:
        path = get_collection_path(conn, r[0])
        print(f"ID: {r[0]}, Path: {path}")
    return results


def get_paper_info(conn, item_id):
    """Get detailed paper information"""
    cursor = conn.cursor()

    # Get title
    cursor.execute("""
        SELECT idv.value
        FROM itemData id
        JOIN itemDataValues idv ON id.valueID = idv.valueID
        JOIN fields f ON id.fieldID = f.fieldID
        WHERE id.itemID = ? AND f.fieldName = 'title'
    """, (item_id,))
    title_row = cursor.fetchone()
    title = title_row[0] if title_row else "Unknown"

    # Get other fields
    cursor.execute("""
        SELECT f.fieldName, idv.value
        FROM itemData id
        JOIN itemDataValues idv ON id.valueID = idv.valueID
        JOIN fields f ON id.fieldID = f.fieldID
        WHERE id.itemID = ?
    """, (item_id,))
    fields = {row[0]: row[1] for row in cursor.fetchall()}

    # Get containing collections
    collections = get_item_collections(conn, item_id)
    collection_paths = [get_collection_path(conn, c[0]) for c in collections]

    print(f"ItemID: {item_id}")
    print(f"Title: {title}")
    print(f"Date: {fields.get('date', 'N/A')}")
    print(f"URL: {fields.get('url', 'N/A')}")
    print(f"Collections: {', '.join(collection_paths) if collection_paths else 'No'}")

    return {
        'item_id': item_id,
        'title': title,
        'fields': fields,
        'collections': collections,
        'collection_paths': collection_paths
    }



# ============================================================
# JSON dump — export full library for similarity ranking
# ============================================================

def dump_json(conn, output_path=None, include_abstract=True):
    """Export full Zotero library as JSON for similarity research."""
    cursor = conn.cursor()
    # Get all non-attachment, non-note items
    cursor.execute("""
        SELECT i.itemID, i.key, i.dateAdded, it.typeName
        FROM items i
        JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
        WHERE it.typeName NOT IN ('attachment', 'note')
        ORDER BY i.dateAdded DESC
    """)
    rows = cursor.fetchall()
    items = []
    for item_id, key, date_added, type_name in rows:
        # Pull all fields for this item
        cursor.execute("""
            SELECT f.fieldName, idv.value
            FROM itemData id
            JOIN itemDataValues idv ON id.valueID = idv.valueID
            JOIN fields f ON id.fieldID = f.fieldID
            WHERE id.itemID = ?
        """, (item_id,))
        fields = {fn: val for fn, val in cursor.fetchall()}
        # Creators
        cursor.execute("""
            SELECT cd.firstName, cd.lastName, ct.creatorType, ic.orderIndex
            FROM itemCreators ic
            JOIN creators cd ON ic.creatorID = cd.creatorID
            JOIN creatorTypes ct ON ic.creatorTypeID = ct.creatorTypeID
            WHERE ic.itemID = ?
            ORDER BY ic.orderIndex
        """, (item_id,))
        creators = []
        for fn, ln, ct, _idx in cursor.fetchall():
            name = ((fn or "") + " " + (ln or "")).strip()
            if name:
                creators.append({"name": name, "type": ct})
        # Collections (with full path)
        cursor.execute("""
            SELECT c.collectionID, c.collectionName
            FROM collectionItems ci
            JOIN collections c ON ci.collectionID = c.collectionID
            WHERE ci.itemID = ?
        """, (item_id,))
        coll_rows = cursor.fetchall()
        collections = [get_collection_path(conn, cid) for cid, _ in coll_rows]
        # Tags
        cursor.execute("""
            SELECT t.name
            FROM itemTags it_
            JOIN tags t ON it_.tagID = t.tagID
            WHERE it_.itemID = ?
        """, (item_id,))
        tags = [r[0] for r in cursor.fetchall()]

        entry = {
            "item_id": item_id,
            "key": key,
            "type": type_name,
            "title": fields.get("title", ""),
            "date": fields.get("date", ""),
            "authors": [c["name"] for c in creators if c["type"] == "author"],
            "creators": creators,
            "url": fields.get("url", ""),
            "doi": fields.get("DOI", ""),
            "publication": fields.get("publicationTitle") or fields.get("repository") or fields.get("bookTitle", ""),
            "collections": collections,
            "tags": tags,
            "dateAdded": date_added,
        }
        if include_abstract:
            entry["abstract"] = fields.get("abstractNote", "")
        items.append(entry)

    payload = {
        "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "item_count": len(items),
        "items": items,
    }
    out = json.dumps(payload, ensure_ascii=False, indent=2)
    if output_path:
        Path(output_path).write_text(out)
        print(f"Wrote {len(items)} items to {output_path}")
    else:
        print(out)
    return payload


# ============================================================
# Add new paper via BibTeX file (safe — no direct DB write)
# ============================================================

def _parse_obsidian_frontmatter(text):
    """Lightweight YAML-frontmatter parser for PaperNote .md files."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    fm_text = text[4:end]
    body = text[end + 4:].lstrip("\n")
    fm = {}
    key = None
    arr_buf = []
    def flush():
        nonlocal key, arr_buf
        if key and arr_buf:
            fm[key] = arr_buf
            arr_buf = []
    for line in fm_text.split("\n"):
        line = line.rstrip("\r")
        if not line.strip():
            continue
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if m:
            flush()
            key = m.group(1)
            val = m.group(2).strip()
            if val == "":
                fm[key] = ""
                key = key
                continue
            if val.startswith("[") and val.endswith("]"):
                inner = val[1:-1].strip()
                fm[key] = [s.strip().strip("\"'") for s in inner.split(",")] if inner else []
                key = None
            else:
                fm[key] = val.strip("\"'")
                key = None
        elif re.match(r"^\s*-\s+", line) and key:
            arr_buf.append(re.sub(r"^\s*-\s+", "", line).strip("\"'"))
    flush()
    return fm, body


def _extract_arxiv_id(url_or_text):
    """Pull an arXiv ID out of a URL or string. Returns e.g. '2605.12335' or None."""
    if not url_or_text:
        return None
    m = re.search(r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})(?:v\d+)?", url_or_text)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{4}\.\d{4,5})\b", url_or_text)
    if m:
        return m.group(1)
    return None


def _bibtex_escape(s):
    """Escape characters that break BibTeX strings."""
    if s is None:
        return ""
    return str(s).replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("&", "\\&").replace("%", "\\%").replace("$", "\\$").replace("#", "\\#").replace("_", "\\_")


def _make_bibtex_key(authors, year, title):
    """Generate a BibTeX-friendly citation key like 'doe2024Title'."""
    first_author_last = ""
    if authors:
        # Take last word of first author
        parts = authors[0].strip().split()
        if parts:
            first_author_last = re.sub(r"[^A-Za-z]", "", parts[-1]).lower()
    if not first_author_last:
        first_author_last = "anon"
    year_str = ""
    if year:
        m = re.search(r"(\d{4})", str(year))
        if m:
            year_str = m.group(1)
    if not year_str:
        year_str = "nd"
    first_title_word = ""
    if title:
        words = re.findall(r"[A-Za-z]+", title)
        # skip common stopwords
        STOP = {"a", "an", "the", "of", "for", "to", "in", "on", "and", "or", "with", "without", "from", "by", "via", "is", "are"}
        for w in words:
            if w.lower() not in STOP:
                first_title_word = w.capitalize()
                break
    return f"{first_author_last}{year_str}{first_title_word}"


def add_from_notepath(note_path, output_dir=None, dry_run=False, attach_pdf=False):
    """Parse a PaperNote .md file and generate a BibTeX entry for Zotero import.

    The output .bib file goes to <vault>/zotero-inbox/ by default. The user can:
      - drag-drop into Zotero, or
      - configure Better BibTeX 'Auto Import' to watch this folder
    """
    note_path = Path(note_path).expanduser()
    if not note_path.exists():
        print(f"❌ Note not found: {note_path}")
        return None
    text = note_path.read_text(encoding="utf-8")
    fm, body = _parse_obsidian_frontmatter(text)

    title = fm.get("title", "").strip().strip("\"")
    if not title:
        title = note_path.stem.replace("-", " ")
    authors = fm.get("authors", [])
    if isinstance(authors, str):
        authors = [a.strip() for a in authors.split(",") if a.strip()]
    year = fm.get("year", "")
    venue = fm.get("venue", "")
    tags_raw = fm.get("tags", [])
    if isinstance(tags_raw, str):
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    else:
        tags = list(tags_raw)
    created = fm.get("created", "")
    method_name = fm.get("method_name", "")

    # Try to find arXiv ID from the body (URL in metadata table)
    arxiv_id = None
    url = ""
    doi = ""
    # search common patterns in body
    m_url = re.search(r"https?://arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})(?:v\d+)?", body)
    if m_url:
        arxiv_id = m_url.group(1)
        url = f"https://arxiv.org/abs/{arxiv_id}"
    m_doi = re.search(r"\bdoi\.org/([\w./\-()]+)", body, re.IGNORECASE)
    if m_doi:
        doi = m_doi.group(1)

    # Build TLDR / abstract from "One-Sentence Summary" section
    abstract = ""
    m_abs = re.search(r"##\s*One-Sentence Summary\s*\n+([^\n#]+)", body)
    if m_abs:
        abstract = m_abs.group(1).strip()
        # Strip Obsidian wiki-link syntax: [[Target|Label]] -> Label, [[Target]] -> Target
        abstract = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", abstract)
        abstract = re.sub(r"\[\[([^\]]+)\]\]", r"\1", abstract)
        # Strip markdown bold/italic markers (but keep the inner text)
        abstract = re.sub(r"\*\*([^*]+)\*\*", r"\1", abstract)
        abstract = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", abstract)
        # Strip inline code backticks
        abstract = re.sub(r"`([^`]+)`", r"\1", abstract)
        abstract = abstract.strip()

    bib_key = _make_bibtex_key(authors, year, title)
    fields = []
    fields.append(("title", f"{{{title}}}"))
    if authors:
        # BibTeX expects "Last, First and Last, First" — but if we don't have first/last split, just use names joined
        fields.append(("author", " and ".join(authors)))
    if year:
        m = re.search(r"(\d{4})", str(year))
        if m: fields.append(("year", m.group(1)))
    if venue:
        fields.append(("journal", venue) if "journal" not in venue.lower() else ("booktitle", venue))
    if url:
        fields.append(("url", url))
    if doi:
        fields.append(("doi", doi))
    if abstract:
        fields.append(("abstract", _bibtex_escape(abstract)))
    if tags:
        fields.append(("keywords", ", ".join(tags)))
    if arxiv_id:
        fields.append(("eprint", arxiv_id))
        fields.append(("archivePrefix", "arXiv"))
    if method_name:
        fields.append(("note", f"method: {method_name}"))
    # Determine entry type — preprint if arxiv, article if venue suggests journal
    entry_type = "misc"
    if arxiv_id:
        entry_type = "article"  # @article works well for arxiv in Zotero
    elif venue:
        entry_type = "article"

    # Format
    bib = f"@{entry_type}{{{bib_key},\n"
    for k, v in fields:
        bib += f"  {k} = {{{v}}},\n"
    bib += "}\n"

    if dry_run:
        print(bib)
        return bib

    # Where to write
    if output_dir is None:
        # default to user's home Zotero/inbox
        output_dir = Path.home() / "Zotero" / "inbox"
    output_dir = Path(output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", title[:60]).strip("-")
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_file = output_dir / f"{ts}-{safe_name}.bib"
    out_file.write_text(bib, encoding="utf-8")
    print(f"✓ Wrote BibTeX to: {out_file}")
    print(f"  Title: {title}")
    print(f"  Authors: {', '.join(authors) if authors else '(none)'}")
    print(f"  arXiv: {arxiv_id or '(none)'}")
    print(f"  Tags: {', '.join(tags) if tags else '(none)'}")
    print()
    print("Import options:")
    print(f"  - Drag the .bib file into Zotero")
    print(f"  - Or in Zotero: File → Import → choose this file")
    print(f"  - Or set up Better BibTeX auto-import on this folder")
    return bib


def main():
    parser = argparse.ArgumentParser(description='Zotero database query tool')
    subparsers = parser.add_subparsers(dest='command', help='subcommand')

    # List collections
    subparsers.add_parser('collections', help='List all collections')

    # List papers under a collection
    papers_parser = subparsers.add_parser('papers', help='List papers under a collection')
    papers_parser.add_argument('collection_id', type=int, help='collection ID')
    papers_parser.add_argument('--recursive', '-r', action='store_true', help='include child collections recursively')

    # Search papers
    search_parser = subparsers.add_parser('search', help='Search papers')
    search_parser.add_argument('keyword', help='search keyword')

    # Get PDF path
    pdf_parser = subparsers.add_parser('pdf', help='Get PDF path')
    pdf_parser.add_argument('item_id', type=int, help='paper ItemID')

    # Get paper info
    info_parser = subparsers.add_parser('info', help='Get detailed paper information')
    info_parser.add_argument('item_id', type=int, help='paper ItemID')

    # Find collection
    find_parser = subparsers.add_parser('find-collection', help='Find collections by name')
    find_parser.add_argument('name', help='collection name, fuzzy matching supported')

    # Add to collection
    add_parser = subparsers.add_parser('add-to-collection', help='Add paper to collection')
    add_parser.add_argument('item_id', type=int, help='paper ItemID')
    add_parser.add_argument('collection_id', type=int, help='target collection ID')

    # Remove from collection
    remove_parser = subparsers.add_parser('remove-from-collection', help='Remove paper from collection')
    remove_parser.add_argument('item_id', type=int, help='paper ItemID')
    remove_parser.add_argument('collection_id', type=int, help='collection ID')

    # Move to new collection
    move_parser = subparsers.add_parser('move', help='Move paper to new collection')
    move_parser.add_argument('item_id', type=int, help='paper ItemID')
    move_parser.add_argument('new_collection_id', type=int, help='new collection ID')
    move_parser.add_argument('--from', dest='old_collection_id', type=int, help='old collection ID, optional')

    # NEW: dump entire library as JSON (for similarity research by Claude)
    dump_parser = subparsers.add_parser('dump-json', help='Export full library as JSON for similarity ranking')
    dump_parser.add_argument('--output', '-o', help='write to file instead of stdout')
    dump_parser.add_argument('--no-abstract', action='store_true', help='exclude abstracts (smaller output)')

    # NEW: add paper to Zotero via BibTeX file (safe, manual import)
    add_parser_bib = subparsers.add_parser('add-bib', help='Create BibTeX file for a paper note (for Zotero import)')
    add_parser_bib.add_argument('note_path', help='path to PaperNote .md file in Obsidian vault')
    add_parser_bib.add_argument('--output-dir', help='where to write the .bib file (default ~/Zotero/inbox)')
    add_parser_bib.add_argument('--dry-run', action='store_true', help='print BibTeX to stdout instead of writing')

    args = parser.parse_args()

    if not ZOTERO_DB.exists():
        print(f"Zotero database does not exist: {ZOTERO_DB}")
        return

    conn = copy_db()

    try:
        if args.command == 'collections':
            list_collections(conn)
        elif args.command == 'papers':
            list_papers_in_collection(conn, args.collection_id, recursive=args.recursive)
        elif args.command == 'search':
            search_paper(conn, args.keyword)
        elif args.command == 'pdf':
            get_pdf_path(conn, args.item_id)
        elif args.command == 'info':
            get_paper_info(conn, args.item_id)
        elif args.command == 'find-collection':
            find_collection_by_name(conn, args.name)
        elif args.command == 'add-to-collection':
            add_to_collection_db(args.item_id, args.collection_id)
        elif args.command == 'remove-from-collection':
            remove_from_collection_db(args.item_id, args.collection_id)
        elif args.command == 'move':
            move_to_collection(args.item_id, args.new_collection_id, args.old_collection_id)
        elif args.command == 'dump-json':
            dump_json(conn, output_path=args.output, include_abstract=not args.no_abstract)
        elif args.command == 'add-bib':
            add_from_notepath(args.note_path, output_dir=args.output_dir, dry_run=args.dry_run)
        else:
            parser.print_help()
    finally:
        conn.close()


if __name__ == '__main__':
    main()
