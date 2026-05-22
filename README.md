# Harness Research

LLM Agent 行为治理框架 — 通过 hook 机制对 coding agent 的执行全流程进行拦截、过滤、监控和控制。

## 框架全景

详见 [FRAMEWORK.md](./FRAMEWORK.md) — 覆盖 5 大问题域、28 个 hook 事件点的完整设计。

```
User Input → [UserPromptSubmit] → LLM 推理 → [PreToolUse] → Tool 执行
                                                                  │
                     ┌────────────────────────────────────────────┤
                     │                                            │
              [PostToolUseFailure]                          [PostToolUse]
                     │                                            │
                     └──────────────┬─────────────────────────────┘
                                    │
                              [PostToolBatch] → 下一轮 LLM → [Stop]
```

## 问题域

| 域 | 解决什么 | 核心 Hook |
|----|---------|----------|
| **Context** | 上下文膨胀、信息稀释 | PostToolUse, PreCompact |
| **Flow** | 方向失控、循环打转、过早放弃 | PreToolUse, PostToolBatch, Stop |
| **Safety** | 破坏性操作、密钥泄露 | PreToolUse, PostToolUse |
| **Quality** | 不测试就交付、低质量输出 | Stop, TaskCompleted, SubagentStop |
| **Observability** | 执行黑箱、无法追溯 | 全事件旁路记录 |

## Projects

| 目录 | 域 | 描述 | 状态 |
|------|---|------|------|
| [context-filter](./context-filter/) | Context | Tool output 分级过滤（日志/JSON/测试/通用截断） | ✅ 已验证 |
| [pivot-gate](./pivot-gate/) | Flow | 检测设计转向，暂停等待人工审核 | ✅ 已验证 |
| safety-guard | Safety | 破坏性命令拦截 + 敏感信息防泄露 | 🔲 计划中 |
| stop-gate | Quality | 停止前强制验证（测试通过、lint clean） | 🔲 计划中 |
| loop-breaker | Flow | 循环打转检测与熔断 | 🔲 计划中 |
| session-logger | Observability | 全事件流日志 + 统计报告 | 🔲 计划中 |

## 平台兼容性

| 能力 | Claude Code | Kiro | Cursor |
|------|------------|------|--------|
| PreToolUse 阻断 | ✅ | ✅ | ❌ |
| PostToolUse 替换输出 | ✅ | ❌ (issue #7417) | ❌ |
| PostToolBatch 阻断 | ✅ | ❌ | ❌ |
| Stop 阻断 | ✅ | ❌ | ❌ |
| MCP Server (通用降级方案) | ✅ | ✅ | ✅ |
