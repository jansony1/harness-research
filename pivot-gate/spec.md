# Pivot Gate — 设计转向人工审核

## Problem

LLM coding agent 在遇到困难时会自行"换思路"——推翻之前的设计、切换实现方案、revert 大量代码。这种 pivot 往往是关键决策点，但默认情况下 agent 会静默执行，人类直到看到最终结果才发现方向变了。

## Goal

在 agent 即将 pivot（换思路/换设计）时，强制暂停，等待人工审核确认后再继续。

## Detection: 两层触发

### Layer 1: 自动检测（行为模式）

通过 PostToolUse hook 统计 session 内的行为信号，累积分数超过阈值时触发暂停。

| 信号 | 分数 | 检测方式 |
|------|------|---------|
| Bash 命令连续失败 N 次 | +N*2 | PostToolUse: exit code != 0 连续计数 |
| 执行 git checkout/git restore/git reset | +5 | PreToolUse: 匹配命令模式 |
| 删除刚创建的文件 | +4 | PostToolUse: 维护 session 文件变更记录，检测 rm 目标 |
| Edit 回退（new_string 接近之前某次 old_string） | +3 | PostToolUse: 维护 edit 历史 |
| 同一文件被修改超过 3 次 | +2 | PostToolUse: 计数 |
| Session 内 tool 调用总数超过阈值 | +1/超出调用 | PostToolUse: 累计计数 |

**触发阈值**: 分数 >= 8 时暂停。

### Layer 2: Agent 主动声明

通过 steering/rules 要求 agent 在以下情况必须执行一个特殊的"pause"动作：

- 准备推翻之前的设计方案
- 准备切换到完全不同的实现路径
- 发现当前方向有根本性问题需要重新思考
- 准备 revert 超过 20 行的改动

**Pause 机制**: Agent 执行一个特殊命令（如 `echo "PIVOT: <reason>"`），PreToolUse 或 PostToolUse hook 检测到这个信号后触发暂停。

## Pause 行为

触发暂停时：

1. Hook 输出诊断信息（触发原因、当前 session 统计）
2. Hook 以 exit code 2 退出（PreToolUse）或返回替换文本要求停止（PostToolUse）
3. Agent 收到中断信号，停止执行
4. 人类审核：
   - 查看 agent 的意图和当前进度
   - 决定：继续 / 修正方向 / 完全终止
5. 人类输入后 agent 恢复

## State Management

Hook 需要维护 session 级别的状态（跨多次 tool 调用）：

```
~/.pivot-gate/
  session.json        # 当前 session 状态
    {
      "session_id": "...",
      "started_at": "...",
      "tool_calls": 0,
      "consecutive_failures": 0,
      "score": 0,
      "files_created": [],
      "files_modified": {"path": count},
      "edit_history": [...],
      "paused": false,
      "pause_history": [...]
    }
```

Session 通过环境变量 `CLAUDE_SESSION_ID` 或文件锁标识。
超过 30 分钟无活动视为 session 过期。

## Integration

| 平台 | Layer 1 (自动检测) | Layer 2 (主动声明) |
|------|-------------------|-------------------|
| Claude Code | PostToolUse hook 统计 + exit 2 拦截 | Steering (CLAUDE.md) + 检测 PIVOT echo |
| Kiro | PostToolUse hook 统计（observe only，无法拦截） | Steering (.kiro/steering/) + 检测 PIVOT echo |
| 通用 | 包装 shell executor 加入状态统计 | System prompt 注入规则 |

## Steering Template

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
