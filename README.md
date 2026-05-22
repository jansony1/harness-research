# Harness Research

LLM Coding Agent 行为治理框架 — 通过 Claude Code hook 机制对 agent 执行全流程进行拦截、过滤和控制。

## 执行链路 & 拦截点

```
User Input
    │
    ▼
[UserPromptSubmit] ─── context-injector: 注入状态提醒
    │
    ▼
LLM 推理 → 生成 tool call(s)
    │
    ▼
[PreToolUse] ─────── safety-guard: 阻断危险操作
                      input-modifier: 篡改参数 (--dry-run, timeout, limit)
    │
    ▼
Tool 执行
    │
    ├── 成功 → [PostToolUse] ── context-filter: 过滤/截断输出
    │                            stop-gate-tracker: 采集测试状态
    │                            compact-guard-collector: 收集记忆标记
    │
    └── 失败 → [PostToolUseFailure] ── context-injector: 失败累积警告
    │
    ▼
[PostToolBatch] ──── loop-breaker: 检测循环 → 阻断下轮推理
                      context-injector: 每 N 批注入 checkpoint
    │
    ▼
LLM 决定停止?
    │
    ▼
[Stop] ──────────── stop-gate: 测试跑了吗？FIXME？→ 阻断
    │
[PreCompact] ─────── compact-guard: 保存关键决策，阻断过早压缩
[PostCompact] ────── compact-guard: 注入恢复信息
```

## Harness 列表

| Harness | Hook 事件 | 能力 | 测试 |
|---------|----------|------|------|
| [context-filter](./context-filter/) | PostToolUse | 替换输出（日志/JSON/测试/通用截断） | 5 |
| [input-modifier](./input-modifier/) | PreToolUse | 修改参数（dry-run/timeout/limit） | 11 |
| [safety-guard](./safety-guard/) | PreToolUse | 阻断执行（git force/rm/creds/prod） | 30 |
| [pivot-gate](./pivot-gate/) | PostToolUse | 设计转向检测 → 暂停人工审核（打分系统） | 6 |
| [loop-breaker](./loop-breaker/) | PostToolBatch | 循环打转 → 阻断下轮推理 | 8 |
| [stop-gate](./stop-gate/) | Stop + PostToolUse | 停止前强制验证（测试/git/FIXME） | 6 |
| [context-injector](./context-injector/) | SessionStart + UserPromptSubmit + PostToolUseFailure + PostToolBatch + SubagentStop | 多时机上下文注入 + subagent 质量门禁 | 10 |
| [compact-guard](./compact-guard/) | PreCompact + PostCompact + PostToolUse | 记忆保护（类型分级 FIFO） | 7 |

**共计 8 个 harness，83 个测试场景。**

## 快速使用

```json
// .claude/settings.json — 最小配置（只启用 safety-guard）
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Edit|Write",
        "hooks": [{"type": "command", "command": "python3 path/to/safety_guard.py"}]
      }
    ]
  }
}
```

完整配置见 [FRAMEWORK.md](./FRAMEWORK.md)。

## 设计原则

1. **每个 harness 是独立的** — 可以单独使用，也可以组合
2. **通过文件系统共享状态** — `~/.agent-harness/state/`，hook 间通过 JSON 文件通信
3. **有界设计** — 所有累积型状态有 FIFO 上限，所有阻断有安全阀
4. **零依赖** — 纯 Python 标准库，无第三方包

## 目录结构

```
harness-research/
├── README.md
├── FRAMEWORK.md              # 完整链路图 + 能力矩阵 + 配置示例
├── shared/adapter.py         # 平台适配层（就绪待集成）
├── context-filter/           # PostToolUse 输出过滤
├── input-modifier/           # PreToolUse 参数修改
├── safety-guard/             # PreToolUse 阻断
├── pivot-gate/               # PostToolUse 转向检测（打分系统）
├── loop-breaker/             # PostToolBatch 循环熔断
├── stop-gate/                # Stop 质量门禁
├── context-injector/         # 多事件上下文注入
├── compact-guard/            # PreCompact+PostCompact 记忆保护
└── feedback/                 # 跨 agent 测试讨论记录
```
