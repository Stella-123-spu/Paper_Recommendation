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
from pathlib import Path

_SHARED_DIR = Path(__file__).resolve().parents[2] / "_shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from user_config import zotero_db_path, zotero_storage_dir

# Default config
ZOTERO_DB = zotero_db_path()
STORAGE_DIR = zotero_storage_dir()
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
        else:
            parser.print_help()
    finally:
        conn.close()


if __name__ == '__main__':
    main()
