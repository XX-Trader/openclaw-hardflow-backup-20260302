---
name: workflow-builder
description: 自然语言描述 → 标准工作流模板生成。将口语化的流程描述转换为 .agents/workflows/*.md 格式。
---

# 🏗️ Workflow Builder 技能

## 概述

将自然语言的流程描述自动转换为符合 `.agents/workflows/*.md` 格式的标准化工作流文件。

## 使用场景

- 用户描述了一个重复性操作流程，需要固化为工作流
- 从故障修复步骤中提炼可复用的运维工作流
- 批量生成部署/测试/回滚等标准工作流

## 使用方式

### 基本用法

```bash
python3 $HOME/.openclaw/ops/workflow_builder.py \
  --title "部署前端到生产环境" \
  --description "Vue3 前端构建并部署到 nofx 服务器" \
  --steps "1.npm run build 2.SCP上传dist到服务器 3.SSH重启nginx 4.验证页面可访问" \
  --output .agents/workflows/deploy-frontend.md
```

### 带前置条件和注意事项

```bash
python3 $HOME/.openclaw/ops/workflow_builder.py \
  --title "数据库备份与迁移" \
  --description "MySQL 数据库完整备份并迁移到新服务器" \
  --steps "1.SSH连接源服务器 2.执行mysqldump备份 3.SCP传输备份文件 4.SSH连接目标服务器 5.导入数据库 6.验证数据完整性" \
  --precondition "源/目标服务器 SSH 可连通" \
  --precondition "目标服务器已安装 MySQL" \
  --note "迁移前务必验证备份文件完整性" \
  --output .agents/workflows/db-migration.md
```

### 全自动模式

```bash
python3 $HOME/.openclaw/ops/workflow_builder.py \
  --title "日常健康检查" \
  --description "检查所有服务状态和磁盘空间" \
  --steps "1.检查pm2进程状态 2.检查磁盘空间 3.检查内存使用 4.检查日志错误" \
  --turbo-all \
  --output .agents/workflows/daily-health-check.md
```

## 步骤自动分类

| 分类 | 识别关键词 | 安全标记 |
|---|---|---|
| SSH 命令 | 连接/登录/远程/ssh | ❌ 需审批 |
| SCP 传输 | 上传/传输/同步/scp | ❌ 需审批 |
| Git 操作 | 提交/推送/commit/push | ❌ 需审批 |
| Python 脚本 | python/执行脚本/.py | ✅ turbo |
| npm 命令 | npm/yarn/pnpm | ✅ turbo |
| 验证操作 | 验证/检查/确认/测试 | ✅ turbo |
| 配置变更 | 修改/更新/配置 | ❌ 需审批 |
| 服务操作 | 重启/启动/停止/pm2 | ❌ 需审批 |
