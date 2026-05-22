# Context Filter — PostToolUse 输出分级过滤

LLM agent 的 tool result 全量注入上下文窗口，导致信息稀释、加速 compaction、成本膨胀。

本 harness 通过 PostToolUse hook 在输出返回给 LLM 前进行分级过滤。

## 过滤策略（优先级从高到低）

| # | 策略 | 触发条件 | 处理方式 |
|---|------|---------|---------|
| 1 | 敏感词拦截 | 输出含 SECRET/PASSWORD/PRIVATE_KEY | 完全替换为 blocked 提示 |
| 2 | 日志过滤 | 50%+ 行匹配日志时间格式 | 只保留 ERROR/WARN + 上下文(±3行) |
| 3 | 测试输出过滤 | 含 ✓/✗/PASS/FAIL 标记 | 只保留失败用例 + 摘要 |
| 4 | JSON 过滤 | JSON 输出 > 4KB | 只提取 status/error 等关键字段 |
| 5 | 通用截断 | 超过 80 行或 4KB | head 30 行 + tail 20 行 |

## 安装

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "python3 path/to/context_filter.py"}]
      }
    ]
  }
}
```

## 配置

编辑 `context_filter.py` 顶部：

```python
BLOCKED_KEYWORDS = ["SECRET", "PASSWORD", "PRIVATE_KEY"]
MAX_OUTPUT_BYTES = 4000   # ~1000 tokens
MAX_LINES = 80
HEAD_LINES = 30
TAIL_LINES = 20
JSON_KEEP_FIELDS = ["status", "error", "error_message", ...]
```

## 验证

```bash
# 模拟数据生成
bash examples/gen_fake_log.sh      # 500行日志
bash examples/gen_test_output.sh   # 50个测试用例
bash examples/gen_fake_json.sh     # 15KB JSON
```

盲测：嵌入随机 marker 到会被过滤的区域，验证模型无法报告 marker 值。

## 效果

| 场景 | 原始 | 过滤后 | 压缩比 |
|------|------|--------|--------|
| 应用日志 (500行) | ~50KB | ~250B | 99.5% |
| API JSON 响应 | ~15KB | ~130B | 99.1% |
| 测试输出 (50用例) | ~3KB | ~500B | 82% |
| 通用长输出 (200行) | ~18KB | ~5KB | 72% |
