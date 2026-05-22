# Pivot Gate — 设计转向人工审核

当 LLM coding agent 遇到困难要换思路时，强制暂停等待人工审核。

## 为什么需要

Agent 会在以下情况静默 pivot：
- 连续几次修复失败后推翻整个方案
- 发现设计问题后 revert 大量代码重来
- 在两个方案间反复摇摆消耗 token

这些是关键决策点，人类应该参与。

## 两层检测

### Layer 1: 自动检测（行为信号累积打分）

| 信号 | 分数 |
|------|------|
| 连续 Bash 失败（每次） | +2 |
| 执行 git checkout/restore/reset | +5 |
| 删除刚创建的文件 | +4 |
| 同一文件被修改 3+ 次 | +2 |
| Tool 调用超过 30 次 | +1/次 |

分数累积 >= 8 时触发暂停。

### Layer 2: Agent 主动声明

在 steering 中要求 agent 换思路前执行：
```bash
echo "PIVOT: <one-line reason>"
```

Hook 检测到 `PIVOT:` 关键词立即触发暂停（直接 +8 分到阈值）。

## 安装

### Claude Code

```json
// .claude/settings.json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/pivot_gate.py"
          }
        ]
      }
    ]
  }
}
```

注意 `matcher` 为空字符串表示匹配所有工具（需要监控 Bash, Edit, Write）。

### Steering 配置

将以下内容加入 `CLAUDE.md` 或 `.kiro/steering/pivot.md`：

```markdown
## Pivot Protocol

When you are about to:
- Abandon your current approach and try a fundamentally different one
- Revert more than 20 lines of changes you just made
- Conclude that the current design has a fundamental flaw

You MUST first execute: `echo "PIVOT: <one-line reason>"`

Do NOT proceed with the new approach until you receive human confirmation.
This is not optional — silent pivots waste context and may go in the wrong direction.
```

## 状态文件

Session 状态保存在 `~/.pivot-gate/session.json`，30 分钟无活动自动过期。

```bash
# 查看当前 session 状态
cat ~/.pivot-gate/session.json | python3 -m json.tool

# 手动重置（强制新 session）
rm ~/.pivot-gate/session.json
```

## 触发时的输出

```
╔══════════════════════════════════════════════════════╗
║  PIVOT GATE — Human Review Required                  ║
╠══════════════════════════════════════════════════════╣
║  The agent appears to be changing approach.           ║
║  Score: 8/8 (threshold reached)                      ║
║  Trigger signals:                                    ║
║    - consecutive failures: 4 (+2)                    ║
║    - revert command: git checkout -- src/main.py (+5)║
╚══════════════════════════════════════════════════════╝
```

## 配合 Context Filter 使用

推荐同时使用 [context-filter](../context-filter/)，这样：
1. Context filter 减少噪音 → agent 更少犯错 → 更少触发 pivot
2. Pivot gate 暂停时的诊断信息不会被 context filter 截断（因为不匹配日志/测试模式）

## 局限性

- Layer 2 依赖 agent 遵守 steering 规则（LLM 不保证 100% 遵守）
- Layer 1 的阈值需要根据项目类型调优（探索性任务可能需要更高阈值）
- Kiro 的 PostToolUse hook 目前无法拦截/替换输出，只能观察（需等 issue #7417）
- 状态文件是本地的，多 session 并行时可能冲突
