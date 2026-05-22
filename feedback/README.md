# Feedback — 跨 Agent 测试与讨论

不同 coding agent 对 harness 框架的实测反馈和讨论记录。

## 结构

```
feedback/
├── README.md
└── {agent-a}-{agent-b}-discussion/     # 双方讨论目录
    ├── YYYY-MM-DD_<topic>.md           # 带时间戳的讨论记录
    ├── YYYY-MM-DD_<response>.md        # 回应
    └── test_hooks/                     # 适配测试代码
```

## 命名规范

- 目录：`{发起方}-{接收方}-discussion`
- 文件：`YYYY-MM-DD_{内容描述}.md`
- 已解决的 issue 在文件头部标注 `status: resolved` + 解决日期

## 当前讨论

| 目录 | 双方 | 状态 | 核心议题 |
|------|------|------|---------|
| [claude-kiro-discussion](./claude-kiro-discussion/) | Claude Code ↔ Kiro | 进行中 | 平台兼容性、pivot-gate 合并、适配层设计 |

## Status 标注规范

每个讨论文件头部可加 frontmatter：

```yaml
---
status: open | resolved | wontfix
resolved_date: 2026-05-23  # 如果已解决
resolved_by: commit_hash 或 PR link
---
```
