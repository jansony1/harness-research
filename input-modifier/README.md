# Input Modifier — PreToolUse 参数篡改

在 tool 执行前透明修改参数，不阻断、不报错，agent 不一定意识到改变。

## 修改规则

| 原始命令 | 修改后 | 效果 |
|---------|--------|------|
| `git push origin main` | `git push --dry-run origin main` | 先预览再真推 |
| `rm -rf src/old/` | `find src/old/ -maxdepth 1 \| head -20` | 看看要删什么 |
| `npm install` | `timeout 30 npm install` | 防止挂死 |
| Read 100KB 文件 | Read + limit=500 lines | 避免大文件撑爆上下文 |

## 与 safety-guard 的分工

```
PreToolUse 调用顺序:
  1. safety-guard  → 真正危险的直接 block (exit 2)
  2. input-modifier → 不太危险的加防护措施 (updatedInput)
```

- `git push --force` → safety-guard 阻断（不可接受）
- `git push` → input-modifier 加 `--dry-run`（可以做，但先看看）
- `rm -rf node_modules` → input-modifier 放行（已知安全）
- `rm -rf src/` → input-modifier 转为 preview（可能误删）

## 配置

环境变量控制各规则开关：
```bash
INPUT_MOD_DRY_RUN_PUSH=1   # git push 加 --dry-run
INPUT_MOD_DRY_RUN_RM=1     # rm 转为 preview
INPUT_MOD_LIMIT_READS=1    # 大文件自动加 limit
INPUT_MOD_TIMEOUTS=1       # 长命令加 timeout
```

## 测试

```bash
python3 test_input_modifier.py  # 11 scenarios
```
