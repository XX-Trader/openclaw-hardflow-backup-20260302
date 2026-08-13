# Linux 服务器部署

## 前置条件

- Python 3.11+
- Git
- 对 `<RUNTIME_HOME>` 的写权限

## 安装

```bash
python3 setup.py \
  --runtime-home "${HARDFLOW_RUNTIME_HOME:-$HOME/.hardflow-runtime}" \
  --runtime-name "${RUNTIME_NAME:-node}" \
  --timezone "${RUNTIME_TIMEZONE:-UTC}" \
  --dry-run --emit-json

python3 setup.py \
  --runtime-home "${HARDFLOW_RUNTIME_HOME:-$HOME/.hardflow-runtime}" \
  --runtime-name "${RUNTIME_NAME:-node}" \
  --timezone "${RUNTIME_TIMEZONE:-UTC}" \
  --emit-json
```

## 验收与回滚

检查安装 JSON、目标目录文件、Cron JSON 和健康检查输出。回滚时依据本次安装清单删除或恢复托管文件，并保留目标 Runtime 自有配置。
