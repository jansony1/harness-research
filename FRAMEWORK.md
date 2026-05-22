# Agent Harness Framework — 全景设计

## 执行链路图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  ① SessionStart                                                             │
│  ┌─────────────────────────────────────────────────────────┐                │
│  │ context-injector: 注入 session 规则、恢复 prior state    │                │
│  └─────────────────────────────────────────────────────────┘                │
│                          │                                                  │
│                          ▼                                                  │
│  ② UserPromptSubmit                                                         │
│  ┌─────────────────────────────────────────────────────────┐                │
│  │ context-injector: 重置计分器                             │                │
│  │ (可扩展: 输入验证、prompt 改写)                          │                │
│  └─────────────────────────────────────────────────────────┘                │
│                          │                                                  │
│                          ▼                                                  │
│                   ┌──────────────┐                                          │
│                   │  LLM 推理    │                                          │
│                   └──────┬───────┘                                          │
│                          │ 生成 tool call(s)                                │
│                          ▼                                                  │
│  ③ PreToolUse                                                               │
│  ┌─────────────────────────────────────────────────────────┐                │
│  │ safety-guard:    阻断破坏性命令 (exit 2 → deny)          │                │
│  │ input-modifier:  篡改参数 (--dry-run, timeout, limit)   │                │
│  │ pivot-gate:      阻断 revert/reset 操作                  │                │
│  └─────────────────────────────────────────────────────────┘                │
│                          │                                                  │
│                          ▼                                                  │
│                   ┌──────────────┐                                          │
│                   │  Tool 执行    │                                          │
│                   └──────┬───────┘                                          │
│                          │                                                  │
│              ┌───────────┼───────────┐                                      │
│              │ 成功      │           │ 失败                                  │
│              ▼           │           ▼                                       │
│  ④ PostToolUse           │  ⑤ PostToolUseFailure                            │
│  ┌─────────────────┐    │  ┌──────────────────────────────┐                │
│  │ context-filter:  │    │  │ context-injector:             │                │
│  │  替换/截断输出   │    │  │   累积失败计数               │                │
│  │ stop-gate-tracker│    │  │   注入 "连续失败N次" 警告     │                │
│  │  采集测试状态    │    │  │ pivot-gate:                   │                │
│  │ compact-collector│    │  │   累积 score                  │                │
│  │  收集 markers    │    │  └──────────────────────────────┘                │
│  └─────────────────┘    │                                                   │
│              │           │           │                                       │
│              └───────────┼───────────┘                                      │
│                          ▼                                                  │
│  ⑥ PostToolBatch (一批并行 tool 全部完成后)                                  │
│  ┌─────────────────────────────────────────────────────────┐                │
│  │ loop-breaker:     检测重复模式 → 阻断下轮推理            │                │
│  │ context-injector: 每 N 批注入 checkpoint                 │                │
│  │ pivot-gate:       综合评估 score → 阻断                  │                │
│  └─────────────────────────────────────────────────────────┘                │
│                          │                                                  │
│                          ▼                                                  │
│                   ┌──────────────┐                                          │
│                   │  LLM 推理    │ (下一轮)                                  │
│                   └──────┬───────┘                                          │
│                          │                                                  │
│              ┌───────────┴───────────┐                                      │
│              │ 继续调用 tool         │ 决定停止                              │
│              │ (回到 ③)              ▼                                       │
│              │               ⑦ Stop                                         │
│              │               ┌──────────────────────────────┐               │
│              │               │ stop-gate:    测试跑了吗？    │               │
│              │               │              有 FIXME 吗？    │               │
│              │               │              git clean?       │               │
│              │               │ (不达标 → exit 2, agent 继续) │               │
│              │               └──────────────────────────────┘               │
│              │                                                              │
│              │  ┌─────────────────────────────────────────┐                 │
│              │  │ ⑧ SubagentStop                          │                 │
│              │  │ context-injector: 输出太短 → 阻断, 要求  │                 │
│              │  │                   补充细节               │                 │
│              │  └─────────────────────────────────────────┘                 │
│              │                                                              │
│              │  ┌─────────────────────────────────────────┐                 │
│              │  │ ⑨ PreCompact (上下文即将被压缩)          │                 │
│              │  │ compact-guard: 保存关键决策/任务/文件到   │                 │
│              │  │               外部存储                    │                 │
│              │  │               (刚开始可阻断自动压缩)      │                 │
│              │  └─────────────────────────────────────────┘                 │
│              │                                                              │
│              │  ┌─────────────────────────────────────────┐                 │
│              │  │ ⑩ PostCompact (压缩完成后)               │                 │
│              │  │ compact-guard: 注入恢复信息 (decisions,   │                 │
│              │  │               task, files, critical ctx)  │                 │
│              │  └─────────────────────────────────────────┘                 │
│              │                                                              │
└──────────────┴──────────────────────────────────────────────────────────────┘
```

## Hook 能力 × Harness 实现矩阵

| Hook 能力 | 对应事件 | Harness 实现 | 状态 |
|-----------|---------|-------------|------|
| **阻断执行** (exit 2) | PreToolUse | safety-guard, pivot-gate | ✅ |
| **阻断下轮推理** (exit 2) | PostToolBatch | loop-breaker, pivot-gate | ✅ |
| **阻断停止** (exit 2) | Stop | stop-gate | ✅ |
| **阻断 subagent 停止** (exit 2) | SubagentStop | context-injector | ✅ |
| **阻断压缩** (exit 2) | PreCompact | compact-guard | ✅ |
| **替换 tool 输出** (updatedToolOutput) | PostToolUse | context-filter | ✅ |
| **修改 tool 输入** (updatedInput) | PreToolUse | input-modifier | ✅ |
| **注入上下文** (additionalContext) | SessionStart | context-injector | ✅ |
| **注入上下文** (additionalContext) | PostToolUseFailure | context-injector | ✅ |
| **注入上下文** (additionalContext) | PostToolBatch | context-injector | ✅ |
| **注入上下文** (additionalContext) | PostCompact | compact-guard | ✅ |
| **旁路状态采集** (exit 0, write file) | PostToolUse | stop-gate-tracker, compact-collector | ✅ |

## 所有 Harness 及其 Hook 覆盖

| Harness | 域 | Hook 事件 | 能力 | 测试数 |
|---------|---|----------|------|--------|
| context-filter | Context | PostToolUse | 替换输出 | 5 scenarios |
| input-modifier | Context+Safety | PreToolUse | 修改参数 | 11 scenarios |
| compact-guard | Context | PreCompact + PostCompact + PostToolUse(collector) | 阻断压缩 + 注入恢复 | 7 scenarios |
| context-injector | Flow+Quality | SessionStart + PostToolUseFailure + PostToolBatch + SubagentStop | 注入上下文 + 阻断subagent | 8 scenarios |
| safety-guard | Safety | PreToolUse | 阻断 | 30 scenarios |
| pivot-gate | Flow | PostToolUse + (PreToolUse planned) | 替换输出(暂停) | 6 scenarios |
| loop-breaker | Flow | PostToolBatch | 阻断下轮推理 | 6 scenarios |
| stop-gate | Quality | Stop + PostToolUse(tracker) | 阻断停止 + 采集状态 | 6 scenarios |

## Claude Code settings.json 完整配置示例

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|compact",
        "hooks": [{"type": "command", "command": "python3 .hooks/context_injector.py"}]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash|Edit|Write",
        "hooks": [
          {"type": "command", "command": "python3 .hooks/safety_guard.py"},
          {"type": "command", "command": "python3 .hooks/input_modifier.py"}
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "python3 .hooks/context_filter.py"}]
      },
      {
        "matcher": "Bash|Edit|Write",
        "hooks": [
          {"type": "command", "command": "python3 .hooks/stop_gate_tracker.py"},
          {"type": "command", "command": "python3 .hooks/compact_guard_collector.py"}
        ]
      }
    ],
    "PostToolUseFailure": [
      {
        "matcher": "",
        "hooks": [{"type": "command", "command": "python3 .hooks/context_injector.py"}]
      }
    ],
    "PostToolBatch": [
      {
        "hooks": [
          {"type": "command", "command": "python3 .hooks/loop_breaker.py"},
          {"type": "command", "command": "python3 .hooks/context_injector.py"}
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [{"type": "command", "command": "python3 .hooks/stop_gate.py"}]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [{"type": "command", "command": "python3 .hooks/context_injector.py"}]
      }
    ],
    "PreCompact": [
      {
        "hooks": [{"type": "command", "command": "python3 .hooks/compact_guard.py"}]
      }
    ],
    "PostCompact": [
      {
        "hooks": [{"type": "command", "command": "python3 .hooks/compact_guard.py"}]
      }
    ]
  }
}
```

## 开放问题

1. **性能**: 每个 hook fork 新 Python 进程 (~50ms)。全配置下一次 tool call 触发 3-4 个 hook。考虑 daemon 模式或合并脚本。
2. **hook 执行顺序**: 同一事件多个 hooks 按数组顺序执行。safety-guard 必须在 input-modifier 之前（先判断是否阻断，再决定是否修改）。
3. **状态一致性**: 多个 harness 共享 `~/.agent-harness/state/`，并行 tool 调用时可能竞态。当前用文件锁 OK，高频场景需 sqlite。
4. **平台降级**: Kiro/Cursor 不支持大部分 hook 能力。降级方案：MCP Server 包装 + steering 软约束。
