# 部署与运维

本目录记录领域中立的 Runtime 安装、验证、更新和回滚流程。所有目标目录、通知通道、时区和项目路径均通过参数或环境变量注入。

## 唯一安装入口

```bash
python setup.py --runtime-home <RUNTIME_HOME> --runtime-name <RUNTIME_NAME> --dry-run --emit-json
python setup.py --runtime-home <RUNTIME_HOME> --runtime-name <RUNTIME_NAME> --emit-json
```

`setup.py` 委托 `skills/library/project-delivery-pipeline/scripts/runtime_installer.py`，负责 Skills、ops 文件和 Cron 模板的幂等安装。

## 验证

1. 先审阅 dry-run JSON 中的目标路径、复制清单和 Cron 渲染结果。
2. 安装后运行 `skills/library/log-monitor/scripts/runtime_profile_healthcheck.py`。
3. 对 `cron/jobs.json` 做 JSON 解析，并由 `export_schedule_registry.py` 导出调度总表。
4. 失败时只回滚本次安装清单中列出的文件，不触碰目标目录中的非托管内容。

## 平台文档

- [Windows 本机部署](windows-本机部署说明.md)
- [Linux 服务器部署](linux-服务器部署说明.md)
- [多项目 Runtime 模板](多项目服务器模板.md)
- [安装与工作流部署](安装与工作流部署说明.md)
- [维护与排障索引](项目维护与排障索引.md)
