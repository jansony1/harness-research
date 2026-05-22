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
| [context-filter](./context-filter/) | Context | PostToolUse 替换输出 — 日志/JSON/测试/通用截断 | ✅ 5 tests |
| [input-modifier](./input-modifier/) | Context+Safety | PreToolUse 修改参数 — dry-run/timeout/limit 注入 | ✅ 11 tests |
| [compact-guard](./compact-guard/) | Context | PreCompact 阻断 + PostCompact 注入恢复 — 记忆保护 | ✅ 7 tests |
| [context-injector](./context-injector/) | Flow+Quality | 多事件注入上下文 — 失败警告/checkpoint/subagent 质量 | ✅ 8 tests |
| [safety-guard](./safety-guard/) | Safety | PreToolUse 阻断 — 破坏性命令/凭证/生产环境拦截 | ✅ 30 tests |
| [pivot-gate](./pivot-gate/) | Flow | PostToolUse 替换输出 — 设计转向检测 + 人工审核 | ✅ 6 tests |
| [loop-breaker](./loop-breaker/) | Flow | PostToolBatch 阻断 — 循环打转检测与熔断 | ✅ 6 tests |
| [stop-gate](./stop-gate/) | Quality | Stop 阻断 + PostToolUse 采集 — 停止前强制验证 | ✅ 6 tests |
| session-logger | Observability | 全事件旁路记录 — 日志 + 统计报告 | 🔲 计划中 |

## 平台兼容性

| 能力 | Claude Code | Kiro | Cursor |
|------|------------|------|--------|
| PreToolUse 阻断 | ✅ | ✅ | ❌ |
| PostToolUse 替换输出 | ✅ | ❌ (issue #7417) | ❌ |
| PostToolBatch 阻断 | ✅ | ❌ | ❌ |
| Stop 阻断 | ✅ | ❌ | ❌ |
| MCP Server (通用降级方案) | ✅ | ✅ | ✅ |
