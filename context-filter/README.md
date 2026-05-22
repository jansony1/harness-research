# Context Filter — Tool Output 分级过滤

LLM agent 的 tool result 会全量注入上下文窗口，导致：
- 大量无关信息稀释注意力
- 加速触发 context compaction
- 增加 token 消耗和成本

本项目提供三种集成方式：

| 方式 | 适用平台 | 说明 |
|------|---------|------|
| [PostToolUse Hook](./.claude/) | Claude Code | Hook 拦截替换 tool result |
| [MCP Server](./mcp-server/) | 任意 MCP 客户端 (Claude Code, Kiro, Cursor, VS Code) | 平台无关的 `filtered_bash` tool |
| [Spec](./spec.md) | 任意 agent 框架 | 行为规格，可适配到 LangChain/AutoGen 等 |

## 过滤策略（优先级从高到低）

| # | 策略 | 触发条件 | 处理方式 |
|---|------|---------|---------|
| 1 | 敏感词拦截 | 输出含 SECRET/PASSWORD/PRIVATE_KEY | 完全替换为 blocked 提示 |
| 2 | 日志过滤 | 50%+ 行匹配日志时间格式 | 只保留 ERROR/WARN + 上下文(±3行) |
| 3 | 测试输出过滤 | 含 ✓/✗/PASS/FAIL 标记 | 只保留失败用例 + 摘要 |
| 4 | JSON 过滤 | JSON 输出 > 4KB | 只提取 status/error 等关键字段 |
| 5 | 通用截断 | 超过 80 行或 4KB | head 30 行 + tail 20 行 |

## 安装

将 `.claude/` 目录复制到你的项目根目录：

```bash
cp -r .claude/ /path/to/your/project/.claude/
```

确保 `settings.json` 中的路径指向正确的 hook 脚本位置：

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/your/project/.claude/hooks/post_tool_filter.py"
          }
        ]
      }
    ]
  }
}
```

## 配置

编辑 `.claude/hooks/post_tool_filter.py` 顶部的配置区：

```python
BLOCKED_KEYWORDS = ["SECRET", "PASSWORD", "PRIVATE_KEY"]  # 拦截关键词
MAX_OUTPUT_BYTES = 4000   # 触发截断的字节阈值 (~1000 tokens)
MAX_LINES = 80            # 触发截断的行数阈值
HEAD_LINES = 30           # 截断后保留的头部行数
TAIL_LINES = 20           # 截断后保留的尾部行数
JSON_KEEP_FIELDS = ["status", "error", "error_message", ...]  # JSON 保留字段
```

## 验证方法

用 `examples/` 下的脚本生成模拟数据来验证过滤效果：

```bash
# 1. 日志过滤 — 500行日志只保留 ERROR
bash examples/gen_fake_log.sh

# 2. 测试输出过滤 — 50个测试只显示失败
bash examples/gen_test_output.sh

# 3. JSON 过滤 — 15KB JSON 只提取关键字段
bash examples/gen_fake_json.sh
```

### 盲测验证（证明过滤确实生效）

```bash
# 生成随机 marker 并嵌入会被过滤的区域
MARKER=$(python3 -c "import random; print(random.randint(100000,999999))")
echo "marker=$MARKER" > /tmp/marker.txt

# 在大量 INFO 日志中间嵌入 marker（远离 ERROR 行）
for i in $(seq 1 100); do
  echo "2026-01-01T00:00:00Z INFO noise $i"
done
echo "2026-01-01T00:00:00Z INFO hidden=$MARKER"
for i in $(seq 101 200); do
  echo "2026-01-01T00:00:00Z INFO noise $i"
done
echo "2026-01-01T12:00:00Z ERROR real error here"

# 然后用 Read 工具读 /tmp/marker.txt 做对照
# 如果模型无法报告 marker 值但能从文件中读到 → 过滤生效
```

## 效果数据

| 场景 | 原始大小 | 过滤后 | 压缩比 | 信息损失 |
|------|---------|--------|--------|---------|
| 应用日志 (500行) | ~50KB | ~250B | 99.5% | 无 |
| API JSON 响应 | ~15KB | ~130B | 99.1% | 无 |
| 测试输出 (50个用例) | ~3KB | ~500B | 82% | 无 |
| 通用长输出 (200行) | ~18KB | ~5KB | 72% | 中间部分 |

## 局限性

- 只作用于 `Bash` 工具，`Read` 工具不受影响（需额外配置 matcher）
- 日志过滤依赖时间戳正则匹配，非标准格式可能漏判
- JSON 字段白名单需要根据实际 API 调整
- hook 本身有执行开销（Python 启动 ~50ms），高频调用时需注意

## 扩展方向

- 支持 `Read` 工具的过滤（大文件读取场景）
- 用 LLM summarization 替代截断（输出 → 小模型摘要 → 注入主模型）
- 按 tool 调用意图动态调整过滤策略
- 统计 token 节省量的 metrics 收集
