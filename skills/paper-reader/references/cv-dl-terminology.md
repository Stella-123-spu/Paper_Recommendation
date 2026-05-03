# 共享领域术语表

这个文件不再维护独立内容。

唯一术语来源是 `../../_shared/user-config.json` 里的：

- `domain.name`
- `domain.summary`
- `domain.focus_themes`
- `domain.related_themes`
- `domain.terminology`

使用规则：

1. 需要查术语、别名、定义时，直接读取共享配置里的 `domain.terminology`。
2. 需要切换到别的研究领域时，只修改 `user-config.json`，不要在这里复制第二份术语表。
3. 如果分析新论文时发现应该补充术语，也只更新 `user-config.json`。

当前这个 Markdown 文件只保留为兼容入口，避免其他 skill 或人工习惯引用旧路径时读到过期内容。
