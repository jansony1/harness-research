# Agent Harness Framework — 全景设计

## 核心问题分类

LLM coding agent 在实际使用中的问题可以分为 5 类：

---

## 1. Context（上下文治理）

**问题**: Agent 的上下文窗口是有限资源，但 tool output 全量注入，导致关键信息被稀释、compaction 提前触发、成本膨胀。

| 场景 | Hook 点 | 能力 |
|------|---------|------|
| 大日志/大JSON过滤 | PostToolUse | 替换输出 |
| 长文件读取只保留相关段 | PostToolUse(Read) | 替换输出 |
| Compaction 前保存关键状态 | PreCompact | 注入上下文 |
| Compaction 后恢复关键记忆 | PostCompact / SessionStart(resume) | 注入上下文 |
| Subagent 返回结果太长 | PostToolUse(Agent) | 替换输出 |
| 重复 tool 调用去重 | PreToolUse | 阻断+返回缓存 |

**已实现**: context-filter (PostToolUse)

---

## 2. Flow（流程控制）

**问题**: Agent 会自行决定方向——换思路、放弃、循环打转、跳过步骤。人类失去控制。

| 场景 | Hook 点 | 能力 |
|------|---------|------|
| 设计转向 → 暂停审核 | PreToolUse + PostToolBatch | 阻断 |
| 连续失败 → 暂停 | PostToolUseFailure + PostToolBatch | 阻断 |
| Agent 要放弃/结束 → 拦截 | Stop | 阻断停止 |
| Agent 循环打转 (>N 次同类操作) | PostToolBatch | 阻断 |
| Subagent 质量不够 → 继续 | SubagentStop | 阻断停止 |
| 新 user prompt → 重置状态 | UserPromptSubmit | 注入上下文 |
| 限制总 tool 调用数（成本控制） | PostToolBatch | 阻断 |
| 强制 checkpoint（每 N 步总结进度） | PostToolBatch | 注入上下文 |

**已实现**: pivot-gate (PostToolUse only, 待重构)

---

## 3. Safety（安全防护）

**问题**: Agent 可能执行危险操作——泄露密钥、删除数据、推送到 production、修改共享基础设施。

| 场景 | Hook 点 | 能力 |
|------|---------|------|
| 拦截 `git push --force` | PreToolUse(Bash) | 阻断 |
| 拦截 `rm -rf /` 等破坏性命令 | PreToolUse(Bash) | 阻断 |
| 输出含密钥/token → 拦截 | PostToolUse | 替换输出 |
| 禁止修改特定文件 (.env, CI config) | PreToolUse(Edit\|Write) | 阻断 |
| 禁止访问特定目录 | PreToolUse(Read\|Bash) | 阻断 |
| 网络请求白名单 | PreToolUse(WebFetch) | 阻断 |
| 文件变更审计日志 | PostToolUse(Edit\|Write\|Bash) | 旁路记录 |
| 阻止 agent 自行修改 settings | ConfigChange | 阻断 |
| 敏感操作需要二次确认 | PermissionRequest | 自定义逻辑 |

---

## 4. Quality（质量保障）

**问题**: Agent 可能产出低质量代码——不测试就收工、忽略 lint 错误、跳过 edge case。

| 场景 | Hook 点 | 能力 |
|------|---------|------|
| 停止前必须跑测试 | Stop | 阻断停止 + 注入 "run tests first" |
| 停止前检查是否有未 stage 的改动 | Stop | 阻断停止 |
| Subagent 输出不符合格式要求 | SubagentStop | 阻断 + 注入反馈 |
| Task 完成前验证通过条件 | TaskCompleted | 阻断完成 |
| Edit 后自动 lint check | PostToolUse(Edit) | 注入 lint 结果到上下文 |
| 代码写入后自动检测安全漏洞 | PostToolUse(Write\|Edit) | 注入上下文 |
| PR 创建前强制 review checklist | PreToolUse(Bash: gh pr create) | 阻断 |

---

## 5. Observability（可观测性）

**问题**: Agent 的执行过程是黑箱——不知道花了多少 token、哪里卡住了、为什么做了某个决定。

| 场景 | Hook 点 | 能力 |
|------|---------|------|
| 记录所有 tool 调用到日志 | PostToolUse + PostToolUseFailure | 旁路记录 |
| Session 耗时/调用数统计 | Stop | 生成报告 |
| 失败原因分析 | StopFailure | 发送告警 |
| Token 消耗追踪 | PostToolBatch | 累计统计 |
| Notification 转发 (Slack/webhook) | Notification | 旁路转发 |
| 哪些 CLAUDE.md 被加载了 | InstructionsLoaded | 审计 |
| Agent 决策树可视化 | PreToolUse + PostToolUse | 记录序列 |

---

## Hook 事件的能力矩阵

按"能做什么"重新分类 hook 点：

### 可以阻断的 (exit 2 = block)

| Hook | 阻断的是什么 |
|------|-------------|
| UserPromptSubmit | 用户输入不被处理 |
| PreToolUse | Tool 不执行 |
| PostToolBatch | 下一轮 LLM 推理不发生 |
| Stop | Agent 不停止（被迫继续） |
| SubagentStop | Subagent 不停止（被迫继续） |
| TaskCompleted | Task 不被标记完成 |
| TaskCreated | Task 不被创建 |
| ConfigChange | 配置变更不生效 |
| PreCompact | Compaction 不发生 |

### 可以修改数据的

| Hook | 能修改什么 |
|------|-----------|
| PreToolUse | tool 参数 (updatedInput) |
| PostToolUse | tool 输出 (updatedToolOutput) |
| PermissionRequest | 权限决策 |
| ElicitationResult | MCP 表单结果 |

### 只能注入上下文的

| Hook | 注入给谁 |
|------|---------|
| SessionStart | agent 初始上下文 |
| PostToolUseFailure | agent 上下文 |
| SubagentStart | subagent 上下文 |
| CwdChanged | 环境变量 |
| FileChanged | 环境变量 |

### 只能旁路观察的

| Hook | 用途 |
|------|------|
| Notification | 转发 |
| InstructionsLoaded | 审计 |
| StopFailure | 告警 |
| WorktreeRemove | 清理 |
| PostCompact | 记录 |

---

## 实现优先级

按 ROI (问题严重性 × 实现难度) 排序：

### P0 — 立即有价值

| Harness | 核心 Hook | 解决的问题 |
|---------|----------|-----------|
| **context-filter** | PostToolUse | 上下文膨胀 → 质量下降 + 成本升高 |
| **safety-guard** | PreToolUse | 破坏性操作 → 不可逆损失 |
| **stop-gate** | Stop + SubagentStop | Agent 过早放弃 / 没做完就停了 |

### P1 — 显著改善体验

| Harness | 核心 Hook | 解决的问题 |
|---------|----------|-----------|
| **pivot-gate** | PreToolUse + PostToolBatch + PostToolUseFailure | 方向错误浪费大量 token |
| **loop-breaker** | PostToolBatch | 循环打转不收敛 |
| **quality-gate** | Stop + TaskCompleted | 代码质量不达标就交付 |

### P2 — 运营级需求

| Harness | 核心 Hook | 解决的问题 |
|---------|----------|-----------|
| **session-logger** | 全事件 | 黑箱 → 可审计可追溯 |
| **cost-limiter** | PostToolBatch | 预算超支 |
| **compact-guard** | PreCompact + PostCompact | Compaction 丢失关键信息 |

---

## 共享基础设施

所有 harness 共享：

```
~/.agent-harness/
  state/
    {session_id}.json     # session 级状态（计分器、调用历史）
  config/
    rules.yaml            # 统一配置（阈值、白名单、行为规则）
  logs/
    {date}.jsonl          # 事件流日志
  engine.py               # 共享的状态管理 + 打分引擎
```

每个 harness 是一个 "plugin"，注册自己关心的事件和处理逻辑：

```python
# 伪代码
class PivotGate(HarnessPlugin):
    events = ["PreToolUse", "PostToolUseFailure", "PostToolBatch"]
    
    def on_pre_tool_use(self, data, state):
        if is_destructive(data.tool_input):
            return Block("destructive operation detected, please confirm")
    
    def on_post_tool_failure(self, data, state):
        state.score += 3
    
    def on_post_tool_batch(self, data, state):
        if state.score >= THRESHOLD:
            return Block("pivot detected, human review required")
```

---

## 开放问题

1. **单进程 vs 多进程**: 每个 hook 事件 fork 新进程 → Python 启动开销 ~50ms。28 个 hook 点全挂的话会拖慢 agent。是否应该做成一个 daemon？
2. **跨 session 状态**: 有些信号跨 session 才有意义（比如 "这个 bug 修了 3 个 session 都没修好"）。用什么存储？
3. **hook 之间的优先级**: context-filter 和 pivot-gate 都挂在 PostToolUse 上，谁先执行？能否保证顺序？
4. **Kiro/Cursor 兼容**: 它们的 hook 能力是 Claude Code 的子集，如何做 graceful degradation？
