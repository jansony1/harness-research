# Context Filter MCP Server

平台无关的 MCP Server，为任何支持 MCP 的 coding agent 提供过滤后的 shell 执行能力。

## 快速开始

### 1. Claude Code

在项目的 `.claude/settings.json` 或 `~/.claude/settings.json` 中添加：

```json
{
  "mcpServers": {
    "context-filter": {
      "command": "python3",
      "args": ["/path/to/mcp-server/server.py"]
    }
  }
}
```

### 2. Kiro

在 `.kiro/settings/mcp.json` 中添加：

```json
{
  "mcpServers": {
    "context-filter": {
      "command": "python3",
      "args": ["/path/to/mcp-server/server.py"]
    }
  }
}
```

### 3. Cursor

在 `.cursor/mcp.json` 中添加：

```json
{
  "mcpServers": {
    "context-filter": {
      "command": "python3",
      "args": ["/path/to/mcp-server/server.py"]
    }
  }
}
```

### 4. VS Code (Copilot)

在 `.vscode/mcp.json` 中添加：

```json
{
  "servers": {
    "context-filter": {
      "command": "python3",
      "args": ["/path/to/mcp-server/server.py"]
    }
  }
}
```

## Tools

### `filtered_bash`

执行 shell 命令，自动过滤输出。

```
参数:
  command (string, required): 要执行的 shell 命令
  timeout (int, optional): 超时秒数，默认 120
  filter_mode (enum, optional): auto|log|test|json|truncate|none
```

使用场景：
- `filter_mode: "auto"` — 自动检测并应用最佳过滤（默认）
- `filter_mode: "log"` — 强制按日志过滤
- `filter_mode: "none"` — 不过滤，直接返回原始输出

### `filter_text`

对任意文本应用过滤（可用于后处理其他工具的输出）。

```
参数:
  text (string, required): 要过滤的文本
  filter_mode (enum, optional): auto|log|test|json|truncate
```

## 配合 Steering 使用

对于不支持 hook 修改 output 的平台（如 Kiro），可以在 steering/rules 中引导 agent 优先使用 `filtered_bash`：

```markdown
<!-- .kiro/steering/tool-usage.md -->
---
inclusion: always
---
# Tool Usage Rules

When executing shell commands that may produce large output (logs, test results, 
API calls, build output), prefer `filtered_bash` over raw shell execution.
This preserves context window budget for reasoning.
```

## 本地测试

```bash
# 发送一条 initialize + tools/list 请求
echo 'Content-Length: 56

{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}Content-Length: 51

{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | python3 server.py
```

## 无依赖

纯 Python 标准库实现，无第三方依赖。Python 3.10+ 即可运行。
