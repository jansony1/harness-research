# Context Filter — Platform-Agnostic Specification

## Problem

LLM agent 的 tool result 全量注入上下文窗口，导致：
- 80-99% 的 token 是噪音（passing tests, INFO logs, unused JSON fields）
- 加速触发 context compaction，丢失有价值的对话历史
- 增加推理成本（按 token 计费）

## Solution

在 tool output 到达 LLM 之前，应用分级过滤管线。

## Filter Pipeline

输入：`(tool_output: string)` → 输出：`(filtered_output: string)`

按优先级依次匹配，第一个命中的 filter 生效：

### 1. Sensitive Keyword Blocking

```
条件: output 包含任意 BLOCKED_KEYWORDS
动作: 替换为 "[BLOCKED: output contained sensitive keyword '{keyword}']"
默认关键词: SECRET, PASSWORD, PRIVATE_KEY, AWS_SECRET_ACCESS_KEY
```

### 2. Log Filtering

```
条件: 50%+ 的行匹配日志格式 (^\d{4}-\d{2}-\d{2}[T ].*?(INFO|DEBUG|WARN|ERROR|FATAL))
动作: 只保留含 ERROR/FATAL/WARN/Exception/Traceback 的行 ± 上下文
输出格式: "[LOG: {total} total lines, filtered to errors/warnings]\n{filtered_lines}"
无错误时: "[LOG: {total} lines, all INFO/DEBUG, no errors]"
```

### 3. Test Output Filtering

```
条件: 输出同时包含 pass 标记(✓/PASS/passing) 和 fail 标记(✗/FAIL/failing/AssertionError)
动作: 只保留失败用例及其 stack trace
输出格式: "[TESTS: {pass_count} passed, failures below]\n{failure_blocks}"
```

### 4. JSON Filtering

```
条件: 输出是有效 JSON 且 > MAX_OUTPUT_BYTES
动作: 只提取 JSON_KEEP_FIELDS 中的字段
输出格式: "[JSON: {size} bytes, key fields extracted. Omitted: {omitted_keys}]\n{extracted_json}"
默认保留字段: status, error, error_message, message, code, request_id, id, name
```

### 5. Generic Truncation

```
条件: 输出 > MAX_LINES 行 或 > MAX_OUTPUT_BYTES 字节
动作: 保留 HEAD_LINES + TAIL_LINES，中间截断
输出格式: "{head}\n\n[... {omitted} lines, {bytes} bytes total — truncated ...]\n\n{tail}"
默认值: MAX_LINES=80, MAX_OUTPUT_BYTES=4000, HEAD_LINES=30, TAIL_LINES=20
```

### 6. Pass-through

```
条件: 以上均未命中
动作: 原样返回
```

## Interface Contract

### Input (JSON on stdin)

```json
{
  "tool_name": "Bash",
  "tool_input": {"command": "..."},
  "tool_response": {"stdout": "...", "stderr": "..."}
}
```

### Output (JSON on stdout)

若需替换：
```json
{
  "filtered_output": "...",
  "filter_applied": "log|test|json|truncate|blocked",
  "original_bytes": 50000,
  "filtered_bytes": 250
}
```

若无需过滤（pass-through）：
```json
{}
```

## Integration Methods

| 平台 | 机制 | 当前支持 |
|------|------|---------|
| Claude Code | PostToolUse hook (stdout 替换结果) | ✅ 完整支持 |
| Kiro | PostToolUse hook (observe only, 不能修改) | ❌ 等待 issue #7417 |
| 任意 MCP 客户端 | MCP Server (`filtered_bash` tool) | ✅ 完整支持 |
| LangChain | `BaseTool._parse_output` 或 `trim_messages` | ✅ 需适配 |
| AutoGen | `TransformMessages` pipeline | ✅ 需适配 |

## Verification Protocol

验证过滤是否真正生效（而非仅在 UI 层隐藏）：

1. 生成随机 marker（6位随机数）
2. 将 marker 嵌入应被过滤掉的区域（如 INFO 日志行、JSON 的非关键字段、截断的中间段）
3. 通过 tool 执行命令
4. 要求 LLM 报告 marker 值 — 若无法报告，证明过滤生效
5. 对照组：通过不被过滤的方式读取 marker（如直接读文件），证明 marker 确实存在
