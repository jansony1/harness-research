# Harness Research

LLM Agent Tool Harness 的实验与规范化研究。

通过 hook、middleware、filter 等机制，优化 LLM agent 与工具交互的效率和安全性。

## Projects

| 目录 | 描述 | 状态 |
|------|------|------|
| [context-filter](./context-filter/) | Tool output 分级过滤，减少上下文污染。含 Hook 实现 + MCP Server + 平台无关 Spec | ✅ 已验证 |

## 背景

LLM agent 框架中 tool result 全量注入上下文是普遍做法，但带来三个问题：

1. **上下文稀释** — 无关输出降低模型对关键信息的注意力
2. **窗口浪费** — 加速触发 compaction/truncation，丢失真正重要的历史
3. **成本放大** — 每个后续 turn 都要重新处理这些无用 token

本仓库收集针对这些问题的实验方案和可复用实现。
