# Image Troubleshooting

Use this reference when paper figures do not load, arXiv HTML is incomplete, or figure numbering does not match the PDF.

## Retrieval Priority

### Source A: arXiv HTML (Preferred)

Fetch:

```text
https://arxiv.org/html/{arxiv_id}
```

Extract every `<figure>` block, including caption text and image URLs. Count the extracted figures and compare with the paper's figure count.

### Source B: Project Page

Use this when arXiv HTML is unavailable or missing figures.
Look for project-page links in the abstract, arXiv page, paper footer, GitHub README, or author pages.

### Source C: PDF Extraction (Final Fallback)

```bash
mkdir -p {note_directory}/assets/
pdfimages -png /tmp/paper.pdf {note_directory}/assets/{method_name}_fig
```

Keep only real figures, usually files larger than 10 KB. Ignore logos, icons, and tiny artifacts.

## External Link Reliability

arXiv external image links can be unstable in some network environments. After saving a note, run the reachability check:

```bash
python3 ../daily-papers/download_note_images.py "{note_path}"
```

The script keeps reachable links unchanged and downloads unreachable links into local `assets/` storage.

## URL Cleanup

Before writing any image URL, check for duplicated arXiv ID path segments.

Bad:

```text
https://arxiv.org/html/2603.05312v1/2603.05312v1/x1.png
```

Good:

```text
https://arxiv.org/html/2603.05312v1/x1.png
```

## Hard Rule

Before writing a note, every image URL must be checked for:

- duplicate path segments
- obvious 404 patterns
- missing scheme such as `https://`
- suspicious tiny local files below 10 KB

## Image Reference Format in Notes

Use standard Markdown images:

```markdown
![Figure 1: short caption](https://example.com/figure.png)
```

For localized Obsidian assets, use wikilinks when the helper script replaces them:

```markdown
![[assets/Figure_1.png]]
```

## Frontmatter Image Source

Record image provenance in frontmatter:

- `image_source: online` when all images are external and reachable
- `image_source: local` when all images are local
- `image_source: mixed` when both are used
