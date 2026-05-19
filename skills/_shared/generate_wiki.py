#!/usr/bin/env python3
"""
generate_wiki.py — generate / update wiki content for an Obsidian PaperNotes vault.

Two outputs:
  1. Tags/<tag>.md          — one page per unique frontmatter tag, listing papers
  2. _concepts/0-uncategorized/<Concept>.md  — stub for each [[wiki-link]] referenced
                                                N+ times that doesn't already have a
                                                concept note

Both are idempotent: re-running refreshes the "Referenced by / Papers with this tag"
sections in place without overwriting any prose you've written above them.

Usage:
    python3 generate_wiki.py
    python3 generate_wiki.py --min-refs 2          # require 2+ wiki-link refs for stubs
    python3 generate_wiki.py --tags-only           # skip concept stubs
    python3 generate_wiki.py --concepts-only       # skip tag pages
"""

import argparse
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# Allow running both inside the skills tree and standalone
_SHARED_DIR = Path(__file__).resolve().parent
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

try:
    from user_config import obsidian_vault_path, paper_notes_dir
except ImportError:
    def obsidian_vault_path():
        return Path(os.environ.get("OBSIDIAN_VAULT", Path.home() / "Documents/Obsidian/Research")).expanduser()
    def paper_notes_dir():
        return obsidian_vault_path() / "PaperNotes"


# ====== Markers used for re-runnable sections ======
BACKREF_BEGIN = "<!-- BACKREF:BEGIN -->"
BACKREF_END = "<!-- BACKREF:END -->"
TAGREF_BEGIN = "<!-- TAGREF:BEGIN -->"
TAGREF_END = "<!-- TAGREF:END -->"


# ====== Frontmatter parsing ======

def parse_frontmatter(text):
    """Return (frontmatter_dict, body_without_frontmatter)."""
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
                continue
            if val.startswith("[") and val.endswith("]"):
                inner = val[1:-1].strip()
                fm[key] = [s.strip().strip("\"'") for s in inner.split(",") if s.strip()] if inner else []
                key = None
            else:
                fm[key] = val.strip("\"'")
                key = None
        elif re.match(r"^\s*-\s+", line) and key:
            arr_buf.append(re.sub(r"^\s*-\s+", "", line).strip("\"'"))
    flush()
    return fm, body


# ====== Scan vault ======

def scan_papernotes(notes_root):
    """Walk PaperNotes/, collect tags + wiki-link refs per note."""
    notes = []
    wiki_to_notes = defaultdict(list)  # concept_name -> [note_info, ...]
    tag_to_notes = defaultdict(list)   # tag -> [note_info, ...]
    for md in notes_root.rglob("*.md"):
        if "_concepts" in md.parts:
            continue
        text = md.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        title = fm.get("title", md.stem)
        method = fm.get("method_name", "")
        year = str(fm.get("year", ""))
        venue = fm.get("venue", "")
        tags = fm.get("tags", []) if isinstance(fm.get("tags", []), list) else []
        rel = md.relative_to(notes_root)
        category = rel.parts[0] if len(rel.parts) > 1 else "_inbox"
        note_info = {
            "path": md,
            "rel": str(rel),
            "filename": md.name,
            "stem": md.stem,
            "title": title,
            "method": method,
            "year": year,
            "venue": venue,
            "category": category,
            "tags": tags,
        }
        notes.append(note_info)
        for t in tags:
            tag_to_notes[t].append(note_info)
        # Capture wiki-link concept refs
        for m in re.finditer(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", body):
            concept = m.group(1).strip()
            # Skip refs that look like paper-note links (have spaces and capital letters & colons typical of paper titles)
            # — but actually we want concept refs. Heuristic: papers usually have ":" or are very long.
            # Keep all for now; the link target naming is loose in Obsidian.
            wiki_to_notes[concept].append(note_info)
    # Deduplicate (same note can reference the same concept many times)
    for c, ns in wiki_to_notes.items():
        seen = set()
        deduped = []
        for n in ns:
            if n["stem"] in seen:
                continue
            seen.add(n["stem"])
            deduped.append(n)
        wiki_to_notes[c] = deduped
    return notes, wiki_to_notes, tag_to_notes


# ====== Render helpers ======

def render_paper_bullet(n):
    """Markdown bullet linking to a PaperNote with metadata."""
    bits = []
    if n["method"]:
        bits.append(f"**{n['method']}**")
    if n["venue"]:
        bits.append(n["venue"])
    if n["year"]:
        bits.append(n["year"])
    suffix = " · ".join(bits)
    line = f"- [[{n['stem']}|{n['title']}]]"
    if suffix:
        line += f" — {suffix}"
    return line


def group_by_category(notes):
    groups = defaultdict(list)
    for n in notes:
        groups[n["category"]].append(n)
    return groups


def update_marked_section(text, begin_marker, end_marker, new_block):
    """Replace content between two HTML-comment markers in `text`. If the markers
    don't exist, append them along with `new_block` at the end."""
    pat = re.compile(re.escape(begin_marker) + r".*?" + re.escape(end_marker), re.S)
    block = f"{begin_marker}\n{new_block.rstrip()}\n{end_marker}"
    if pat.search(text):
        return pat.sub(block, text)
    if not text.endswith("\n"):
        text += "\n"
    return text + "\n" + block + "\n"


# ====== Concept stubs ======

CONCEPT_STUB_TEMPLATE = """---
type: concept
aliases: []
auto_generated: true
created: {today}
---

# {name}

## Definition

> _Stub — fill in a precise 1-2 sentence definition._

## Key Points

1.
2.
3.

## Mathematical Form

<!-- Optional. Add LaTeX if relevant. -->

## Representative Works

{representative}

## Related Concepts

<!-- Add [[wiki-links]] to other concepts here. -->

---

{backref_section}
"""

def render_backref_section(notes):
    lines = [f"## Referenced by ({len(notes)})", ""]
    for n in notes:
        lines.append(render_paper_bullet(n))
    return "\n".join(lines)


def generate_concept_stubs(vault, wiki_to_notes, min_refs=2, dry_run=False):
    concepts_dir = vault / "PaperNotes" / "_concepts" / "0-uncategorized"
    concepts_dir.mkdir(parents=True, exist_ok=True)

    # Index existing concept notes (across ALL subfolders of _concepts/)
    existing_concepts = {}
    for md in (vault / "PaperNotes" / "_concepts").rglob("*.md"):
        key = md.stem.lower()
        existing_concepts[key] = md
        # also index aliases
        try:
            fm, _ = parse_frontmatter(md.read_text(encoding="utf-8"))
            for a in fm.get("aliases", []) or []:
                if isinstance(a, str):
                    existing_concepts[a.lower()] = md

        except Exception:
            pass

    created = 0
    updated = 0
    skipped = 0
    for concept, refs in sorted(wiki_to_notes.items(), key=lambda x: -len(x[1])):
        if len(refs) < min_refs:
            continue
        # Skip if a concept note already exists (by name or alias)
        existing = existing_concepts.get(concept.lower())
        if existing:
            # Update backref section in place
            text = existing.read_text(encoding="utf-8")
            backref = render_backref_section(refs)
            new_text = update_marked_section(text, BACKREF_BEGIN, BACKREF_END, backref)
            if new_text != text:
                if not dry_run:
                    existing.write_text(new_text, encoding="utf-8")
                updated += 1
            else:
                skipped += 1
            continue

        # Create stub
        safe_name = re.sub(r'[\\/:*?"<>|]', "-", concept).strip()
        target = concepts_dir / f"{safe_name}.md"
        if target.exists():
            skipped += 1
            continue
        representative = "\n".join(render_paper_bullet(n) for n in refs[:5])
        if not representative:
            representative = "<!-- No representative work yet. -->"
        backref_section = f"{BACKREF_BEGIN}\n{render_backref_section(refs)}\n{BACKREF_END}"
        content = CONCEPT_STUB_TEMPLATE.format(
            name=concept,
            today=datetime.now().strftime("%Y-%m-%d"),
            representative=representative,
            backref_section=backref_section,
        )
        if not dry_run:
            target.write_text(content, encoding="utf-8")
        created += 1
        print(f"  + {target.relative_to(vault)}  ({len(refs)} refs)")

    return {"created": created, "updated": updated, "skipped": skipped}


# ====== Tag pages ======

TAG_PAGE_TEMPLATE = """---
type: tag-page
tag: {tag}
auto_generated: true
generated: {today}
---

# Tag: #{tag}

> _Auto-generated index of all PaperNotes tagged `#{tag}`. Re-run `generate_wiki.py` to refresh._

{tagref_section}
"""


def render_tag_papers_section(notes, tag):
    by_cat = group_by_category(notes)
    lines = [f"## {len(notes)} papers", ""]
    for cat in sorted(by_cat.keys()):
        lines.append(f"### {cat}")
        for n in sorted(by_cat[cat], key=lambda x: x["year"] or "0", reverse=True):
            lines.append(render_paper_bullet(n))
        lines.append("")
    return "\n".join(lines)


def generate_tag_pages(vault, tag_to_notes, dry_run=False):
    tags_dir = vault / "Tags"
    tags_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")

    written = 0
    for tag, notes in sorted(tag_to_notes.items()):
        safe = re.sub(r'[\\/:*?"<>|]', "-", tag)
        target = tags_dir / f"{safe}.md"
        tagref = f"{TAGREF_BEGIN}\n{render_tag_papers_section(notes, tag)}\n{TAGREF_END}"
        if target.exists():
            text = target.read_text(encoding="utf-8")
            new_text = update_marked_section(text, TAGREF_BEGIN, TAGREF_END, render_tag_papers_section(notes, tag))
            if new_text != text:
                if not dry_run:
                    target.write_text(new_text, encoding="utf-8")
                written += 1
        else:
            content = TAG_PAGE_TEMPLATE.format(tag=tag, today=today, tagref_section=tagref)
            if not dry_run:
                target.write_text(content, encoding="utf-8")
            written += 1

    # Tag Index page
    index_path = tags_dir / "Tag Index.md"
    sorted_tags = sorted(tag_to_notes.items(), key=lambda x: (-len(x[1]), x[0]))
    lines = [
        "---",
        "type: tag-index",
        "auto_generated: true",
        f"generated: {today}",
        "---",
        "",
        "# Tag Index",
        "",
        f"> {len(tag_to_notes)} unique tags · {sum(len(v) for v in tag_to_notes.values())} tag uses across {len({n['stem'] for ns in tag_to_notes.values() for n in ns})} papers. Re-run `generate_wiki.py` to refresh.",
        "",
        "## Frequent tags (2+ papers)",
        "",
    ]
    frequent = [(t, ns) for t, ns in sorted_tags if len(ns) >= 2]
    rare = [(t, ns) for t, ns in sorted_tags if len(ns) == 1]
    if frequent:
        for tag, ns in frequent:
            lines.append(f"- [[{tag}|#{tag}]] — {len(ns)} papers")
    else:
        lines.append("_(none)_")
    lines.extend(["", "## Single-use tags", ""])
    for tag, ns in rare:
        lines.append(f"- [[{tag}|#{tag}]] — 1 paper")
    if not dry_run:
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"pages_written": written, "tags": len(tag_to_notes)}


# ====== Main ======

def main():
    ap = argparse.ArgumentParser(description="Generate wiki pages (Tags + Concept stubs) for an Obsidian PaperNotes vault.")
    ap.add_argument("--vault", help="Vault root (default: user_config.obsidian_vault)")
    ap.add_argument("--min-refs", type=int, default=2, help="Min [[wiki-link]] references to create a concept stub (default 2)")
    ap.add_argument("--tags-only", action="store_true", help="Skip concept stubs")
    ap.add_argument("--concepts-only", action="store_true", help="Skip tag pages")
    ap.add_argument("--dry-run", action="store_true", help="Print what would be done without writing")
    args = ap.parse_args()

    vault = Path(args.vault).expanduser() if args.vault else obsidian_vault_path()
    notes_root = vault / "PaperNotes"
    if not notes_root.exists():
        print(f"❌ PaperNotes dir not found at: {notes_root}")
        sys.exit(1)

    print(f"Vault: {vault}")
    print(f"PaperNotes: {notes_root}")
    print()
    notes, wiki_to_notes, tag_to_notes = scan_papernotes(notes_root)
    print(f"Scanned {len(notes)} PaperNotes")
    print(f"  {len(tag_to_notes)} unique tags")
    print(f"  {len(wiki_to_notes)} unique [[wiki-link]] refs")
    print()

    if not args.tags_only:
        print(f"== Concept stubs (min refs: {args.min_refs}) ==")
        r = generate_concept_stubs(vault, wiki_to_notes, min_refs=args.min_refs, dry_run=args.dry_run)
        print(f"  created: {r['created']}, updated: {r['updated']}, skipped: {r['skipped']}")
        print()

    if not args.concepts_only:
        print(f"== Tag pages ==")
        r = generate_tag_pages(vault, tag_to_notes, dry_run=args.dry_run)
        print(f"  pages written: {r['pages_written']}, total tags: {r['tags']}")
        print()

    print("✓ Done.")


if __name__ == "__main__":
    main()
