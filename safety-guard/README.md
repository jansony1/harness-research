# Safety Guard — PreToolUse 破坏性命令拦截

在危险操作**执行之前**拦截，而不是事后统计。

## 防护范围

| 类别 | 示例 |
|------|------|
| 破坏性 Git | `git push --force`, `git reset --hard`, `git branch -D` |
| 文件系统 | `rm -rf /`, `rm -rf ~`, `chmod 777` |
| 凭证泄露 | `cat .env`, `echo $SECRET_KEY`, `env \| grep` |
| 生产环境 | `deploy prod`, `kubectl --context production`, `terraform apply` |
| 远程执行 | `curl ... \| bash`, `wget ... \| sh` |
| 受保护路径 | 写入 `/etc/`, `.env`, `.ssh/`, `credentials.json` |

## Hook 配置

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Edit|Write",
        "hooks": [{
          "type": "command",
          "command": "python3 /path/to/safety_guard.py"
        }]
      }
    ]
  }
}
```

## 效果

Agent 收到的是 deny + 原因，不是错误：
```
[DESTRUCTIVE] force push can overwrite remote history
  Command: git push origin main --force
```

Agent 可以向用户解释为什么被拒绝，用户决定是否放行。

## 测试

```bash
python3 test_safety_guard.py
# 30 scenarios: destructive git, fs, credentials, production, protected paths
```
