---
status: open
action_items: 6
resolved_items: 0
---

# Harness Research — Kiro 实测反馈

> 测试日期: 2026-05-22  
> 测试环境: Kiro CLI (macOS, Auto model)  
> 测试方法: 单元测试 + Hook 协议模拟 + MCP Server 端到端验证

---

## 评估原则

- ✅ **正向**: 能在 Kiro 下实现（含替代方案）/ 设计思路行之有效值得借鉴
- ❌ **负向 (Kiro 不适配)**: 设计本身合理，Kiro 当前无法实现且无替代
- ❌ **负向 (设计问题)**: 设计本身存在问题，不推荐

---

## 逐模块评估

### 1. safety-guard — PreToolUse 破坏性命令拦截

**评估: ✅ 正向 — Kiro 完全支持，且有多层实现路径**

| 维度 | 说明 |
|------|------|
| Kiro 兼容 | ✅ PreToolUse exit 2 阻断完全支持 |
| 设计价值 | 高 — 在执行前拦截不可逆操作是最基本的安全需求 |
| 实测结果 | 6/6 场景通过 |

**适配成本**: 极低，仅需工具名映射 (`Bash`→`shell`/`execute_bash`, `Write`→`fs_write`)

**实测输出**:
```
git push --force → exit 2, STDERR 返回 LLM: "[BLOCKED] force push can overwrite remote history"
rm -rf /usr/local → exit 2, STDERR: "[BLOCKED] destructive filesystem operation"
cat .env → exit 2, STDERR: "[BLOCKED] credential exposure risk"
ls -la → exit 0 (放行)
```

**补充: Kiro 原生替代方案**

Kiro 的 `toolsSettings` 已内置部分能力：
```json
{
  "toolsSettings": {
    "execute_bash": {
      "allowedCommands": ["git status", "cargo test"]
    },
    "fs_write": {
      "allowedPaths": ["src/**"],
      "deniedPaths": ["/etc/**", "**/.env"]
    }
  }
}
```

但 safety-guard hook 的优势在于：
- **正则匹配**比白名单更灵活（如检测 `curl|bash` 管道模式）
- **分类拦截信息**让 LLM 理解为什么被拒绝，可以向用户解释
- **可组合**：toolsSettings 做粗粒度控制，hook 做细粒度策略

**结论**: 两者互补，建议同时使用。

---

### 2. input-modifier — PreToolUse 参数透明修改

**评估: ✅ 正向 (设计优秀) — Kiro 有可行降级方案**

| 维度 | 说明 |
|------|------|
| Kiro 兼容 | ❌ 不支持 `updatedInput`，但有降级路径 |
| 设计价值 | 高 — "不阻断但加防护"是比硬拦截更优雅的安全策略 |

**为什么设计好**: 
- `git push` → 自动加 `--dry-run`，让 agent 先看结果再决定
- `rm -rf src/` → 转为 `find ... | head -20` 预览
- 长命令自动加 `timeout`，防止挂死
- 大文件读取自动加 `limit`，保护上下文窗口

**Kiro 降级方案（实际可行）**:

方案 A — **exit 2 阻断 + STDERR 建议**:
```bash
# hook 脚本
echo "[SUGGESTION] 建议使用: git push --dry-run origin main (先预览再真推)" >&2
exit 2
```
LLM 收到 STDERR 后会理解建议并重新发起修改后的命令。实测 Kiro 的 LLM 能正确响应这类引导。

方案 B — **MCP Server 包装**（类似 context-filter 的 filtered_bash）:
提供 `safe_bash` MCP tool，内部自动注入 --dry-run/timeout 等参数。

**方案 A 的效果**: 不如原版透明（agent 会感知到被拒绝），但实际效果接近——LLM 会按建议重试。

---

### 3. context-filter — Tool 输出分级过滤

**评估: ✅ 正向 — MCP Server 在 Kiro 完全可用，设计解决真实痛点**

| 维度 | 说明 |
|------|------|
| Kiro 兼容 | Hook 方式 ❌ / MCP Server 方式 ✅ |
| 设计价值 | 极高 — 上下文膨胀是所有 coding agent 的核心问题 |

**实测 MCP Server**:
```
Initialize: context-filter v1.0.0 ✅
filtered_bash("echo hello"): 正常输出 ✅
filter_text(101行日志): 101行 → 155字符 (99.8%压缩) ✅
```

**Kiro 配置**:
```json
{
  "mcpServers": {
    "context-filter": {
      "command": "python3",
      "args": ["/path/to/context-filter/mcp-server/server.py"]
    }
  }
}
```

**如何让 agent 优先使用 filtered_bash**:

通过 agent `prompt` 引导：
```json
{
  "prompt": "当执行可能产生大量输出的命令（日志查看、测试运行、JSON API 调用）时，优先使用 @context-filter/filtered_bash 而非内置 shell。"
}
```

或更激进：通过 `tools` 字段不包含 `execute_bash`，只暴露 MCP 的 filtered_bash。但这会限制其他场景。

**局限**: 无法像 PostToolUse hook 那样透明拦截所有输出。Agent 需要"配合"。

---

### 4. loop-breaker — 循环打转检测与熔断

**评估: ✅ 正向 (设计优秀) — Kiro 有部分替代路径**

| 维度 | 说明 |
|------|------|
| Kiro 兼容 | ❌ 无 PostToolBatch 事件，但可用 postToolUse + userPromptSubmit 组合 |
| 设计价值 | 高 — 循环打转是 agent 最常见的失败模式之一 |

**为什么设计好**:
- 4 层检测信号：相同命令重复 / 相似命令重复 / 同文件反复编辑 / ABAB 交替模式
- 有 session budget 上限，防止无限消耗
- 检测到后给出明确指导

**Kiro 替代方案**:

1. **postToolUse hook 累积状态**：每次 tool 执行后记录到文件，虽然不能阻断下轮推理，但可以在 STDERR 输出警告（用户可见）
2. **userPromptSubmit hook 检查**：每次用户发消息时检查累积状态，STDOUT 注入上下文警告 agent。这是一个有效的检查点——如果 agent 在循环中，用户的下一次交互会触发检测
3. **preToolUse hook 阻断**：在 postToolUse 中记录状态，在下一次 preToolUse 时检查是否循环并 exit 2 阻断

**方案 3 最接近原版效果**：
```
postToolUse: 记录命令到状态文件（exit 0，不影响执行）
preToolUse: 读取状态文件，检测循环模式 → exit 2 阻断
```

这样虽然不是在"批次完成后"阻断，而是在"下一个工具调用前"阻断，但实际效果等价。

**结论**: 通过 postToolUse(记录) + preToolUse(检测+阻断) 组合，**可以在 Kiro 下实现 loop-breaker 的核心功能**。

---

### 5. stop-gate — 停止前质量门禁

**评估: ✅ 正向 (设计优秀) + ❌ Kiro 不适配（无完美替代）**

| 维度 | 说明 |
|------|------|
| Kiro 兼容 | ❌ stop hook 不支持 exit 2 阻断 |
| 设计价值 | 高 — "不测试就交付"是 agent 质量问题的根源 |

**为什么设计好**:
- 检查 3 个维度：测试是否跑过且通过 / git 是否有未提交变更 / 代码中是否有 TODO/FIXME
- 有安全阀（连续阻断 3 次后放行），避免死锁
- 强制 agent 在交付前验证质量

**Kiro 替代方案（效果有限）**:

1. **stop hook 输出警告**：虽然不能阻断，但 STDERR 会显示给用户。用户看到"测试未跑"的警告后可以手动要求 agent 继续
2. **prompt 软约束**：在 agent prompt 中写入"完成任务前必须运行测试并确认通过"。Kiro 的内置行为已有类似 verification 指导
3. **steering 文件**：`.kiro/steering/quality.md` 中定义质量规则，作为持久上下文

**为什么这些替代不够好**: 软约束依赖 LLM 自觉遵守，没有硬性保证。stop-gate 的价值恰恰在于"不管 LLM 怎么想，不达标就不让停"。这是 Kiro 当前无法实现的。

**建议**: 这是 Kiro 最值得增加的能力之一。Stop hook exit 2 阻断的实现成本低（已有事件，只需改 exit code 语义），但价值极高。

---

### 6. compact-guard — 上下文压缩记忆保护

**评估: ✅ 正向 (设计优秀) — Kiro 有替代路径（Knowledge + Resources）**

| 维度 | 说明 |
|------|------|
| Kiro 兼容 | ❌ 无 PreCompact/PostCompact 事件，但有替代机制 |
| 设计价值 | 高 — 压缩后丢失关键决策是长 session 的核心痛点 |

**Kiro 替代方案**:

1. **Knowledge Base 持久化**：Kiro 的 Knowledge Management 支持语义搜索的持久化存储。Agent 可以在关键决策点主动将信息写入 knowledge base，压缩后通过搜索恢复
   
2. **Resources 文件**：将关键决策写入文件（如 `.kiro/session-memory.md`），通过 agent resources 配置持久加载：
   ```json
   { "resources": ["file://.kiro/session-memory.md"] }
   ```
   这个文件会在每次上下文重建时被加载，等效于 PostCompact 注入。

3. **agentSpawn hook**：agent 激活时读取持久化的状态文件，STDOUT 注入上下文。如果 Kiro 在 compact 后重新激活 agent，这个 hook 会触发。

**方案 2 最实用**：agent 在做重要决策时写入 session-memory 文件，该文件作为 resource 始终在上下文中。不需要 hook 事件，利用 Kiro 已有能力。

**与原版的差异**: 原版是自动的（hook 自动保存/恢复），替代方案需要 agent 主动写入。可通过 prompt 引导 agent 在关键节点写入记忆文件。

---

### 7. context-injector — 多事件上下文注入

**评估: ⚠️ 部分正向 — 核心功能可通过 Kiro 组合实现**

| 维度 | 说明 |
|------|------|
| Kiro 兼容 | agentSpawn ✅ / userPromptSubmit ✅ / 其他 ❌ |
| 设计价值 | 中高 — 思路好但部分场景价值存疑 |

**Kiro 可实现的部分**:

| 原始功能 | Kiro 替代 | 效果 |
|---------|----------|------|
| SessionStart 注入规则 | agentSpawn hook (STDOUT→上下文) | ✅ 等效 |
| 失败累积警告 | postToolUse 记录 + preToolUse 检查 | ⚠️ 可实现但不如原版优雅 |
| Checkpoint 注入 | userPromptSubmit hook (STDOUT→上下文) | ⚠️ 触发时机不同（用户发消息时而非每 N 批） |

**存疑部分**:
- **SubagentStop 输出长度检查**: 用输出字符数（<50）判断 subagent 质量过于粗暴。短输出不一定质量差（如"已完成，无错误"），长输出不一定质量好。**这是设计问题，不是平台问题。**

---

### 8. pivot-gate — 设计转向检测

**评估: ⚠️ 设计有争议 — 部分可在 Kiro 实现但 ROI 存疑**

| 维度 | 说明 |
|------|------|
| Kiro 兼容 | 核心检测逻辑可通过 postToolUse(记录) + preToolUse(阻断) 实现 |
| 设计价值 | 中 — 思路有价值但实现有过度工程化倾向 |

**正向**:
- 检测 agent "悄悄换方向"是有价值的需求
- 强制暂停让人类审核，避免 agent 自作主张

**设计问题（非平台问题）**:
- 评分系统阈值是经验值，不同项目差异大，需要大量调优
- 与 loop-breaker 功能重叠（都检测重复/失败模式），职责边界不清晰
- Agent 正常的"尝试 → 失败 → 调整"工作流可能频繁触发误报
- 建议：**合并到 loop-breaker 中**作为一个检测维度，而非独立模块

---

## 综合评估总表

| 模块 | 设计评价 | Kiro 可用性 | 综合判定 |
|------|---------|------------|---------|
| safety-guard | ⭐⭐⭐ 优秀 | ✅ 直接可用 + toolsSettings 互补 | ✅ 正向 |
| context-filter (MCP) | ⭐⭐⭐ 优秀 | ✅ MCP Server 完全可用 | ✅ 正向 |
| input-modifier | ⭐⭐⭐ 优秀 | ⚠️ exit 2 + STDERR 建议降级 | ✅ 正向（降级可用） |
| loop-breaker | ⭐⭐⭐ 优秀 | ⚠️ postToolUse记录 + preToolUse阻断 | ✅ 正向（组合实现） |
| compact-guard | ⭐⭐⭐ 优秀 | ⚠️ Resources文件 + Knowledge 替代 | ✅ 正向（替代方案） |
| stop-gate | ⭐⭐⭐ 优秀 | ❌ 无硬性替代 | ❌ Kiro 不适配 |
| context-injector | ⭐⭐ 良好 | ⚠️ agentSpawn + userPromptSubmit | ⚠️ 部分正向 |
| pivot-gate | ⭐⭐ 有争议 | ⚠️ 可实现但 ROI 低 | ⚠️ 建议合并到 loop-breaker |

---

## 补充建议

### 1. Kiro 独有优势可以反哺框架设计

Harness 框架是为 Claude Code 设计的，但 Kiro 有一些 Claude Code 没有的能力：

| Kiro 能力 | 可用于 | 说明 |
|-----------|--------|------|
| `userPromptSubmit` hook (STDOUT→上下文) | 状态检查点 | 每次用户交互时注入累积状态，比 PostToolBatch 更自然 |
| `toolsSettings.deniedPaths` | 路径保护 | 内置能力，不需要 hook 脚本 |
| Knowledge Base (语义搜索) | 记忆保护 | 比文件持久化更强大，支持跨 session |
| Skills (按需加载) | 上下文管理 | 只在需要时加载，天然解决上下文膨胀 |
| Agent prompt (系统提示) | 软约束 | 配合 hook 硬约束形成双层防护 |
| `max_output_size` (hook 配置) | 输出截断 | 内置的输出大小限制，部分替代 context-filter |

### 2. 建议的 Kiro 最佳实践架构

```
┌─────────────────────────────────────────────────────┐
│ Agent Config (.kiro/agents/harness-agent.json)       │
├─────────────────────────────────────────────────────┤
│ prompt: 质量规则 + 行为约束（软约束层）              │
│ toolsSettings: deniedPaths + allowedCommands（内置层）│
│ hooks:                                               │
│   agentSpawn: 注入 session 规则 + 恢复记忆           │
│   userPromptSubmit: 状态检查 + 累积警告              │
│   preToolUse: safety-guard + loop-breaker 阻断       │
│   postToolUse: 状态记录（为 preToolUse 提供数据）    │
│   stop: 质量警告（软提醒，无法硬阻断）              │
│ mcpServers:                                          │
│   context-filter: filtered_bash + filter_text        │
│ resources:                                           │
│   file://.kiro/session-memory.md（记忆持久化）       │
└─────────────────────────────────────────────────────┘
```

### 3. 唯一真正无法替代的能力

经过完整分析，**只有 stop-gate 的"硬阻断停止"在 Kiro 下完全无法实现**。其他模块都有可行的替代路径（虽然有些效果打折）。

建议向 Kiro 团队反馈的优先级调整为：
1. **Stop hook exit 2 阻断** — 唯一无替代的能力，实现成本低，价值最高
2. **PreToolUse updatedInput** — 有降级方案但体验差距大，值得原生支持
3. 其他能力（PostToolBatch、PostToolUse updatedOutput、Compact 事件）有替代路径，优先级降低

### 4. 框架本身的改进建议

| 建议 | 原因 |
|------|------|
| 合并 pivot-gate 到 loop-breaker | 功能重叠，减少维护成本和误报 |
| context-injector SubagentStop 改用语义判断 | 字符数阈值过于粗暴 |
| 增加平台适配层 | 当前代码硬编码 Claude Code 的 tool_name 和输出格式，应抽象为适配器 |
| 增加 Kiro agent 配置示例 | 降低 Kiro 用户的使用门槛 |

---

## 实测数据附录

### 单元测试（代码逻辑验证）

| 模块 | 测试数 | 结果 |
|------|--------|------|
| safety-guard | 30 | ✅ All passed |
| input-modifier | 11 | ✅ All passed |
| loop-breaker | 6 | ✅ All passed |
| pivot-gate | 6 | ✅ All passed |
| compact-guard | 7 | ✅ All passed |
| stop-gate | 6 | ✅ All passed |
| context-injector | 8 | ✅ All passed |

### Kiro Hook 协议集成测试

```
PreToolUse exit 2 阻断:      ✅ 正确阻断，STDERR 返回 LLM
PreToolUse updatedInput:      ❌ STDOUT 被捕获但不解析为参数修改
PostToolUse 状态记录:         ✅ exit 0 正常，可写文件记录状态
Stop exit 2 阻断:            ❌ 仅显示警告，不阻断停止
agentSpawn STDOUT→上下文:     ✅ 文档确认 STDOUT 注入 agent 上下文
userPromptSubmit STDOUT→上下文: ✅ 文档确认输出加入对话上下文
MCP Server (context-filter):  ✅ 初始化/tools/call 全部正常
```

### 测试脚本位置

```
feedback/test_hooks/safety_guard_kiro.sh    — 适配 Kiro 的 safety-guard
feedback/test_hooks/input_modifier_kiro.py  — updatedInput 测试
feedback/test_hooks/stop_gate_kiro.sh       — stop 阻断测试
.kiro/agents/harness-test.json              — Kiro agent 配置示例
```
