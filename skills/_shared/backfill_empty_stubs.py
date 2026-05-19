#!/usr/bin/env python3
"""
backfill_empty_stubs.py — Find empty concept stubs in the wiki, rank by inbound link count,
and use `claude -p` to write real content for the top-N most-referenced ones.

Usage:
    # Just preview which stubs would be backfilled — no writes, no LLM calls
    python3 backfill_empty_stubs.py --dry-run

    # Backfill the top 15 most-referenced empty stubs (default)
    python3 backfill_empty_stubs.py

    # Backfill top 5 only, requiring at least 2 inbound references
    python3 backfill_empty_stubs.py --top-n 5 --min-inbound 2

The script preserves any Claudian-managed BACKREF block at the end of each file.
Output language follows `output.language` from shared config.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from user_config import obsidian_vault_path, paper_notes_dir, concepts_dir, daily_papers_dir, load_user_config

VAULT = obsidian_vault_path()
CONCEPTS = concepts_dir()
PAPERS_ROOT = paper_notes_dir()
DAILY = daily_papers_dir()

def _resolve_claude_bin() -> str | None:
    """Find the claude CLI. Env override > PATH search > common install locations."""
    env_override = os.environ.get("CLAUDE_BIN")
    if env_override and Path(env_override).is_file() and os.access(env_override, os.X_OK):
        return env_override
    on_path = shutil.which("claude")
    if on_path:
        return on_path
    # Common install locations on macOS
    fallbacks = [
        "/opt/homebrew/bin/claude",
        "/usr/local/bin/claude",
        Path.home() / ".local/bin/claude",
        Path.home() / ".npm-global/bin/claude",
        Path.home() / ".npm/bin/claude",
    ]
    for f in fallbacks:
        f = str(f)
        if Path(f).is_file() and os.access(f, os.X_OK):
            return f
    return None


CLAUDE_BIN = _resolve_claude_bin()

WIKILINK_RE = re.compile(r"\[\[([^\|\]]+?)(?:\|[^\]]+)?\]\]")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.S)
EMPTY_STUB_FRONTMATTER_RE = re.compile(r"^auto_generated:\s*true", re.M)
EMPTY_STUB_BODY_MARKERS = [
    "Stub — fill in",
    "Add definition here.",
    "Add [[wiki-links]] to other concepts here.",
]
BACKREF_BLOCK_RE = re.compile(r"<!-- BACKREF:BEGIN -->.*?<!-- BACKREF:END -->", re.S)


def is_empty_stub(text: str) -> bool:
    m = re.match(r"^---\s*\n(.*?)\n---\s*", text, re.S)
    if m and EMPTY_STUB_FRONTMATTER_RE.search(m.group(1)):
        return True
    body = FRONTMATTER_RE.sub("", text, count=1)
    if any(marker in body for marker in EMPTY_STUB_BODY_MARKERS):
        return True
    body_no_backref = BACKREF_BLOCK_RE.sub("", body)
    body_no_comments = re.sub(r"<!--.*?-->", "", body_no_backref, flags=re.S)
    prose_lines = [
        ln.strip()
        for ln in body_no_comments.split("\n")
        if ln.strip()
        and not ln.startswith("#")
        and not ln.startswith("---")
        and not re.match(r"^\d+\.\s*$", ln)
        and ln.strip() not in {"-", "1.", "2.", "3."}
    ]
    real_prose = [ln for ln in prose_lines if not re.match(r"^[-*]\s*\[\[", ln)]
    return len(real_prose) < 2


def find_empty_stubs() -> list[Path]:
    if not CONCEPTS.exists():
        return []
    return [p for p in CONCEPTS.rglob("*.md") if is_empty_stub(p.read_text(encoding="utf-8", errors="ignore"))]


def count_inbound(targets: set[str]) -> Counter:
    """Count how many .md files reference each target (by stem)."""
    counter: Counter = Counter()
    roots = [PAPERS_ROOT, DAILY]
    for root in roots:
        if not root.exists():
            continue
        for md in root.rglob("*.md"):
            text = md.read_text(encoding="utf-8", errors="ignore")
            seen_this_file = set()
            for m in WIKILINK_RE.finditer(text):
                target = m.group(1).strip()
                # Strip aliases like "Foo|bar" — already split by regex
                if target in targets and target not in seen_this_file:
                    counter[target] += 1
                    seen_this_file.add(target)
    return counter


def find_referencing_papers(target_stem: str) -> list[tuple[Path, str]]:
    """Return list of (file_path, surrounding_context_snippet) for each file referencing target.
    Matches the universe of count_inbound: scans both PaperNotes/ (including _concepts/) and
    DailyPapers/. Concept-to-concept refs from auto-stubs are weak signal, but the snippet
    context is what matters for grounding; downstream LLM can ignore poor snippets.
    """
    out = []
    roots = [r for r in (PAPERS_ROOT, DAILY) if r.exists()]
    for root in roots:
        for md in root.rglob("*.md"):
            text = md.read_text(encoding="utf-8", errors="ignore")
            for m in WIKILINK_RE.finditer(text):
                tgt = m.group(1).strip()
                if tgt == target_stem:
                    start = max(0, m.start() - 80)
                    end = min(len(text), m.end() + 80)
                    snippet = re.sub(r"\s+", " ", text[start:end]).strip()
                    out.append((md, snippet))
                    break
    return out


def preserve_backref(original_text: str) -> str | None:
    m = BACKREF_BLOCK_RE.search(original_text)
    return m.group(0) if m else None


def build_prompt(concept_name: str, referencing: list[tuple[Path, str]], output_language: str) -> str:
    refs_block = "\n".join(
        f"- 论文 [[{p.stem}]] (path: {p.relative_to(VAULT)}), 上下文: \"…{snippet}…\""
        for p, snippet in referencing[:8]
    )
    return f"""你需要给一个空的概念笔记 stub 填写实际内容。

**概念名称**: {concept_name}

**这个概念被以下论文笔记引用**（共 {len(referencing)} 篇）：

{refs_block}

**任务**：基于这些 paper context 和你对该概念的背景知识，输出该概念笔记的完整 markdown 内容。

**输出格式严格遵守**：

```markdown
---
type: concept
aliases: [常见别名 / 缩写 / 同义词]
---

# {concept_name}

## Definition

一句话精准定义。明确这个概念是什么、用在哪个领域。

## Mathematical Form (如有)

若有相关公式，用 $$...$$ LaTeX 块。没有就写 "N/A"。

## Key Points

1. 第一个关键点
2. 第二个关键点
3. 第三个关键点
4. （3-5 条）

## Representative Works

- [[相关论文笔记名]]: 一句话说明该论文为何是代表作

## Related Concepts

- [[相关概念1]]
- [[相关概念2]]
- [[相关概念3]]
```

**重要约束**：
- 输出语言：{output_language}（中文 prose；技术术语 / dataset / model name / formula 保留英文）
- 不要捏造引用——只引用上面 paper context 里真实存在的论文
- 不要写 commentary 或解释，**只输出 markdown 文件内容**，从 `---` 开始
- 不要在末尾加 BACKREF 块——脚本会自动保留原 BACKREF 块
- Related Concepts 列 3-5 个真正相关的概念（你判断，可以是 vault 内或常见 ML 概念）

直接开始输出："""


def llm_generate(prompt: str, timeout_sec: int = 180) -> tuple[bool, str]:
    if not CLAUDE_BIN:
        return False, "claude binary not found (set CLAUDE_BIN env var or install claude on PATH)"
    try:
        result = subprocess.run(
            [CLAUDE_BIN, "-p", "--dangerously-skip-permissions", prompt],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        if result.returncode == 0:
            return True, result.stdout
        return False, f"exit={result.returncode}: {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)


def write_stub(stub_path: Path, generated: str, backref: str | None) -> None:
    # Strip ```markdown ... ``` wrapper if LLM added one
    generated = generated.strip()
    if generated.startswith("```markdown"):
        generated = generated[len("```markdown"):].lstrip()
    elif generated.startswith("```"):
        generated = generated[3:].lstrip()
    if generated.endswith("```"):
        generated = generated[:-3].rstrip()

    if backref:
        generated = generated.rstrip() + "\n\n---\n\n" + backref + "\n"
    else:
        generated = generated.rstrip() + "\n"

    stub_path.write_text(generated, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill top-N most-referenced empty concept stubs.")
    parser.add_argument("--top-n", type=int, default=15, help="Maximum stubs to backfill (default 15)")
    parser.add_argument("--min-inbound", type=int, default=2, help="Skip stubs with fewer than this many inbound refs (default 2)")
    parser.add_argument("--dry-run", action="store_true", help="Print plan only; do not call LLM or write files")
    args = parser.parse_args()

    print(f"Scanning {CONCEPTS} for empty stubs...", file=sys.stderr)
    empty_stubs = find_empty_stubs()
    print(f"  found {len(empty_stubs)} empty stubs total", file=sys.stderr)
    if not empty_stubs:
        print("Nothing to do.", file=sys.stderr)
        return 0

    stub_stems = {p.stem for p in empty_stubs}
    inbound = count_inbound(stub_stems)
    stub_by_stem = {p.stem: p for p in empty_stubs}

    ranked = sorted(stub_stems, key=lambda s: -inbound.get(s, 0))
    target = [(stub_by_stem[s], inbound.get(s, 0)) for s in ranked if inbound.get(s, 0) >= args.min_inbound]
    target = target[: args.top_n]

    if not target:
        print(f"No stubs meet --min-inbound {args.min_inbound}. Lower the threshold to see candidates.", file=sys.stderr)
        # Show top of unfiltered list for diagnosis
        print("\nTop 10 by inbound count (regardless of threshold):", file=sys.stderr)
        for s in ranked[:10]:
            print(f"  {inbound.get(s, 0):3d}x  [[{s}]]", file=sys.stderr)
        return 0

    print(f"\nWould backfill top {len(target)} stubs (min_inbound={args.min_inbound}):", file=sys.stderr)
    for stub, cnt in target:
        print(f"  {cnt:3d}x  [[{stub.stem}]]  ({stub.relative_to(VAULT)})", file=sys.stderr)

    if args.dry_run:
        print("\n[dry-run] no writes, no LLM calls. Run without --dry-run to backfill.", file=sys.stderr)
        return 0

    if not CLAUDE_BIN:
        print("\nERROR: claude CLI binary not found.", file=sys.stderr)
        print("Tried PATH and common install locations (/opt/homebrew/bin, /usr/local/bin, ~/.local/bin, etc).", file=sys.stderr)
        print("Either install it (npm i -g @anthropic-ai/claude-code) or set CLAUDE_BIN=/path/to/claude.", file=sys.stderr)
        return 1

    cfg = load_user_config()
    output_lang = cfg.get("output", {}).get("language", "en")

    print(f"\nLanguage: {output_lang}. Calling {CLAUDE_BIN} for each stub...", file=sys.stderr)
    successes = 0
    failures = []
    for stub, cnt in target:
        print(f"\n→ [{cnt}x] {stub.stem}", file=sys.stderr)
        referencing = find_referencing_papers(stub.stem)
        if len(referencing) < args.min_inbound:
            print(f"  skip: only found {len(referencing)} concrete paper refs", file=sys.stderr)
            continue
        original_text = stub.read_text(encoding="utf-8")
        backref = preserve_backref(original_text)
        prompt = build_prompt(stub.stem, referencing, output_lang)
        ok, output = llm_generate(prompt)
        if not ok:
            print(f"  LLM failed: {output}", file=sys.stderr)
            failures.append(stub.stem)
            continue
        try:
            write_stub(stub, output, backref)
            print(f"  ✓ wrote {len(output)} chars to {stub.relative_to(VAULT)}", file=sys.stderr)
            successes += 1
        except Exception as e:
            print(f"  write failed: {e}", file=sys.stderr)
            failures.append(stub.stem)

    print(f"\nDone: {successes}/{len(target)} stubs backfilled, {len(failures)} failures.", file=sys.stderr)
    if failures:
        print(f"  failed: {failures}", file=sys.stderr)

    # Append to log via post_ingest
    if successes > 0:
        try:
            subprocess.run(
                [sys.executable, str(_HERE / "post_ingest.py"),
                 "lint:backfill",
                 f"backfilled {successes} top empty concept stubs (min_inbound={args.min_inbound})"],
                check=False,
            )
        except Exception as e:
            print(f"post_ingest log append failed: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
