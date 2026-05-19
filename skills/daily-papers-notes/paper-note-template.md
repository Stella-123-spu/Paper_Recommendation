---
title: "{{title}}"
method_name: "{{method_name}}"
authors: []
year:
venue:
tags: []  # 3-6 tags from {VAULT}/tag-taxonomy.md (topic/, method/, venue/, data/ prefixes only); never invent new top-level tags
image_source: online
created: {{date}}
---

# {{title}}

```dataviewjs
try {
  const ZOTERO_HOST = 'http://127.0.0.1:23119';
  const TARGET_COLLECTION = 'YW86BS54'; // @Notion

  const fm = dv.current();
  const file = fm.file;
  const tFile = app.vault.getAbstractFileByPath(file.path);
  if (!tFile) throw new Error('cannot read file');
  const body = await app.vault.cachedRead(tFile);

  const bodyOnly = body.replace(/^---[\s\S]*?---\s*/, '');
  const linkRegex = /\[[^\]]*\]\((https?:\/\/[^\)]+)\)/g;
  const urls = [];
  let m;
  while ((m = linkRegex.exec(bodyOnly)) !== null) urls.push(m[1]);

  const priority = (u) => {
    if (u.includes('arxiv.org/abs/')) return 0;
    if (u.includes('openreview.net/forum')) return 1;
    if (u.includes('arxiv.org/pdf/')) return 2;
    if (u.includes('arxiv.org/html/')) return 3;
    if (u.includes('openreview.net/pdf')) return 4;
    if (u.includes('doi.org/')) return 5;
    if (u.includes('pubmed.ncbi')) return 6;
    if (u.includes('biorxiv.org/')) return 7;
    if (u.includes('medrxiv.org/')) return 8;
    return 99;
  };
  const url = urls.sort((a, b) => priority(a) - priority(b))[0];
  if (!url) throw new Error('no URL found in note body');

  const title = String(fm.title || file.name);
  const venue = String(fm.venue || '');
  const year = String(fm.year || '');
  const creators = (fm.authors || []).map(a => {
    const s = String(a).trim();
    const parts = s.split(/\s+/);
    const lastName = parts.pop() || s;
    const firstName = parts.join(' ');
    return firstName
      ? { creatorType: 'author', firstName, lastName }
      : { creatorType: 'author', name: lastName };
  });

  let itemType = 'preprint';
  if (url.includes('pubmed') || url.match(/doi\.org\//)) itemType = 'journalArticle';
  if (url.match(/openreview\.net/) && venue.match(/NeurIPS|ICML|ICLR|COLM|CVPR|ICCV|AAAI/i)) itemType = 'conferencePaper';

  const arxivMatch = url.match(/arxiv\.org\/(?:abs|pdf|html)\/([^?\/v]+)/);
  const archiveID = arxivMatch ? arxivMatch[1] : '';

  const itemData = { itemType, title, url, creators, date: year, collections: [TARGET_COLLECTION] };
  if (archiveID) { itemData.repository = 'arXiv'; itemData.archiveID = archiveID; }
  if (venue && itemType === 'conferencePaper') itemData.conferenceName = venue;
  if (venue && itemType === 'journalArticle') itemData.publicationTitle = venue;

  const payload = { items: [itemData], uri: url };

  const row = dv.el('div', '');
  row.style.cssText = 'display:flex; align-items:center; gap:10px; margin:8px 0; padding:8px; background:var(--background-secondary); border-radius:6px;';
  const btn = row.createEl('button', { text: '📚 Save to Zotero' });
  btn.style.cssText = 'padding:4px 12px; cursor:pointer;';
  const info = row.createEl('span', { text: `${itemType} · @Notion · ${url.length > 50 ? url.slice(0, 50) + '…' : url}` });
  info.style.cssText = 'font-size:0.85em; color:var(--text-muted);';

  btn.addEventListener('click', async () => {
    btn.disabled = true; btn.textContent = '⏳ saving…'; info.textContent = '';
    try {
      // Use Obsidian's requestUrl which bypasses CORS / Origin header issues
      const { requestUrl } = require('obsidian');
      const r = await requestUrl({
        url: `${ZOTERO_HOST}/connector/saveItems`,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Zotero-Allowed-Request': 'true'
        },
        body: JSON.stringify(payload),
        throw: false
      });
      if (r.status >= 200 && r.status < 300) {
        btn.textContent = '✓ Saved'; btn.style.background = 'var(--interactive-success, #a3d977)';
        info.textContent = `HTTP ${r.status} · added to @Notion`;
        new Notice('✓ Added to Zotero @Notion');
      } else {
        btn.textContent = '✗ Failed'; btn.style.background = 'var(--background-modifier-error)';
        info.textContent = `HTTP ${r.status}: ${(r.text || '').slice(0, 120)}`;
        btn.disabled = false;
      }
    } catch (e) {
      btn.textContent = '✗ Error'; btn.style.background = 'var(--background-modifier-error)';
      info.textContent = (e && e.message) ? e.message : String(e);
      btn.disabled = false;
    }
  });
} catch (err) {
  dv.paragraph('⚠️ Zotero button error: ' + (err.message || err));
}
```

## Metadata

| Field | Value |
|---|---|
| Title | {{title}} |
| Authors |  |
| Institutions |  |
| Published |  |
| Links | [arXiv]() / [Code]() |

## 相关论文（共享 tag）

```dataview
TABLE WITHOUT ID
  file.link AS "论文",
  filter(tags, (t) => contains(this.tags, t)) AS "共享 tag",
  venue,
  year
FROM "PaperNotes"
WHERE file.name != this.file.name
  AND method_name
  AND length(filter(tags, (t) => contains(this.tags, t))) > 0
SORT length(filter(tags, (t) => contains(this.tags, t))) DESC
LIMIT 8
```

## One-Sentence Summary


## Core Contributions

1. **Contribution 1**:
2. **Contribution 2**:
3. **Contribution 3**:

## Background

### Problem Being Solved


### Limitations of Existing Methods


### Motivation


## Method Details

### Overall Framework

```text
Input --> [Module A] --> [Module B] --> Output
```

### Core Modules


### Loss Function

$$
L = L_{task} + \lambda L_{reg}
$$

## Experiments

### Datasets

| Dataset | Size | Characteristics |
|---|---|---|
|  |  |  |

### Main Results


### Ablation Studies


## Critical Analysis

### Strengths


### Limitations


### Potential Improvements


## Related Work

| Paper | Relationship | Notes |
|---|---|---|
|  |  |  |

## Further Reading


*Note created: {{date}}*
