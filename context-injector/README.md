# Context Injector — 多事件上下文注入

在关键时机向 agent 的上下文注入信息，引导其行为而不阻断执行。

## 覆盖事件

| Hook 事件 | 触发时机 | 注入内容 |
|-----------|---------|---------|
| SessionStart(resume/compact) | Session 恢复时 | 之前的失败数、修改文件列表 |
| PostToolUseFailure | 每次 tool 失败 | "连续失败N次" 警告 + 递进引导 |
| PostToolBatch | 每 10 批次 | Checkpoint 总结（调用数、文件数） |
| SubagentStop | Subagent 要停止时 | 输出太短 → 阻断 + 要求补充 |

## 递进引导策略

```
失败 1次: (静默)
失败 2次: [WARNING] 2 consecutive failures detected.
失败 3次: Consider: Is the current approach working?
失败 5次: STRONGLY consider stopping and explaining the blocker.
```

## 与其他 Harness 的协作

- **loop-breaker** 在 PostToolBatch 做"硬熔断"（exit 2 阻断）
- **context-injector** 在 PostToolBatch 做"软引导"（注入 checkpoint 信息）
- 两者可以同时挂在 PostToolBatch 上，按顺序执行

## 测试

```bash
python3 test_context_injector.py  # 8 scenarios
```
