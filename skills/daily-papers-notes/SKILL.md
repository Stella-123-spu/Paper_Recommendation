---
name: daily-papers-notes
description: |
  论文笔记生成（3 步流水线的第 3 步）。补充概念库，为推荐论文生成完整笔记，
  链接回填到推荐文件；目录页默认自动刷新，git 自动化默认关闭。

  触发词："批量笔记"、"跑一下论文笔记"
---

> **开始前**: 先说一声 "开始整理笔记 📝" 并告知今天日期。

# 论文笔记 (Concepts + Notes + Backfill)

你是 用户的论文笔记系统（3 步流水线的第 3 步）。补充概念库 → 生成论文笔记 → 链接回填 → 刷新目录页。

## Step 0: 读取共享配置

先读取 `../_shared/user-config.json`，如果 `../_shared/user-config.local.json` 存在，再用它覆盖默认值。

显式生成并在后续统一使用这些变量：

- `VAULT_PATH`
- `NOTES_PATH`
- `CONCEPTS_PATH`
- `DAILY_PAPERS_PATH`
- `NOTE_TEMPLATE = ../daily-papers-notes/论文笔记模板.md`
- `AUTO_REFRESH_INDEXES`
- `GIT_COMMIT_ENABLED`
- `GIT_PUSH_ENABLED`
- `ENRICHED_INPUT = /tmp/daily_papers_enriched.json`

其中：

- `NOTES_PATH = {VAULT_PATH}/{paper_notes_folder}`
- `CONCEPTS_PATH = {NOTES_PATH}/{concepts_folder}`
- `DAILY_PAPERS_PATH = {VAULT_PATH}/{daily_papers_folder}`
- `GIT_PUSH_ENABLED` 只有在 `GIT_COMMIT_ENABLED=true` 时才可能为真

后续步骤统一使用上面的变量。

概念补充、论文笔记重点和链接回填的主题判断也统一以共享配置为准，不要沿用过时的默认语境。

## 前置检查

1. 检查 `/tmp/daily_papers_enriched.json` 是否存在
2. 检查今天的推荐文件 `{DAILY_PAPERS_PATH}/YYYY-MM-DD-论文推荐.md` 是否存在
3. 如果任一不存在，告知用户需要先运行前置步骤，然后停止

## 工作流程

### Step 1: 概念库补充

**1a: 提取概念列表**
1. 扫描今天的推荐文件，提取所有 `[[...]]` 链接
2. 额外从 `/tmp/daily_papers_enriched.json` 的 `method_names` 列表中提取所有方法名
3. 合并去重

**1b: 过滤**
只保留以下类型的术语（跳过通用词、论文自身名称、公司名、人名）：
- 方法/模型名（如 Q-Former, Parseval Regularization, CVAE, PCM）
- 数据集名（如 MIMIC-IV, eICU, PhysioNet, UK Biobank）
- 框架/基准名（如 Med-PaLM, BEHRT, RETAIN, CLMBR）
- 技术概念名（如 counterfactual inference, temporal abstraction, intervention modeling）

**1c: 创建缺失的概念笔记（自动归类）**
检查 `{CONCEPTS_PATH}/` 下是否已存在（搜索所有子目录）。对于缺失的概念，**根据概念类型自动归类到对应子目录**，不要全扔 `0-uncategorized/`。

分类规则见 `../paper-reader/references/concept-categories.md`

概念笔记模板见 `../paper-reader/references/concept-categories.md`

### Step 2: 论文笔记生成

为推荐论文生成完整论文笔记：

1. 从今天的推荐文件中，读取分流表，筛选出标记为"必读"的论文
2. **兜底规则**：如果今天分流表里没有"必读"，不要让 `PaperNotes/` 空着。此时从"值得看"中按出现顺序挑选前 1-2 篇作为今天的重点论文，照常生成完整笔记。
3. **必须使用 subagents 并行执行**，不要写 Python 包装脚本代替：
   - 为每篇需要生成的论文 `spawn_agent`
   - `spawn_agent` 时模型固定使用 `gpt-5.4-mini`
   - 每个 subagent 只负责 **1 篇论文 + 1 个目标笔记文件**
   - 明确告诉 subagent：代码库里不止它一个，不要回滚别人改动；它的职责只是调用 `paper-reader` skill 生成该论文笔记
   - 若论文数 > 1，优先并行生成，而不是串行一篇篇慢跑
   - 只有在拿到 subagent 结果后，主线程再统一做质量检查、回填链接、刷新索引
4. **质量检查已有笔记**（不是只看文件是否存在）：
   - 对已有 `📒 **笔记**` 标记的论文，用 Glob 找到对应笔记文件，检查行数
   - **行数 < 100 的视为骨架笔记，必须重新生成**（删除旧文件，重新调用 paper-reader）
   - 行数 >= 100 且包含 `## 关键公式` 和 `## 关键图表` 的才算合格，可以跳过
5. 对每篇需要生成/重新生成的论文，让对应的 subagent 调用 `paper-reader` skill（传入 arXiv 链接）
6. 笔记生成后，paper-reader 会自动补充概念库，无需重复
7. 如果用户提供了 Obsidian 笔记模板，或当前 skill 已配置 `NOTE_TEMPLATE`，则 subagent 必须把该模板作为最终成稿骨架；可以补充 `paper-reader` 要求的公式、图片、表格和概念链接，但不要偏离模板主结构

#### subagent 执行模板

给每个 subagent 的任务里，至少包含这些信息：

- 论文标题
- arXiv 链接
- 目标根目录：`{NOTES_PATH}`
- 模板路径：`{NOTE_TEMPLATE}`
- 约束：必须使用 `paper-reader` skill；必须写出真实论文笔记，不能只更新 `_index.md` 之类的目录页
- 模型要求：subagent 使用 `gpt-5.4-mini`
- 协作提醒：你不是唯一在工作的 agent，不要回滚他人更改；只负责这 1 篇论文

推荐发给 subagent 的话术类似：

```text
请处理这 1 篇论文，不要处理别的论文。你不是独自在代码库里工作，不要回滚他人的改动。
必须使用 [$paper-reader](../paper-reader/SKILL.md) skill 生成完整论文笔记。
请使用 gpt-5.4-mini。
论文：{标题}
链接：{arXiv URL}
模板：{NOTE_TEMPLATE}
输出要求：把真实笔记写到 {NOTES_PATH} 下，不要只更新目录页；最终结构以模板为骨架，同时保留 paper-reader 要求的完整内容；完成后回复最终笔记路径。
```

> **铁律**：不论论文数量多少，"必读"的论文**全部**生成笔记，一篇不能少。
> 耗时长是正常的，不是偷懒的理由。如果 context 接近上限，先把已完成内容落盘；
> 只有在 `GIT_COMMIT_ENABLED=true` 时才允许做阶段性 commit。然后告知用户剩余论文需要在新会话中继续，**绝对不能默默跳过**。

#### ⚠️ 笔记质量硬性要求

**绝对禁止自己手写简化版笔记。每篇论文必须通过 `paper-reader` skill 生成。**
不要因为"怕 context overflow"或"论文太多"就自己写个 70 行的骨架糊弄过去。
如果当前会话上下文接近上限，可以开启新的 Codex 会话继续剩余论文；但不能跳过任何一篇必读论文。

笔记质量由 paper-reader skill 自身保证（模板、公式、图片、概念链接等规则均在 paper-reader 中定义）。
如果同时存在用户模板与 paper-reader 默认模板，优先以用户模板为最终章节骨架，再补齐 paper-reader 的质量要件。

#### 🔍 生成后质量验证（每篇必须执行）

每篇笔记生成后，立即验证：
1. 文件行数 >= 120（低于此值说明内容不完整）
2. 包含 `$$` 或 `$` LaTeX 公式（至少 2 处）
3. 包含 `![` 图片引用（至少 1 张）
4. 包含 `## 关键公式` 和 `## 实验结果` section header
5. 如果任一条件不满足，**删除文件并重新生成**

### Step 3: 笔记链接回填

论文笔记全部生成完成后，将笔记链接回填到当天的推荐文件中。

**3a: 收集已有笔记**

用 Glob 扫描 `{NOTES_PATH}/` 下所有子目录（跳过 `{CONCEPTS_PATH}`），获取所有 `.md` 文件列表，建立 `{文件名(不含.md): 相对路径}` 的索引。

**3b: 匹配论文与笔记**

读取当天推荐文件 `{DAILY_PAPERS_PATH}/YYYY-MM-DD-论文推荐.md`，对每篇论文（`### N.` 开头的段落）：

1. 从论文标题中提取方法名/模型名（通常是标题冒号前的缩写，如 "DM0"、"BPP"、"PA3FF"）
2. 与 3a 的笔记索引匹配（不区分大小写）
3. 也检查富化数据的 `method_names`（如果有残留数据）

**3c: 插入笔记链接**

对匹配到笔记的论文，在 `- **来源**:` 行之后插入一行：

```markdown
- 📒 **笔记**: [[笔记名]]
```

其中 `笔记名` 是不含 `.md` 后缀的文件名（Obsidian 会自动解析到正确路径）。

- 如果该论文已有 `📒 **已有笔记**` 或 `📒 **笔记**` 行，跳过不重复添加
- 使用 Edit 工具逐篇插入，确保不破坏文件其他内容

### Step 4: 刷新 MOC 索引

只有在 `AUTO_REFRESH_INDEXES=true` 时才执行：

```bash
python3 ../_shared/generate_concept_mocs.py
python3 ../_shared/generate_paper_mocs.py
```

默认配置下这个开关是开启的，所以新增的概念和论文笔记通常会自动反映到各分类目录页中。

### Step 5: Git 提交

仅当 `GIT_COMMIT_ENABLED=true` 时执行，并且必须先检查：

1. `VAULT_PATH/.git` 存在
2. `git add -A` 后确实有 staged changes

满足条件后才 commit：

```bash
cd {VAULT_PATH} && git add -A && git commit -m "daily papers: notes YYYY-MM-DD"
```

只有在 `GIT_PUSH_ENABLED=true` 且仓库已配置远端时才 push。

## 输出

完成后告知用户：
- 创建了多少个新概念
- 生成了多少篇论文笔记
- 回填了多少个笔记链接
- 流水线全部完成

## 注意事项

- 如果前置文件不存在，必须先运行前面的步骤
- `paper-reader` skill 会自动处理概念库补充，不要重复创建
- 优先为"必读"论文生成笔记；如果当天没有"必读"，必须从"值得看"里补 1-2 篇重点论文，不能让 `PaperNotes/` 只剩目录页
- 默认自动刷新目录页，但默认不做 git commit / push
- **绝对禁止**以下偷懒行为：
  - 自己手写 70 行骨架笔记代替 paper-reader 输出
  - 用 Python 脚本包装 `codex exec` 来批量替代 subagents
  - 以"context overflow"为由跳过论文不生成笔记
  - 看到文件已存在就跳过，不检查质量
  - 生成笔记后不做质量验证
- 如果 context 真的接近上限：先保存已完成的笔记；只有在 `GIT_COMMIT_ENABLED=true` 时才 commit。然后**明确告知用户**还有 N 篇未完成，需要在新会话中运行 `跑一下论文笔记` 继续。绝不能默默跳过
