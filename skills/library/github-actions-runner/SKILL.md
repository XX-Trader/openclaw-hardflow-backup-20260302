---
name: github-actions-runner
displayName: "GitHub Actions Runner"
version: "1.0.0"
description: GitHub Actions 自托管 Runner 部署和管理技能。自动在服务器上部署 GitHub Actions Runner，实现无需白名单的 CI/CD、内网服务访问、更快的构建速度和更好的数据隐私。支持自动启动、监控和维护。
description_zh: "github-actions-runner技能，详见 SKILL.md"
license: MIT
author: Claude Code
updated_at: "2026-01-25"

triggers:
  keywords:
    - "GitHub Actions"
    - "CI/CD"
    - "自动化部署"
    - "GitHub Actions配置"
    - "workflows"
    - "自托管runner"
  auto_trigger: true
  confidence_threshold: 0.7

tools:
  required:
    - Bash
    - Read
    - Write
  optional:
    - Task

permissions:
  level: "full"
  scope:
    - "file:read"
    - "file:write"
    - "bash:full"
---

# GitHub Actions 自托管 Runner 部署技能

## 🎯 技能特性

- ✅ **自动部署**: 一键脚本自动安装配置 Runner
- ✅ **开机自启**: systemd 服务管理，服务器重启自动启动
- ✅ **权限管理**: 自动配置 sudo 权限
- ✅ **健康监控**: 监控脚本自动检查 Runner 状态
- ✅ **自动修复**: 检测到问题自动重启服务
- ✅ **无需白名单**: 不需要配置 5509 个 GitHub IP 白名单
- ✅ **内网访问**: Runner 可直接访问内网服务
- ✅ **更快速度**: 10 秒启动 vs GitHub 托管的 2 分钟

## 📋 适用场景

**强烈推荐使用自托管 Runner 当你需要**:
- 部署到内网服务器（不能配置外网白名单）
- 访问内网数据库、Redis 等服务
- 频繁部署（节省 GitHub Actions 分钟数）
- 保护敏感数据（代码不出外网）
- 需要 Docker 或特殊运行环境

**使用 GitHub 托管 Runner 当**:
- 偶尔部署（每月少于 10 次）
- 无特殊网络需求
- 不想维护服务器

## 🔧 前置要求

### 服务器要求

**最低配置**:
```
CPU: 2 核
内存: 4 GB
硬盘: 40 GB
系统: Ubuntu 20.04+ / CentOS 7+ / Debian 10+
带宽: 5 Mbps
```

**推荐配置**:
```
CPU: 4 核
内存: 8 GB
硬盘: 100 GB
系统: Ubuntu 22.04 LTS
带宽: 10 Mbps
```

### 网络要求

- ✅ 出站访问 `github.com` (443 端口)
- ✅ 能拉取 Docker 镜像 (如需要)
- ⚠️ 不需要入站白名单

### GitHub 准备

1. 获取 Runner Token:
   ```
   GitHub 仓库 → Settings → Actions → Self-hosted runners → New runner
   选择 Linux → 复制 Token (A... 开头，约 70-80 字符)
   ```

2. 仓库权限:
   - repo 权限（完整控制）
   - workflow 权限

## 📁 技能文件结构

```
skills/github-actions-runner/
├── SKILL.md                           # 本文件
├── README.md                          # 使用指南
├── QUICK_REFERENCE.md                 # 快速参考
├── scripts/
│   ├── deploy-github-runner.sh       # 一键部署脚本
│   ├── uninstall-github-runner.sh    # 卸载脚本
│   └── monitor-github-runner.sh      # 监控脚本
└── docs/
    ├── 部署指南.md                     # 详细部署文档
    ├── 快速参考.md                     # 常用命令速查
    └── 故障排查.md                     # 常见问题解决
```

## 🚀 快速部署

### 方式一：自动部署脚本（推荐）

```bash
# 1. SSH 登录服务器
ssh ubuntu@YOUR_SERVER_IP

# 2. 下载并运行部署脚本
wget https://raw.githubusercontent.com/YOUR_REPO/main/scripts/deploy-github-runner.sh
chmod +x deploy-github-runner.sh
sudo ./deploy-github-runner.sh
```

脚本会自动：
- ✅ 安装依赖 (Docker, Git, curl, jq)
- ✅ 创建 github-runner 用户
- ✅ 下载最新版 Runner
- ✅ 配置服务
- ✅ 启动并设置开机自启

### 方式二：手动部署

```bash
# 1. 安装依赖
sudo apt update
sudo apt install -y curl jq git docker.io

# 2. 创建用户
sudo useradd -m -s /bin/bash github-runner
sudo usermod -aG docker github-runner

# 3. 下载 Runner
mkdir -p /opt/github-runner
cd /opt/github-runner
curl -o actions-runner-linux-x64-2.330.0.tar.gz \
  -L https://github.com/actions/runner/releases/download/v2.330.0/actions-runner-linux-x64-2.330.0.tar.gz
tar xzf actions-runner-linux-x64-2.330.0.tar.gz
rm actions-runner-linux-x64-2.330.0.tar.gz

# 4. 配置 Runner
sudo -u github-runner ./config.sh \
  --url https://github.com/YOUR_ORG/YOUR_REPO \
  --token YOUR_TOKEN \
  --labels self-hosted,tencent-cloud \
  --work _work \
  --unattended

# 5. 安装服务
sudo -u github-runner ./svc.sh install github-runner
sudo ./svc.sh start

# 6. 配置 sudo 权限
echo "github-runner ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/github-runner
sudo chmod 440 /etc/sudoers.d/github-runner

# 7. 验证
./svc.sh status
```

## ⚙️ 配置 Workflow

部署完成后，修改你的 workflow 文件使用自托管 Runner：

```yaml
# .github/workflows/deploy.yml

name: 自动部署

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: self-hosted  # 使用自托管 Runner

    steps:
      - uses: actions/checkout@v4

      # 现在可以直接访问内网服务！
      - name: 部署到服务器
        run: |
          curl http://10.0.0.1:8000/api/deploy
          mysql -h 10.0.0.2 -u user -p password db < backup.sql
```

### 指定 Runner 标签

```yaml
jobs:
  deploy-production:
    runs-on: [self-hosted, production]  # 必须同时有这两个标签
```

## 🔍 验证部署

### 在 GitHub 上查看

1. 访问: `https://github.com/YOUR_REPO/settings/actions/runners`
2. 应该看到:
   ```
   ● VM-4-14-ubuntu (Idle)
   Labels: self-hosted, tencent-cloud
   ```

### 在服务器上验证

```bash
# 查看服务状态
cd /opt/github-runner
./svc.sh status

# 查看日志
sudo journalctl -u actions.runner.* -f

# 查看最近的任务
sudo journalctl -u actions.runner.* --no-pager | grep "Running job"
```

## 🛠️ 管理命令

```bash
cd /opt/github-runner

# 服务管理
./svc.sh start      # 启动
./svc.sh stop       # 停止
./svc.sh restart    # 重启
./svc.sh status     # 状态

# 日志查看
journalctl -u actions.runner.* -f          # 实时日志
journalctl -u actions.runner.* -n 100     # 最近 100 行

# 重新配置
./config.sh remove --token OLD_TOKEN
./config.sh --url https://github.com/REPO --token NEW_TOKEN
./svc.sh restart
```

## 📊 监控和维护

### 自动监控

使用监控脚本定期检查 Runner 健康：

```bash
# 上传监控脚本
scp scripts/monitor-github-runner.sh ubuntu@SERVER:/opt/

# 添加到 crontab（每小时检查）
sudo crontab -e
# 添加: 0 * * * * /opt/monitor-github-runner.sh --auto-fix
```

监控脚本会检查：
- ✅ 服务运行状态
- ✅ 进程是否存活
- ✅ 磁盘空间
- ✅ Docker 状态
- ✅ 自动修复问题

### 定期维护

**每日**:
- 监控脚本自动检查

**每周**:
- 查看日志，确认无异常

**每月**:
- 更新 Runner 版本
  ```bash
  cd /opt/github-runner
  ./bin/updatedependencies.sh
  ./svc.sh restart
  ```
- 清理构建缓存
  ```bash
  ./svc.sh stop
  find _work -mindepth 1 -maxdepth 1 -type d | sort -r | tail -n +6 | xargs rm -rf
  ./svc.sh start
  ```

## 🔄 开机自启配置

Runner 使用 systemd 管理，自动配置开机自启：

### 验证自启

```bash
# 检查是否启用
sudo systemctl is-enabled actions.runner.*
# 输出: enabled

# 查看符号链接
ls -l /etc/systemd/system/multi-user.target.wants/actions.runner.*
```

### 自启流程

```
服务器启动
  ↓
systemd 加载服务
  ↓
检查 multi-user.target.wants 符号链接
  ↓
自动启动 Runner 服务
  ↓
Runner 连接到 GitHub
  ↓
开始监听任务
```

### 重启测试

```bash
# 重启服务器
sudo reboot

# 等待重启后连接
ssh ubuntu@SERVER_IP

# 验证 Runner 自动启动
sudo systemctl status actions.runner.*
```

## ⚠️ 注意事项

### 安全建议

1. **最小权限**: Runner 用户有 sudo 权限，谨慎使用
2. **隔离部署**: 建议使用独立服务器或容器
3. **密钥管理**: 使用 GitHub Secrets 存储敏感信息
4. **日志审计**: 定期检查 Runner 日志

### 性能优化

1. **使用缓存**: 在 workflow 中配置依赖缓存
2. **并发限制**: 根据服务器配置调整 `max-parallel`
3. **定期清理**: 清理 `_work` 目录释放空间

### 故障处理

**Runner 离线**:
```bash
cd /opt/github-runner
./svc.sh restart
```

**Workflow 一直 pending**:
- 检查 `runs-on: self-hosted`
- 确认 Runner 在线

**权限问题**:
```bash
# 重新配置权限
echo "github-runner ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/github-runner
```

## 📚 相关资源

- [GitHub Actions Runner 官方文档](https://docs.github.com/en/actions/hosting-your-own-runners)
- [项目部署技能](../db-deploy/SKILL.md)

## 🔗 与其他技能配合

### 配合 db-deploy 使用

```yaml
# db-deploy 中的 workflow
jobs:
  deploy:
    runs-on: self-hosted  # 使用自托管 Runner
    steps:
      - name: 部署到生产环境
        run: |
          # 直接访问内网数据库和服务
          python manage.py migrate
          sudo systemctl restart django
```

优势：
- ✅ 无需配置 GitHub Actions IP 白名单
- ✅ 可直接访问内网 MySQL、Redis
- ✅ 部署速度更快（~10 秒启动）

### 配合 deployment-test 使用

```yaml
jobs:
  test:
    runs-on: self-hosted
    steps:
      - name: 测试 API
        run: |
          # 测试内网服务
          curl http://10.0.0.1:8000/api/health
```

## 📊 性能对比

| 特性 | GitHub 托管 | 自托管 Runner |
|------|------------|--------------|
| 启动时间 | ~2 分钟 | ~10 秒 |
| IP 白名单 | 需要 5509 个 | 不需要 |
| 内网访问 | ❌ | ✅ |
| 数据隐私 | 在 GitHub | 仅在你的环境 |
| 成本 | 按分钟计费 | 服务器成本 |
| 维护 | 无需维护 | 需要维护 |

## ✅ 完成检查清单

部署完成后，确认以下项目：

- [ ] Runner 在 GitHub 显示在线（绿色圆点）
- [ ] 服务状态为 `active (running)`
- [ ] 开机自启已启用 (`enabled`)
- [ ] sudo 权限已配置
- [ ] 测试 workflow 成功执行
- [ ] 可以访问内网服务
- [ ] 监控脚本已配置（可选）
- [ ] 文档已更新

## 🎓 最佳实践

1. **定期更新**: 每月更新 Runner 版本
2. **监控告警**: 配置监控脚本和定时任务
3. **备份配置**: 定期备份 Runner 配置文件
4. **日志管理**: 定期清理旧日志
5. **安全审查**: 定期审查 Runner 权限

## 💡 常见问题

**Q: Runner 占用多少资源？**
A: 空闲时约 50-100MB 内存，执行任务时根据任务而定。

**Q: 可以部署多个 Runner 吗？**
A: 可以，在同一服务器或不同服务器部署多个 Runner。

**Q: Runner 故障了怎么办？**
A: 监控脚本会自动重启，或手动执行 `./svc.sh restart`。

**Q: 需要公网 IP 吗？**
A: 不需要，Runner 只需要能访问 GitHub（出站连接）。

**Q: 能删除吗？**
A: 可以，使用 `./uninstall-github-runner.sh` 完全卸载。

---

**版本**: v1.0.0
**最后更新**: 2025-01-05
**维护者**: DaBaiLiangHua_quant Team
