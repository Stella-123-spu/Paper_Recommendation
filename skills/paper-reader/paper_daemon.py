#!/usr/bin/env python3
"""
Paper Reading Daemon - background paper-reading daemon

Features:
1. Gets the paper list for a specified Zotero collection, recursively including child collections
2. Calls Claude Code (`claude -p`) to process papers one by one
3. Automatically waits and retries on rate limits
4. Supports resume from checkpoints

Usage:
    # Start the daemon for a Zotero collection
    screen -S paper-daemon
    python3 paper_daemon.py -c "target collection name"

    # View progress
    python3 paper_daemon.py --status
"""

import os
import sys
import json
import sqlite3
import shlex
import subprocess
import time
import argparse
import logging
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

_SHARED_DIR = Path(__file__).resolve().parents[1] / "_shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from user_config import concepts_dir, obsidian_vault_path, paper_notes_dir, zotero_db_path, zotero_storage_dir

# Config
ZOTERO_DB = str(zotero_db_path())
ZOTERO_STORAGE = str(zotero_storage_dir())
OBSIDIAN_VAULT = str(obsidian_vault_path())
PAPER_NOTES_ROOT = str(paper_notes_dir())
CONCEPTS_ROOT = str(concepts_dir())
_DAEMON_STATE_DIR = os.path.expanduser(os.environ.get("PAPER_DAEMON_STATE_DIR", "~/.claude"))
_CLAUDE_BIN = os.environ.get("PAPER_DAEMON_CLAUDE_BIN", "claude")
_CLAUDE_WORKDIR = os.environ.get("PAPER_DAEMON_CLAUDE_WORKDIR", OBSIDIAN_VAULT)
_CLAUDE_MODEL = os.environ.get("PAPER_DAEMON_CLAUDE_MODEL", "").strip()
_CLAUDE_EXTRA_ARGS = os.environ.get("PAPER_DAEMON_CLAUDE_ARGS", "")
PROGRESS_FILE = os.path.join(_DAEMON_STATE_DIR, "paper_daemon_progress.json")
LOG_FILE = os.path.join(_DAEMON_STATE_DIR, "paper_daemon.log")
PID_FILE = os.path.join(_DAEMON_STATE_DIR, "paper_daemon.pid")

# Rate limit config
INITIAL_WAIT = 60          # initial wait time (seconds)
MAX_WAIT = 21600           # maximum wait time (6 hours)
WAIT_MULTIPLIER = 2        # wait multiplier
BETWEEN_PAPERS_WAIT = 5    # wait time between papers (seconds)
QUOTA_WAIT_TIME = 1800     # default wait time after quota limit (30 minutes)

# Set up logging
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

_SUBSCRIPT_TRANSLATION = str.maketrans("₀₁₂₃₄₅₆₇₈₉₊₋", "0123456789+-")
_GREEK_REPLACEMENTS = {
    "π": "pi",
    "ϕ": "phi",
    "φ": "phi",
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
}


def acquire_lock() -> bool:
    """Acquire process lock to prevent duplicate runs"""
    if os.path.exists(PID_FILE):
        with open(PID_FILE, 'r') as f:
            old_pid = f.read().strip()
        # Check whether the process is still running
        try:
            os.kill(int(old_pid), 0)
            return False  # process is still running
        except (OSError, ValueError):
            pass  # process has ended; continuing

    # Write current PID
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
    return True


def release_lock():
    """Release process lock"""
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)


def wait_for_quota_reset(wait_seconds: Optional[int] = None):
    """Wait until quota resets or manual recovery before continuing."""
    if wait_seconds is None:
        wait_seconds = QUOTA_WAIT_TIME
    wait_minutes = max(1, wait_seconds // 60)
    logger.info(f"⏳ Quota limited; waiting {wait_minutes} minutes...")
    time.sleep(wait_seconds)


def detect_limit_error(output: str) -> Optional[str]:
    """Detect quota or rate-limit error type"""
    text = output.lower()
    if 'rate limit' in text or 'too many requests' in text:
        return 'RATE_LIMIT'
    if 'hit your limit' in text or 'usage limit' in text or 'resets' in text:
        return 'QUOTA_LIMIT'
    return None


def parse_reset_wait_seconds(message: str) -> Optional[int]:
    """
    Parse messages such as "resets 9pm (Asia/Shanghai)" and compute wait seconds
    """
    match = re.search(
        r'resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?(?:\s*\(([^)]+)\))?',
        message,
        re.IGNORECASE
    )
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    ampm = (match.group(3) or '').lower()
    tz_name = match.group(4) or 'Asia/Shanghai'

    if ampm == 'pm' and hour < 12:
        hour += 12
    if ampm == 'am' and hour == 12:
        hour = 0

    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        return None

    now = datetime.now(tz)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)

    wait_seconds = int((target - now).total_seconds())
    return max(60, wait_seconds)


def copy_zotero_db() -> str:
    """Copy Zotero database to avoid locking"""
    tmp_db = "/tmp/zotero_readonly.sqlite"
    subprocess.run(["cp", ZOTERO_DB, tmp_db], check=True)
    return tmp_db


def get_collection_id_and_path(db_path: str, collection_name: str) -> tuple[Optional[int], Optional[str]]:
    """Get ID and full path from collection name"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT collectionID, collectionName, parentCollectionID FROM collections")
    collections = {row[0]: {'name': row[1], 'parent': row[2]} for row in cursor.fetchall()}

    def get_path(cid):
        path_parts = []
        current = cid
        while current:
            if current in collections:
                path_parts.insert(0, collections[current]['name'])
                current = collections[current]['parent']
            else:
                break
        return '/'.join(path_parts)

    for cid, info in collections.items():
        if info['name'].lower() == collection_name.lower():
            conn.close()
            return cid, get_path(cid)
        if collection_name.lower() in info['name'].lower():
            conn.close()
            return cid, get_path(cid)

    conn.close()
    return None, None


def get_all_child_collections(db_path: str, collection_id: int) -> list[int]:
    """Recursively get all child collection IDs, including itself"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT collectionID, parentCollectionID FROM collections")
    all_collections = cursor.fetchall()
    conn.close()

    children_map = {}
    for cid, parent_id in all_collections:
        if parent_id not in children_map:
            children_map[parent_id] = []
        children_map[parent_id].append(cid)

    result = [collection_id]
    def collect_children(cid):
        if cid in children_map:
            for child_id in children_map[cid]:
                result.append(child_id)
                collect_children(child_id)

    collect_children(collection_id)
    return result


def get_papers_in_collection(db_path: str, collection_id: int) -> list[dict]:
    """Get all papers under a collection, including child collections recursively"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    collection_ids = get_all_child_collections(db_path, collection_id)
    placeholders = ','.join('?' * len(collection_ids))
    query = f"""
        SELECT DISTINCT i.itemID, idv.value as title
        FROM items i
        JOIN collectionItems ci ON i.itemID = ci.itemID
        JOIN itemData id ON i.itemID = id.itemID
        JOIN itemDataValues idv ON id.valueID = idv.valueID
        JOIN fields f ON id.fieldID = f.fieldID
        WHERE ci.collectionID IN ({placeholders}) AND f.fieldName = 'title' AND i.itemTypeID != 14
    """
    cursor.execute(query, collection_ids)
    logger.info(f"Recursive query including {len(collection_ids)} collections")

    papers = [{'item_id': row[0], 'title': row[1]} for row in cursor.fetchall()]
    conn.close()
    return papers


def get_pdf_path(db_path: str, item_id: int) -> Optional[str]:
    """Get paper PDF path"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT ia.path, items.key
        FROM itemAttachments ia
        JOIN items ON ia.itemID = items.itemID
        WHERE ia.parentItemID = ? AND ia.contentType = 'application/pdf'
    """, (item_id,))

    row = cursor.fetchone()
    conn.close()

    if row:
        path, key = row
        if path and path.startswith('storage:'):
            filename = path.replace('storage:', '')
            return os.path.join(ZOTERO_STORAGE, key, filename)
    return None


def get_paper_online_source(db_path: str, item_id: int) -> Optional[dict]:
    """
    Get online source information for a paper, including arXiv ID, DOI, and URL
    Used for processing papers without PDFs
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get paper fields
    cursor.execute("""
        SELECT f.fieldName, idv.value
        FROM itemData id
        JOIN fields f ON id.fieldID = f.fieldID
        JOIN itemDataValues idv ON id.valueID = idv.valueID
        WHERE id.itemID = ?
    """, (item_id,))

    fields = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()

    result = {}

    # Check arXiv ID, possibly in extra field or archiveID
    extra = fields.get('extra', '')
    if 'arXiv:' in extra:
        # Format: arXiv:2401.12345
        match = re.search(r'arXiv[:\s]+(\d{4}\.\d{4,5})', extra, re.IGNORECASE)
        if match:
            result['arxiv_id'] = match.group(1)

    # Check DOI
    doi = fields.get('DOI', '')
    if doi:
        result['doi'] = doi

    # Check URL
    url = fields.get('url', '')
    if url:
        result['url'] = url
        # Try extracting arXiv ID from URL
        if 'arxiv.org' in url and 'arxiv_id' not in result:
            match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})', url)
            if match:
                result['arxiv_id'] = match.group(1)

    return result if result else None


def get_existing_notes() -> dict[str, str]:
    """Get existing Obsidian notes, returning {method_name: file_path}"""
    existing = {}
    notes_dir = Path(PAPER_NOTES_ROOT)
    concepts_root = Path(CONCEPTS_ROOT)
    if notes_dir.exists():
        for md_file in notes_dir.rglob("*.md"):
            if md_file.name == "_index.md":
                continue
            name = md_file.stem
            try:
                md_file.relative_to(concepts_root)
                continue
            except ValueError:
                pass

            # Skip index pages, such as PaperNotes/PaperNotes.md or _inbox/_inbox.md
            if md_file.parent == notes_dir and name == notes_dir.name:
                continue
            if md_file.parent.name == name:
                continue

            candidates = set(_extract_note_method_names(name))
            try:
                content = md_file.read_text(encoding="utf-8")
            except OSError:
                content = ""

            match = re.search(r'^method_name:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
            if match:
                candidates.update(_extract_note_method_names(match.group(1).strip()))

            for method_name in candidates:
                existing[method_name] = str(md_file)
    return existing


def title_matches_note(title: str, existing_notes: dict[str, str]) -> bool:
    """
    Check whether a paper title matches an existing note
    Return True only for exact method-name matches
    """
    if not title:
        return False

    normalized_candidates = {
        _normalize_method_name(title.strip()),
        _normalize_method_name(title.split(':', 1)[0].strip()),
    }

    for method_normalized in normalized_candidates:
        if not method_normalized:
            continue
        for note_method in existing_notes.keys():
            # Exact equality
            if note_method == method_normalized:
                return True
            # Note method name is fully contained in title method name, with similar length
            if note_method in method_normalized and len(note_method) > 3:
                # Avoid overly short matches, such as "gs" matching "3dgs"
                if len(note_method) >= len(method_normalized) * 0.5:
                    return True

    return False


def _normalize_method_name(value: str) -> str:
    normalized = value.strip().lower().translate(_SUBSCRIPT_TRANSLATION)
    for source, target in _GREEK_REPLACEMENTS.items():
        normalized = normalized.replace(source, target)
    normalized = normalized.replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "", normalized)


def _extract_note_method_names(stem: str) -> set[str]:
    candidates = {stem}

    match = re.match(r"^(?:19|20)\d{2}_(.+)$", stem)
    if match:
        candidates.add(match.group(1))

    return {
        normalized
        for candidate in candidates
        if (normalized := _normalize_method_name(candidate))
    }


def load_progress() -> dict:
    """Load progress"""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {'completed': [], 'failed': [], 'current': None, 'started_at': None}


def save_progress(progress: dict):
    """Save progress"""
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)


def call_claude(paper_source: dict, collection_path: str, item_id: int) -> tuple[bool, str]:
    """
    Call Claude Code (`claude -p`) to process a paper

    paper_source can include:
    - pdf_path: local PDF path
    - arxiv_id: arXiv ID (for example 2401.12345)
    - doi: DOI
    - url: paper URL
    - title: paper title, used for search
    """

    arxiv_id = paper_source.get('arxiv_id', '')
    notes_root = PAPER_NOTES_ROOT
    concepts_root = CONCEPTS_ROOT

    # Build source information
    source_lines = []
    if paper_source.get('pdf_path'):
        source_lines.append(f"PDF Path: {paper_source['pdf_path']}")
    if arxiv_id:
        source_lines.append(f"arXiv ID: {arxiv_id}")
        source_lines.append(f"arXiv page: https://arxiv.org/abs/{arxiv_id}")
        source_lines.append(f"arXiv PDF: https://arxiv.org/pdf/{arxiv_id}.pdf")
        source_lines.append(f"arXiv HTML (images): https://arxiv.org/html/{arxiv_id}")
    if paper_source.get('doi'):
        source_lines.append(f"DOI: {paper_source['doi']}")
        source_lines.append(f"DOI link: https://doi.org/{paper_source['doi']}")
    if paper_source.get('url'):
        source_lines.append(f"URL: {paper_source['url']}")
    if paper_source.get('title'):
        source_lines.append(f"Paper title: {paper_source['title']}")

    source_info = '\n'.join(source_lines)

    # If no PDF exists, add special instructions
    no_pdf_instruction = ""
    if not paper_source.get('pdf_path'):
        fallback_steps = []
        if arxiv_id:
            fallback_steps.extend(
                [
                    f"1. **arXiv HTML version**(recommended): read with WebFetch https://arxiv.org/html/{arxiv_id}, can directly retrieve image URLs",
                    f"2. **arXiv abstract page**: read with WebFetch https://arxiv.org/abs/{arxiv_id}",
                    f"3. **arXiv PDF**: download https://arxiv.org/pdf/{arxiv_id}.pdf locally and read it with Read",
                ]
            )
        if paper_source.get('doi'):
            fallback_steps.append(f"{len(fallback_steps) + 1}. **DOI page**: open https://doi.org/{paper_source['doi']} read")
        if paper_source.get('url'):
            fallback_steps.append(f"{len(fallback_steps) + 1}. **Original URL**: read {paper_source['url']}")
        if not fallback_steps:
            fallback_steps.append("1. Search online sources by title, then prefer an HTML version that exposes image URLs directly")

        no_pdf_instruction = f"""
## No Local PDF - Online Retrieval Required

This paper has no local PDF. Retrieve content in this priority order:

{chr(10).join(fallback_steps)}

Prefer the HTML version because it can expose online image links directly.
"""

    prompt = f"""Use the `paper-reader` skill to read and analyze this paper, then generate a complete structured note.

{source_info}
Zotero collection path: {collection_path}
Zotero ItemID: {item_id}
{no_pdf_instruction}

## Quality Requirements

Follow the high-quality note style and include:

1. **Metadata table**: institutions, date, project page, and compared baselines
2. **Inline concept links**: use in the body `[[Flow Matching]]`, `[[DiT]]` as concept links in the body, not only at the end
3. **Formula format**: each formula includes Meaning and Symbol Explanation subsections
4. **Image format**: `### Figure X: English title` + online URL + `**Explanation**:`
5. **Critical analysis**: strengths, limitations, potential improvements, and reproducibility checklist
6. **Related note categories**: split into "Builds on", "Compared with", "Method-related", "Hardware/data-related"
7. **Quick reference card**: ASCII box-style quick reference

## Processing Rules

1. **Prefer online image links**: check the arXiv HTML version first and use online image URLs if available

## Concept Library Update (Required)

**After every paper, create notes for newly encountered technical concepts.**

### Concept library location
{concepts_root}

### When to create concept notes
1. Technical terms first encountered in the paper, such as Flow Matching, Action Chunking, and DiT
2. new method names proposed by the paper, if they are general concepts
3. A [[Concept]] link is used in the note but no concept note exists

### Concept note format
```markdown
---
type: concept
aliases: [alias1, alias2]
---

# Concept Name

## Definition
One-sentence definition

## Mathematical Form, If Any
$$formula$$

## Key Points
1. point1
2. point2

## Representative Works
- [[Paper 1]]: Explanation
- [[Paper 2]]: Explanation

## Related Concepts
- [[Related Concepts1]]
```

### Concept Directory Structure (Existing Categories)
- 1-generative-models/: Diffusion Model, DiT, VAE, Flow Matching, EDM, Latent Diffusion
- 2-reinforcement-learning/: MDP, Policy, Value Function, PPO, GAIL, World Model
- 3-robot-policy/: Action Chunking, Inverse Dynamics Model, Sim-to-Real
- 4-legged-locomotion/: CPG, Curriculum Learning, Privileged Learning
- 5-navigation-and-localization/: VLN
- For a new field, create a new subdirectory, such as 6-3d-vision/

### Execution Steps
1. After analyzing the paper, list every [[Concept]] link in the note
2. Check whether each concept already exists by inspecting `{concepts_root}` for existing concept notes
3. Create concept-note files for missing concepts
4. Use the Write tool to write concept notes

## Automatic Categorization and Zotero Sync

**Do not rely on keyword matching alone.** You must understand the paper and judge the category yourself.

### Categorization Principles
1. Understand the paper's core contribution
2. Ask: where would I look for this paper later?
3. Categorize by primary contribution, not by the technology used
   - Example: diffusion for robot control -> VLA, not Diffusion Model
   - Example: 3DGS for SLAM -> SLAM, not 3DGS

### Categorization Operations
Use the zotero_helper.py script:
- collections: List all collections
- find-collection "name": find collection ID
- move <item_id> <collection_id>: move paper

### When Moving Is Required
- Currently in temporary collections such as "2025", "misc", or "feifeili" -> must move
- Collection clearly mismatches paper content -> move

## Save Location

Based on your understanding of the paper, save it under the appropriate Obsidian directory:
- Base structure:{notes_root}/matching category path/
- If uncertain:{notes_root}/_inbox/

Start directly without confirmation. Extract every formula, figure, and table."""

    try:
        cmd = [
            _CLAUDE_BIN,
            '-p',
            '--dangerously-skip-permissions',
        ]
        if _CLAUDE_MODEL:
            cmd.extend(['--model', _CLAUDE_MODEL])
        if _CLAUDE_EXTRA_ARGS:
            cmd.extend(shlex.split(_CLAUDE_EXTRA_ARGS))
        cmd.append(prompt)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=_CLAUDE_WORKDIR,
            timeout=900  # 15-minute timeout because image extraction can take time
        )

        output = result.stdout + result.stderr

        limit_type = detect_limit_error(output)
        if limit_type == 'RATE_LIMIT':
            return False, 'RATE_LIMIT'
        if limit_type == 'QUOTA_LIMIT':
            return False, f'QUOTA_LIMIT|{output[:200]}'

        if result.returncode == 0:
            return True, ''
        else:
            return False, output[:500]

    except subprocess.TimeoutExpired:
        return False, 'TIMEOUT'
    except Exception as e:
        return False, str(e)


def process_collection(collection_name: str, resume: bool = True):
    """Process all papers in a collection"""
    logger.info(f"=== Start processing collection: {collection_name} ===")

    db_path = copy_zotero_db()

    collection_id, collection_path = get_collection_id_and_path(db_path, collection_name)
    if not collection_id:
        logger.error(f"Collection not found: {collection_name}")
        return

    logger.info(f"Collection path: {collection_path} (ID: {collection_id})")

    papers = get_papers_in_collection(db_path, collection_id)
    logger.info(f"Collection contains {len(papers)} papers")

    progress = load_progress() if resume else {'completed': [], 'failed': [], 'current': None, 'started_at': None}
    if not progress['started_at']:
        progress['started_at'] = datetime.now().isoformat()

    # Get existing notes
    existing_notes = get_existing_notes()
    logger.info(f"Existing Obsidian notes: {len(existing_notes)} notes")

    # Filter papers to process
    pending = []
    skipped_existing = 0
    for paper in papers:
        item_id = paper['item_id']
        title = paper['title']

        if item_id in progress['completed']:
            continue

        # Check for existing notes
        if title_matches_note(title, existing_notes):
            logger.info(f"Skip (existing note): {title[:50]}")
            skipped_existing += 1
            progress['completed'].append(item_id)  # mark as completed
            continue

        pdf_path = get_pdf_path(db_path, item_id)
        paper_source = {'title': title}

        if pdf_path and os.path.exists(pdf_path):
            paper_source['pdf_path'] = pdf_path
        else:
            # Try to get online source
            online_source = get_paper_online_source(db_path, item_id)
            if online_source:
                paper_source.update(online_source)
                logger.info(f"No local PDF; using online source: {list(online_source.keys())}")
            else:
                logger.warning(f"Skip (no PDF and no online source): {title[:50]}")
                continue

        pending.append({**paper, 'source': paper_source})

    if skipped_existing > 0:
        logger.info(f"Skipped existing notes: {skipped_existing} papers")
        save_progress(progress)

    logger.info(f"Pending: {len(pending)} papers")

    wait_time = INITIAL_WAIT

    for i, paper in enumerate(pending):
        item_id = paper['item_id']
        title = paper['title']
        paper_source = paper['source']

        source_type = "PDF" if paper_source.get('pdf_path') else "online"
        logger.info(f"\n[{i+1}/{len(pending)}] processing ({source_type}): {title[:60]}...")
        progress['current'] = {'item_id': item_id, 'title': title}
        save_progress(progress)

        success, error = call_claude(paper_source, collection_path, item_id)

        if success:
            logger.info(f"✓ Done: {title[:50]}")
            progress['completed'].append(item_id)
            progress['current'] = None
            save_progress(progress)
            wait_time = INITIAL_WAIT

            if i < len(pending) - 1:
                time.sleep(BETWEEN_PAPERS_WAIT)

        elif error == 'RATE_LIMIT':
            logger.warning(f"⏳ Rate limit, waiting {wait_time} seconds...")
            time.sleep(wait_time)
            wait_time = min(wait_time * WAIT_MULTIPLIER, MAX_WAIT)
            pending.insert(i + 1, paper)  # requeue

        elif error.startswith('QUOTA_LIMIT'):
            reset_wait = parse_reset_wait_seconds(error)
            if reset_wait:
                logger.warning(f"⏳ Quota limit, waiting until reset, about {reset_wait // 60} minutes...")
                time.sleep(reset_wait)
            else:
                wait_for_quota_reset()
            pending.insert(i + 1, paper)  # requeue

        elif error == 'TIMEOUT':
            logger.error(f"✗ Timeout: {title[:50]}")
            progress['failed'].append({'item_id': item_id, 'title': title, 'error': 'TIMEOUT'})
            save_progress(progress)

        else:
            logger.error(f"✗ Failed: {title[:50]} - {error[:100]}")
            progress['failed'].append({'item_id': item_id, 'title': title, 'error': error[:200]})
            save_progress(progress)

    progress['current'] = None
    progress['finished_at'] = datetime.now().isoformat()
    save_progress(progress)

    logger.info("\n=== Processing complete ===")
    logger.info(f"Successful: {len(progress['completed'])} papers")
    logger.info(f"Failed: {len(progress['failed'])} papers")


def show_status():
    """Show current progress"""
    progress = load_progress()
    print("\n=== Paper Daemon Status ===")
    print(f"Started at: {progress.get('started_at', 'N/A')}")
    print(f"Finished at: {progress.get('finished_at', 'in progress...')}")
    print(f"Completed: {len(progress.get('completed', []))} papers")
    print(f"Failed: {len(progress.get('failed', []))} papers")

    current = progress.get('current')
    if current:
        print(f"Currently processing: {current.get('title', 'N/A')[:60]}")

    if progress.get('failed'):
        print("\nFailed papers:")
        for item in progress['failed'][:5]:
            print(f"  - {item['title'][:50]}: {item['error'][:50]}")


def main():
    parser = argparse.ArgumentParser(description='Paper Reading Daemon')
    parser.add_argument('--collection', '-c', type=str, help='Zotero Collection Name')
    parser.add_argument('--status', '-s', action='store_true', help='show current status')
    parser.add_argument('--no-resume', action='store_true', help='do not resume previous progress')
    parser.add_argument('--list', '-l', action='store_true', help='list all Zotero collections')

    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.list:
        db_path = copy_zotero_db()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.collectionName, COUNT(ci.itemID) as count
            FROM collections c
            LEFT JOIN collectionItems ci ON c.collectionID = ci.collectionID
            GROUP BY c.collectionID
            HAVING count > 0
            ORDER BY c.collectionName
        """)
        print("\n=== Zotero category ===")
        for name, count in cursor.fetchall():
            print(f"  {name}: {count} papers")
        conn.close()
        return

    if not args.collection:
        parser.print_help()
        return

    # Check whether another process is running
    if not acquire_lock():
        logger.error("Another paper_daemon process is running. Stop it first or delete ~/.claude/paper_daemon.pid")
        return

    try:
        process_collection(args.collection, resume=not args.no_resume)
    finally:
        release_lock()


if __name__ == '__main__':
    main()
