# Compact Guard — PreCompact + PostCompact 记忆保护

防止 compaction 丢失关键决策和进度信息。

## 工作方式

```
Session 进行中
     │
     │  compact-guard-collector (PostToolUse):
     │    扫描 Bash 输出中的 DECISION:/TASK:/CRITICAL: 标记
     │    记录修改中的文件列表
     │    → 写入 ~/.agent-harness/state/compact_memory.json
     │
     ▼
PreCompact 触发
     │
     │  compact-guard:
     │    - 新 session (<60s) → 阻断自动压缩（保护初始上下文）
     │    - 成熟 session → 放行，保存当前 memory 快照
     │
     ▼
Compaction 执行 (上下文被压缩)
     │
     ▼
PostCompact 触发
     │
     │  compact-guard:
     │    注入恢复信息:
     │    [TASK IN PROGRESS] Implement caching layer
     │    [FILES BEING MODIFIED] src/cache.py, src/redis.py
     │    [KEY DECISIONS MADE]
     │      - Use Redis instead of Memcached
     │    [CRITICAL CONTEXT]
     │      - Must maintain backward compat with v1 API
     │    [COMPACT #2] Previous context was compacted.
     │
     ▼
LLM 继续推理 (关键信息已恢复)
```

## Marker 协议

Agent 可以通过在 Bash 输出中包含标记来主动保存关键信息：

```bash
echo "DECISION: Use Redis for session store"
echo "TASK: Implement caching layer"
echo "CRITICAL: Must maintain backward compat with v1 API"
```

配合 steering 使用:
```markdown
## Memory Protocol (CLAUDE.md)
When you make a key design decision, record it:
  echo "DECISION: <what you decided and why>"
When you start a new sub-task:
  echo "TASK: <what you're working on>"
```

## 测试

```bash
python3 test_compact_guard.py  # 7 scenarios
```
