#!/usr/bin/env python3
"""
generate_wiki_index.py — Scan the vault and emit a Karpathy-style index.md catalog.

Reads the Healthcare AI vault (from user-config.json paths) and writes a structured
index of all papers, concepts, themes, and comparisons, with empty-stub flagging.

Usage:
    python3 generate_wiki_index.py

Writes to: {vault}/index.md
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

_SHARED = Path(__file__).resolve().parent
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from user_config import obsidian_vault_path, paper_notes_dir, daily_papers_dir, concepts_dir

VAULT = obsidian_vault_path()
PAPER_NOTES = paper_notes_dir()
CONCEPTS = concepts_dir()
DAILY = daily_papers_dir()

WIKILINK_RE = re.compile(r"\[\[([^\|\]]+?)(?:\|[^\]]+)?\]\]")
EMPTY_STUB_FRONTMATTER_RE = re.compile(r"^auto_generated:\s*true", re.M)
EMPTY_STUB_BODY_MARKERS = [
    "Stub — fill in",  # Claudian's literal placeholder
    "Add definition here.",
    "Add [[wiki-links]] to other concepts here.",
]
BACKREF_BLOCK_RE = re.compile(r"<!-- BACKREF:BEGIN -->.*?<!-- BACKREF:END -->", re.S)


def relpath(p: Path) -> str:
    return str(p.relative_to(VAULT))


def is_empty_stub(text: str) -> bool:
    """Heuristic: file is an unfilled stub (Claudian template or similar)."""
    # Strongest signal: explicit auto_generated flag in frontmatter
    m = re.match(r"^---\s*\n(.*?)\n---\s*", text, re.S)
    if m and EMPTY_STUB_FRONTMATTER_RE.search(m.group(1)):
        return True

    # Second signal: literal stub placeholder text anywhere in body
    body = re.sub(r"^---.*?---\s*", "", text, count=1, flags=re.S)
    if any(marker in body for marker in EMPTY_STUB_BODY_MARKERS):
        return True

    # Third signal: after stripping Claudian's BACKREF auto-block, comments,
    # and headings/blanks, there's basically no prose.
    body_no_backref = BACKREF_BLOCK_RE.sub("", body)
    body_no_comments = re.sub(r"<!--.*?-->", "", body_no_backref, flags=re.S)
    prose_lines = [
        ln.strip()
        for ln in body_no_comments.split("\n")
        if ln.strip()
        and not ln.startswith("#")
        and not ln.startswith("---")
        and not re.match(r"^\d+\.\s*$", ln)  # empty numbered point
        and not ln.strip() in {"-", "1.", "2.", "3."}
    ]
    # Discount lines that are just wikilink lists (auto-populated by Claudian)
    real_prose = [ln for ln in prose_lines if not re.match(r"^[-*]\s*\[\[", ln)]
    return len(real_prose) < 2


def first_paragraph(text: str) -> str:
    """Return one-line summary from first non-frontmatter paragraph or TLDR."""
    body = re.sub(r"^---.*?---\s*", "", text, count=1, flags=re.S)
    body = re.sub(r"^# .*\n", "", body, count=1)
    # Look for "One-Sentence Summary" / "Definition" heading first
    for heading in ("One-Sentence Summary", "## Definition", "## TLDR", "## Summary"):
        m = re.search(rf"{re.escape(heading)}\s*\n+(.+?)(?:\n\n|\n##)", body, re.S)
        if m:
            line = m.group(1).strip().split("\n")[0]
            return line[:200]
    # Fallback: first non-empty line of body
    for ln in body.split("\n"):
        ln = ln.strip()
        if ln and not ln.startswith("#") and not ln.startswith("|") and not ln.startswith("-"):
            return ln[:200]
    return ""


def collect_papers() -> list[dict]:
    items = []
    if not PAPER_NOTES.exists():
        return items
    for path in sorted(PAPER_NOTES.rglob("*.md")):
        # Skip _concepts/, themes/, comparisons/ — handled separately
        rel = path.relative_to(PAPER_NOTES)
        top = rel.parts[0] if rel.parts else ""
        if top in {"_concepts", "themes", "comparisons"}:
            continue
        text = path.read_text(errors="ignore")
        items.append({
            "name": path.stem,
            "path": relpath(path),
            "category": top,
            "summary": first_paragraph(text),
            "empty": is_empty_stub(text),
        })
    return items


def collect_concepts() -> list[dict]:
    items = []
    if not CONCEPTS.exists():
        return items
    for path in sorted(CONCEPTS.rglob("*.md")):
        text = path.read_text(errors="ignore")
        items.append({
            "name": path.stem,
            "path": relpath(path),
            "summary": first_paragraph(text),
            "empty": is_empty_stub(text),
        })
    return items


def collect_themes() -> list[dict]:
    items = []
    themes_dir = PAPER_NOTES / "themes"
    if not themes_dir.exists():
        return items
    for path in sorted(themes_dir.rglob("*.md")):
        text = path.read_text(errors="ignore")
        items.append({"name": path.stem, "path": relpath(path), "summary": first_paragraph(text)})
    return items


def collect_comparisons() -> list[dict]:
    items = []
    cmp_dir = PAPER_NOTES / "comparisons"
    if not cmp_dir.exists():
        return items
    for path in sorted(cmp_dir.rglob("*.md")):
        text = path.read_text(errors="ignore")
        items.append({"name": path.stem, "path": relpath(path), "summary": first_paragraph(text)})
    return items


def collect_daily() -> list[dict]:
    items = []
    if not DAILY.exists():
        return items
    for path in sorted(DAILY.glob("*.md"), reverse=True):
        items.append({"name": path.stem, "path": relpath(path)})
    return items[:20]  # last 20 only


def render() -> str:
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    papers = collect_papers()
    concepts = collect_concepts()
    themes = collect_themes()
    comparisons = collect_comparisons()
    daily = collect_daily()

    empty_concepts = sum(1 for c in concepts if c["empty"])
    empty_papers = sum(1 for p in papers if p["empty"])

    out = [
        "# Wiki Index",
        "",
        f"*Last generated: {today} by `generate_wiki_index.py`*",
        "",
        "## Summary",
        "",
        f"- **Paper notes**: {len(papers)} ({empty_papers} empty stubs)",
        f"- **Concept pages**: {len(concepts)} ({empty_concepts} empty stubs — run `wiki-lint` to triage)",
        f"- **Theme overviews**: {len(themes)}",
        f"- **Comparisons**: {len(comparisons)}",
        f"- **Daily recommendations** (most recent shown): {len(daily)}",
        "",
        "---",
        "",
    ]

    # Themes
    out += ["## Themes (主题综述)", ""]
    if themes:
        for t in themes:
            line = f"- [[{t['name']}]]"
            if t["summary"]:
                line += f" — {t['summary']}"
            out.append(line)
    else:
        out.append("_None yet. Create with `wiki-theme {theme-name}`._")
    out += ["", "---", ""]

    # Comparisons
    out += ["## Comparisons (对比)", ""]
    if comparisons:
        for c in comparisons:
            line = f"- [[{c['name']}]]"
            if c["summary"]:
                line += f" — {c['summary']}"
            out.append(line)
    else:
        out.append("_None yet. Generate during query workflow when synthesizing across papers._")
    out += ["", "---", ""]

    # Papers grouped by category
    out += ["## Papers (论文笔记)", ""]
    by_cat = {}
    for p in papers:
        by_cat.setdefault(p["category"] or "_inbox", []).append(p)
    for cat in sorted(by_cat.keys()):
        out += [f"### {cat}", ""]
        for p in sorted(by_cat[cat], key=lambda x: x["name"]):
            marker = " ⚠️ empty stub" if p["empty"] else ""
            line = f"- [[{p['name']}]]{marker}"
            if p["summary"] and not p["empty"]:
                line += f" — {p['summary'][:120]}"
            out.append(line)
        out.append("")
    out += ["---", ""]

    # Concepts (compact, grouped by subdirectory)
    out += ["## Concepts (概念笔记)", ""]
    by_concept_cat = {}
    for c in concepts:
        parts = Path(c["path"]).parts
        subcat = parts[-2] if len(parts) >= 3 else "_root"
        by_concept_cat.setdefault(subcat, []).append(c)
    for sub in sorted(by_concept_cat.keys()):
        items = by_concept_cat[sub]
        n_empty = sum(1 for c in items if c["empty"])
        out += [f"### {sub} ({len(items)} total, {n_empty} empty)", ""]
        for c in sorted(items, key=lambda x: x["name"]):
            marker = " ⚠️" if c["empty"] else " ✓"
            out.append(f"- {marker} [[{c['name']}]]")
        out.append("")
    out += ["---", ""]

    # Daily recommendations (recent)
    out += ["## Daily / Conference Recommendations (recent 20)", ""]
    for d in daily:
        out.append(f"- [[{d['name']}]]")
    if not daily:
        out.append("_None yet._")

    return "\n".join(out) + "\n"


def main():
    text = render()
    out_path = VAULT / "index.md"
    out_path.write_text(text, encoding="utf-8")
    print(f"Wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
