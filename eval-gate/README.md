# Eval Gate — 第二 Agent 评审门禁

在 agent 完成任务前，调用第二个 LLM 做 code review。不通过则阻断。

## 与 stop-gate 的区别

| | stop-gate | eval-gate |
|--|-----------|-----------|
| 检查方式 | 机械条件（测试跑了？有 FIXME？） | 语义审查（逻辑对吗？有遗漏？） |
| 判断者 | 规则脚本 | 第二次 LLM 推理 |
| 成本 | 几乎为零 | 每次触发消耗 ~2000 tokens |
| 适合 | 每次 Stop | 重要 task 完成时 |

## 工作方式

```
Agent 完成工作 → [TaskCompleted/Stop hook]
    │
    ▼
eval_gate.py:
    1. git diff HEAD → 获取变更
    2. claude --print "Review this diff..." → 第二次 LLM 推理
    3. 输出包含 "APPROVED" → 放行
    4. 输出不包含 → exit 2 阻断，反馈给 agent
    │
    ▼
Agent 收到 review feedback → 修改 → 再次尝试完成
```

## 安装

```json
{
  "hooks": {
    "TaskCompleted": [
      {"hooks": [{"type": "command", "command": "python3 path/to/eval_gate.py"}]}
    ],
    "Stop": [
      {"hooks": [{"type": "command", "command": "python3 path/to/eval_gate.py"}]}
    ]
  }
}
```

## 配置

```bash
EVAL_GATE_REVIEWER=claude    # 调用的 reviewer 命令 (默认 claude)
```

脚本顶部可调：
```python
MAX_DIFF_CHARS = 8000        # diff 截断长度
MAX_REVIEW_TIMEOUT = 60      # reviewer 超时秒数
MAX_CONSECUTIVE_BLOCKS = 2   # 安全阀：连续拒绝 N 次后放行
```

## 安全机制

- 无 diff → 跳过（不浪费 reviewer token）
- Reviewer 超时/崩溃 → 放行（不因 infra 问题阻塞 agent）
- 连续阻断 2 次 → 自动放行（避免死循环）
- 空 reviewer 响应 → 放行

## 行业对标

| 平台 | 类似机制 |
|------|---------|
| Devin | 内建 self-review（diff → 第二次 LLM） |
| AutoGen | critic agent 对话 loop |
| CrewAI | hierarchical manager 审批 |
| LangGraph | Reflection 节点 + conditional edge |

## 测试

```bash
python3 test_eval_gate.py  # 7 scenarios (uses mock reviewer)
```
