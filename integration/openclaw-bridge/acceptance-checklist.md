# Runtime Bridge 验收清单

## 安装预检

```bash
python setup.py --runtime-home <RUNTIME_HOME> --runtime-name <RUNTIME_NAME> --dry-run --emit-json
```

## 验收项

- [ ] 目标 Runtime、项目目录、通知通道和时区来自参数或环境变量。
- [ ] 安装清单只包含托管文件。
- [ ] `cron/jobs.json` 可解析且引用存在的 owner 脚本。
- [ ] Runtime Profile 健康检查通过。
- [ ] 未配置部署命令时记录显式跳过。
- [ ] 失败产物包含 `failed_stage`、证据和下一步。
- [ ] 回滚不影响非托管配置。
