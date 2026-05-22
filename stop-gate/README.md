# Stop Gate — 停止前强制质量验证

Agent 不能半途而废。停止前必须满足质量标准。

## 检查项

| 检查 | 条件 | 可配置 |
|------|------|--------|
| 测试必须跑过 | session 内至少执行过一次 test 命令且通过 | `STOP_GATE_REQUIRE_TESTS` |
| Git 状态干净 | 无未提交的改动 | `STOP_GATE_REQUIRE_GIT` |
| 无 TODO/FIXME | 修改过的文件中不含 incomplete markers | `STOP_GATE_REQUIRE_NO_FIXME` |

## 双 Hook 架构

```
PostToolUse (stop_gate_tracker.py):
  - 追踪 test 是否跑过
  - 追踪 test 是否通过
  - 记录修改了哪些文件
  - 写入 ~/.agent-harness/state/stop_gate.json

Stop (stop_gate.py):
  - 读取状态
  - 运行所有检查
  - 不达标 → exit 2 阻断停止，告诉 agent 还差什么
```

## Hook 配置

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash|Edit|Write",
        "hooks": [{"type": "command", "command": "python3 /path/to/stop_gate_tracker.py"}]
      }
    ],
    "Stop": [
      {
        "hooks": [{"type": "command", "command": "python3 /path/to/stop_gate.py"}]
      }
    ]
  }
}
```

## 安全阀

连续被 block 3 次后自动放行（`STOP_GATE_MAX_BLOCKS`），避免 agent 永远无法停止。

## 测试

```bash
python3 test_stop_gate.py
```
