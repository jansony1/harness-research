# Loop Breaker — PostToolBatch 循环打转检测

检测 agent 是否在反复做同样的事情而无进展，及时熔断。

## 检测信号

| 信号 | 阈值 | 场景 |
|------|------|------|
| 相同命令重复 | 3次 | `npm test` 一直失败一直跑 |
| 相似命令重复 | 5次 | `git add` 各种文件（基础命令相同） |
| 同文件反复编辑 | 5次 | 一个文件改来改去 |
| ABAB 交替模式 | 4批次 | edit → test fail → edit → test fail |
| Session 批次预算 | 50次 | 总调用量控制成本 |

## 为什么用 PostToolBatch

**PostToolBatch 是唯一在 "一批操作结束、下轮推理开始前" 的 hook。**

```
LLM 推理 → [并行 tool calls] → PostToolBatch → 下轮 LLM 推理
                                      ↑
                                  在这里阻断
```

单个 PostToolUse 无法综合看一批操作的全貌，也无法阻断下一轮推理。

## Hook 配置

```json
{
  "hooks": {
    "PostToolBatch": [
      {
        "hooks": [{"type": "command", "command": "python3 /path/to/loop_breaker.py"}]
      }
    ]
  }
}
```

## 触发时的输出

```
LOOP BREAKER — Agent appears stuck (detected 2 signal(s)):

  • Same command executed 4 times: 'npm test...'
  • Alternating pattern detected over last 4 batches

Session stats: 12 batches, 15 commands tracked.

Please step back and reconsider your approach before continuing.
```

## 测试

```bash
python3 test_loop_breaker.py
```
