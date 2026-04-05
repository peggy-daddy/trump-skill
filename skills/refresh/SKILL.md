---
name: refresh
description: 🔄 刷新语料库 — 搜索最近的特朗普发言，更新本地热点数据
---

# 刷新语料库

通过 web search 获取特朗普最近的公开发言和热点话题，更新本地数据。

## 流程

1. 使用 WebSearch 工具搜索以下关键词（分多次搜索以获取更全面的结果）：

   - `"Trump posted on Truth Social" latest 2026`
   - `"Trump said" OR "Trump statement" recent`
   - `Trump tariffs OR Iran OR immigration latest`

   注意：Truth Social 不被搜索引擎直接索引，从新闻报道中提取特朗普原话。

2. 从搜索结果中提取：
   - 5-10 个热门话题
   - 每个话题下特朗普的原话（保留英文原文）
   - 标注每个话题对应的十神分类

3. 将提取的内容写入 `data/recent-topics.md`，使用以下格式：

```markdown
# Trump Recent Topics — [年月]

> 最后更新：[日期]
> 通过 `/trump:refresh` 更新

## [话题名] [话题分类标签]

[简要描述]

关键语录：
- "[原话1]"
- "[原话2]"

话题分类：[对应的十神]
```

4. 完成后回复确认：

```
🔄 语料库已更新。

特朗普最近在说：
1. [话题1] → 触发十神：[十神列表]
2. [话题2] → 触发十神：[十神列表]
3. [话题3] → 触发十神：[十神列表]
...

共收录 [N] 条新语录。TREMENDOUS update! Believe me.
```

## 话题到十神的映射参考

| 话题关键词 | 对应十神 |
|-----------|---------|
| 军事、战争、制裁、打击 | 七杀·The Warlord |
| 行政命令、政策、法案 | 正官·The POTUS |
| 关税、贸易、谈判、协议 | 食神·The Dealer |
| 经济、商业、就业、GDP | 偏财·The Mogul、正财·The Accountant |
| 媒体、假新闻、调查 | 伤官·The Attacker |
| 选举、民调、支持率 | 比肩·The Ego、偏印·The Showman |
| 移民、边境、非法入境 | 七杀·The Warlord、劫财·The Winner |
| 集会、演讲、收视率 | 偏印·The Showman |
| 家族、Ivanka、传承 | 正印·The Dynasty |
| 对手、竞争、比较 | 劫财·The Winner |

## 重要约束

- 仅从公开新闻报道中提取信息
- 保留特朗普原话的英文原文
- 不要编造或虚构特朗普没说过的话
- 如果搜索结果有限，保留已有的 recent-topics.md 内容并追加新内容
