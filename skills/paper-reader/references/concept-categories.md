# 概念自动归类规则

概念库位置：`{CONCEPTS_PATH}`

先读取 `../_shared/user-config.json` 中的 `paper_notes_taxonomy` 段。**目录名、关键词、优先级、Zotero 映射都以这一个配置为准。**

工作规则：

1. 先用 `ls {CONCEPTS_PATH}` 查看已有子目录。
2. 按 `paper_notes_taxonomy.categories` 中的顺序匹配。顺序越靠前，优先级越高。
3. 如果一个概念同时命中多个分类，按配置顺序选最前面的那个。
4. 只有完全无法判断时，才使用 `paper_notes_taxonomy.concept_fallback_category`。
5. 如果要迁移到别的研究领域，只改 `user-config.json`，不要在这个文档里再补第二套规则。

需要快速查看当前分类时，直接打开 `../_shared/user-config.json`，看：

- `paper_notes_taxonomy.categories[*].name`
- `paper_notes_taxonomy.categories[*].keywords`
- `paper_notes_taxonomy.fallback_category`
- `paper_notes_taxonomy.concept_fallback_category`

## 概念笔记模板

```markdown
---
type: concept
aliases: [中文别名, 英文别名]
---

# 概念名称

## 定义
{一句话定义}

## 数学形式
$$公式$$

## 核心要点
1. ...
2. ...

## 代表工作
- [[Paper1]]: ...
- [[Paper2]]: ...

## 相关概念
- [[相关概念1]]
- [[相关概念2]]
```
