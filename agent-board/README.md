# Agent Board — Pixel Quest

像素风格的多 agent 协作看板。实时查看每个 coding agent 的状态、任务进度和通信日志。

## 启动

```bash
cd agent-board
python3 server.py          # http://localhost:8420
```

## 集成 Claude Code

在项目 `.claude/settings.json` 中添加：

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "",
        "hooks": [{"type": "command", "command": "python3 /path/to/agent-board/hooks/board_hook.py"}]
      }
    ],
    "PostToolBatch": [
      {
        "hooks": [{"type": "command", "command": "python3 /path/to/agent-board/hooks/board_hook.py"}]
      }
    ],
    "Stop": [
      {
        "hooks": [{"type": "command", "command": "python3 /path/to/agent-board/hooks/board_hook.py"}]
      }
    ]
  }
}
```

设置 agent 名称（多 agent 场景）：
```bash
export AGENT_BOARD_NAME="Claude-1"  # 默认 "Claude"
export AGENT_BOARD_STATE="/path/to/agent-board/state.json"
```

## 集成 Kiro

Kiro agent 配置 `.kiro/agents/your-agent.json`：
```json
{
  "hooks": {
    "postToolUse": [{"command": "python3 /path/to/agent-board/hooks/board_hook.py"}]
  }
}
```

## Agent 主动上报（CLAUDE.md 规则）

在项目 CLAUDE.md 中添加：

```markdown
## Board Reporting

When you reach a key milestone, report to the agent board:
  python3 /path/to/agent-board/board_cli.py log Claude "description" success
  python3 /path/to/agent-board/board_cli.py task move "task title" done

When changing direction or encountering a blocker:
  python3 /path/to/agent-board/board_cli.py status Claude blocked "reason"
```

## CLI 命令

```bash
# 状态更新
python3 board_cli.py status Claude working "Implementing feature" 50
python3 board_cli.py status Kiro blocked "Waiting for API" 30
python3 board_cli.py idle Claude

# 日志
python3 board_cli.py log Claude "Tests passing" success
python3 board_cli.py log Kiro "Hook test failed" error

# 任务管理
python3 board_cli.py task add "New feature" Claude high
python3 board_cli.py task move "New feature" progress
python3 board_cli.py task move "New feature" done
```

## 工作原理

```
Claude Code ──[PostToolUse hook]──▶ board_hook.py ──▶ state.json
Kiro        ──[postToolUse hook]──▶ board_hook.py ──▶ state.json
Agent (主动) ──[board_cli.py]────────────────────────▶ state.json
                                                          │
Browser ◀── server.py ◀── poll every 2s ──────────────────┘
```

## 数据格式 (state.json)

```json
{
  "agents": [
    {"name": "Claude", "status": "working|idle|blocked", "current_task": "...", "progress": 75}
  ],
  "tasks": [
    {"title": "...", "status": "planning|progress|done", "assignee": "Claude", "priority": "high|mid|low"}
  ],
  "messages": [
    {"time": "10:30", "agent": "Claude", "text": "...", "type": "success|error|\"\""}
  ]
}
```
