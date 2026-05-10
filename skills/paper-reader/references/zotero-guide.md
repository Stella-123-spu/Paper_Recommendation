# Zotero Guide

## Query Papers Under a Collection (Recursive Supported)

Common commands:

```bash
python3 assets/zotero_helper.py collections          # list all collections
python3 assets/zotero_helper.py papers 1             # list papers under collection ID 1
python3 assets/zotero_helper.py papers 1 --recursive # include child collections recursively
python3 assets/zotero_helper.py info 12345           # inspect one paper item
```

Batch collection logic:

1. Get all child collection IDs for the target collection by recursively traversing `parentCollectionID`.
2. Query items linked to any of those collections.
3. Deduplicate because one paper may appear in multiple collections.

## Get Zotero Collection Path

Collection paths should preserve hierarchy, for example:

```text
top Level/Subtopic/Theme
```

Use the helper functions in `assets/zotero_helper.py` instead of manually joining IDs.

## Intelligent Categorization

**Do not rely only on keyword matching.** Understand the paper's core contribution before categorizing it. The taxonomy in shared config provides candidate directories and priority, not a replacement for judgment.

Recommended process:

1. Read the paper title, abstract, and main contribution.
2. Inspect existing categories with `python3 assets/zotero_helper.py collections`.
3. Choose the most useful category by asking: where would I look for this paper later?
4. Categorize by **primary contribution**, not by a secondary technique.
5. Interdisciplinary papers may be added to multiple categories, but choose the core category as the main note path.

### Categorization Examples

| Paper Type | Wrong Category | Right Category | Reason |
|---|---|---|---|
| EHR foundation model | Generic LLM | EHR foundation model | The data and transfer setting define the contribution |
| Treatment-effect model | Generic prediction | Causal and intervention modeling | The core contribution is intervention reasoning |
| Survey / benchmark | One method branch | Survey / benchmark | Paper type matters more than technique stack |
| Interdisciplinary paper | Secondary component | Primary application setting | Future readers search by the main use case |

## Zotero Collection Operations

```bash
# inspect current paper collections
python3 assets/zotero_helper.py info {item_id}

# find target collection ID
python3 assets/zotero_helper.py find-collection "collection name"

# add to a collection
python3 assets/zotero_helper.py add-to-collection {item_id} {collection_id}

# remove from a collection
python3 assets/zotero_helper.py remove-from-collection {item_id} {collection_id}

# move from one collection to another
python3 assets/zotero_helper.py move {item_id} {new_collection_id} --from {old_collection_id}
```

### When to Move Collections

| Current Collection | Handling |
|---|---|
| temporary collections such as "2025", "misc", or a personal inbox | must move |
| category clearly mismatches paper content | move to the correct category |
| category is roughly right but could be more precise | optionally move to a subcategory |
| paper belongs to multiple areas | add secondary categories, but keep one main path |
