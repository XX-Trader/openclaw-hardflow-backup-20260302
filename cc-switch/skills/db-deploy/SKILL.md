---
name: db-deploy
description: 全栈项目自动部署技能。支持 Django 后端、Vue3 前端、MySQL 数据库、Redis 缓存、Nginx 反向代理和 Python 脚本的完整部署流程。当用户请求部署、更新、或维护 Web 项目时使用此技能。支持多仓库配置、GitHub Actions 自动部署、SSL 证书自动配置。
license: MIT
---

# 全栈项目自动部署技能

## 🎯 技能特性

- ✅ 支持多项目、多仓库部署
- ✅ 配置文件驱动，易于管理
- ✅ GitHub Actions 自动部署
- ✅ SSL 证书自动申请和续期
- ✅ 完整的备份和恢复机制
- ✅ 一键初始化和更新

## 📁 技能文件结构

```
db-deploy/
├── SKILL.md                      # 本文件
├── DEPLOYMENT_CHECKLIST.md       # 部署前准备清单
├── templates/                    # 配置模板
│   ├── deploy.config.env         # 部署配置模板
│   ├── github-action.yml         # GitHub Actions 模板
│   └── nginx.conf                # Nginx 配置模板
└── scripts/                      # 脚本文件
    ├── deploy.sh                 # 主部署脚本
    ├── init-config.sh            # 初始化配置脚本
    └── backup.sh                 # 备份脚本
```

## 🚀 快速开始

### 1. 准备阶段

查看 [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) 完成所有准备工作。

**关键准备项**:
- 服务器 IP 和 SSH 访问
- 域名（如需）
- GitHub 仓库和 Personal Access Token
- 各种密钥和密码

### 2. 配置阶段

```bash
# 复制配置模板
cp templates/deploy.config.env deploy.config.env

# 编辑配置文件
vim deploy.config.env
```

**配置文件结构** (详见模板):
```bash
# 服务器配置
SERVER_HOST="your.server.ip"
SERVER_PORT="22"
SERVER_USER="root"

# GitHub 配置
GITHUB_OWNER="your-github-username"
GITHUB_REPO="your-repo-name"
GITHUB_BRANCH="main"

# 项目配置
PROJECT_NAME="my-project"
PROJECT_ROOT="/www/wwwroot/my-project"

# 域名配置
DOMAIN="example.com"
WWW_DOMAIN="www.example.com"
API_DOMAIN="api.example.com"

# 数据库配置
DB_NAME="my_database"
DB_USER="db_user"
DB_PASSWORD="your_secure_password"

# Django 配置
DJANGO_SECRET_KEY="your_django_secret_key"
DJANGO_SETTINGS_MODULE="myproject.settings"

# 前端配置
FRONTEND_BUILD_COMMAND="npm run build"
FRONTEND_DIST_DIR="dist"

# 后端配置
BACKEND_PYTHON_VERSION="3.10"
BACKEND_VENV_NAME="venv"
```

### 3. 部署阶段

```bash
# 方法 1: 使用配置文件部署
bash scripts/deploy.sh --config deploy.config.env

# 方法 2: 交互式部署
bash scripts/deploy.sh --interactive

# 方法 3: 使用 GitHub Actions 自动部署
# (需要先配置 GitHub Secrets)
git push origin main
```

## 📋 项目架构概览

```
服务器环境 (Ubuntu 22.04+)
${PROJECT_ROOT}/                     # 项目根目录
├── backend/                         # 后端代码
│   ├── Project/BackendProject/      # Django 项目目录
│   │   ├── manage.py
│   │   ├── requirements.txt
│   │   └── ${BACKEND_VENV_NAME}/    # Python 虚拟环境
│   └── .env                         # 环境变量
├── frontend/                        # 前端代码
│   └── Project/FrontendProject/
│       └── ${FRONTEND_DIST_DIR}/    # 构建输出
├── logs/                            # 日志目录
│   ├── django-error.log
│   ├── django-access.log
│   ├── nginx-error.log
│   └── nginx-access.log
└── backups/                         # 备份目录
    ├── db/
    └── files/

系统配置:
├── /var/lib/mysql/                  # MySQL 数据
├── /etc/nginx/conf.d/               # Nginx 配置
└── /etc/supervisor/conf.d/          # Supervisor 配置
```

## 🔄 完整部署流程

### 流程概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        完整部署流程                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  本地开发环境                          Git 仓库                   服务器      │
│  ──────────                          ───────                   ───────      │
│                                                                             │
│  ┌──────────────┐      ┌───────────────┐      ┌───────────────┐            │
│  │  1. 创建仓库  │ ───→ │  2. 推送代码   │ ───→ │  3. 克隆代码   │            │
│  │  GitHub/     │      │  git push     │      │  git clone    │            │
│  │  GitLab      │      │               │      │               │            │
│  └──────────────┘      └───────────────┘      └───────────────┘            │
│         │                                            │                     │
│         │                                            ↓                     │
│         │                                    ┌───────────────┐            │
│         │                                    │  4. 安装依赖   │            │
│         │                                    │  pip/npm      │            │
│         │                                    └───────────────┘            │
│         │                                            │                     │
│         │                                            ↓                     │
│         │                                    ┌───────────────┐            │
│         │                                    │  5. 配置服务   │            │
│         │                                    │  Nginx/Superv │            │
│         │                                    └───────────────┘            │
│         │                                            │                     │
│         │                                            ↓                     │
│         │                                    ┌───────────────┐            │
│         │                                    │  6. 启动服务   │            │
│         │                                    │  systemctl    │            │
│         │                                    └───────────────┘            │
│         │                                                                   │
│         └────────────────────────────────────────────────────────────────   │
│                                                                             │
│  后续更新 (可选配置 GitHub Actions 自动部署)                                 │
│  ─────────────────────────────────────────────────────────────────────────   │
│                                                                             │
│  ┌──────────────┐      ┌───────────────┐      ┌───────────────┐            │
│  │ 修改本地代码  │ ───→ │ git push      │ ───→ │ 自动部署       │            │
│  │             │      │ 触发 Actions   │      │ 或手动更新     │            │
│  └──────────────┘      └───────────────┘      └───────────────┘            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 步骤 1: 创建 GitHub 仓库

#### 1.1 创建后端仓库

```bash
# 在 GitHub 网站创建新仓库
# 仓库名称: my-project-backend (或你的项目名)
# 描述: Django backend for my project
# 可见性: Private (私有) 或 Public (公开)
# 不要初始化 README、.gitignore 或 license
```

创建后，GitHub 会显示仓库地址，例如：
```
https://github.com/your-github-username/my-project-backend.git
```

#### 1.2 创建前端仓库 (可选)

如果前后端分离，创建独立仓库：

```bash
# 在 GitHub 创建第二个仓库
# 仓库名称: my-project-frontend
# 仓库地址: https://github.com/your-github-username/my-project-frontend.git
```

---

### 步骤 2: 上传本地代码到 Git

#### 2.1 初始化本地 Git 仓库

```bash
# 进入你的项目目录
cd /path/to/your/local/project

# 初始化 Git 仓库
git init

# 添加所有文件
git add .

# 首次提交
git commit -m "feat: initial commit"
```

#### 2.2 关联远程仓库并推送

**后端项目**:
```bash
# 添加远程仓库 (替换为你的仓库地址)
git remote add origin https://github.com/your-github-username/my-project-backend.git

# 推送到远程仓库
git branch -M main
git push -u origin main
```

**前端项目** (如果独立):
```bash
cd /path/to/frontend/project
git init
git add .
git commit -m "feat: initial commit"
git remote add origin https://github.com/your-github-username/my-project-frontend.git
git branch -M main
git push -u origin main
```

---

### 步骤 3: 配置部署参数

现在使用部署技能配置服务器参数：

**Windows**:
```bash
# 进入技能目录
cd %USERPROFILE%\.claude\skills\db-deploy

# 使用交互式向导配置
bash scripts/init-config.sh
```

**Linux/Mac**:
```bash
# 进入技能目录
cd $HOME/.claude/skills/db-deploy

# 使用交互式向导配置
bash scripts/init-config.sh
```

在配置向导中，填写以下关键信息：

```bash
# GitHub 配置
GitHub 用户名或组织: your-github-username
后端仓库名称: my-project-backend
前端仓库名称: my-project-frontend (可选)
Git 分支名称: main

# 服务器配置
服务器 IP: YOUR_SERVER_IP
SSH 端口: 22
SSH 用户: root (或 ubuntu/centos)

# 项目配置
项目名称: my-project
项目根目录: /www/wwwroot/my-project
```

配置完成后，会生成 `deploy.config.env` 文件。

---

### 步骤 4: 服务器部署

#### 4.1 SSH 登录服务器

```bash
# 使用密码登录
ssh root@YOUR_SERVER_IP

# 或使用 SSH 密钥 (推荐)
ssh -i ~/.ssh/id_ed255 root@YOUR_SERVER_IP
```

#### 4.2 安装系统依赖

```bash
# 更新软件包
sudo apt update

# 安装必需软件
sudo apt install -y \
    python3.10 \
    python3.10-venv \
    python3-pip \
    mysql-server \
    redis-server \
    nginx \
    git \
    supervisor \
    certbot \
    python3-certbot-nginx
```

#### 4.3 克隆代码

**方式 1: 使用 HTTPS (推荐首次部署)**

```bash
# 创建项目目录
sudo mkdir -p /www/wwwroot/my-project
cd /www/wwwroot/my-project

# 克隆后端代码
git clone https://github.com/your-github-username/my-project-backend.git backend

# 克隆前端代码 (如果独立)
git clone https://github.com/your-github-username/my-project-frontend.git frontend
```

**方式 2: 使用 SSH (需要配置 SSH 密钥)**

```bash
# 生成 SSH 密钥
ssh-keygen -t ed25519 -C "server@your-domain.com"

# 查看公钥
cat ~/.ssh/id_ed255.pub

# 将公钥添加到 GitHub:
# Settings → SSH and GPG keys → New SSH key → 粘贴公钥

# 使用 SSH 克隆
git clone git@github.com:your-github-username/my-project-backend.git backend
```

#### 4.4 配置数据库

```bash
# 登录 MySQL
sudo mysql

# 在 MySQL 命令行中执行:
CREATE DATABASE my_database CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'db_user'@'localhost' IDENTIFIED BY 'your_secure_password';
GRANT ALL PRIVILEGES ON my_database.* TO 'db_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

#### 4.5 部署后端

```bash
# 进入后端目录
cd /www/wwwroot/my-project/backend/Project/BackendProject

# 创建虚拟环境
python3.10 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 创建环境变量文件
cp .env.example .env
nano .env  # 编辑配置文件

# 数据库迁移
python manage.py makemigrations
python manage.py migrate

# 创建超级用户
python manage.py createsuperuser

# 收集静态文件
python manage.py collectstatic --noinput
```

#### 4.6 部署前端

```bash
# 进入前端目录
cd /www/wwwroot/my-project/frontend/Project/FrontendProject

# 安装依赖
npm install

# 构建生产版本
npm run build
```

#### 4.7 配置 Nginx

```bash
# 复制 Nginx 配置
sudo cp /path/to/db-deploy/templates/nginx.conf /etc/nginx/conf.d/my-project.conf

# 编辑配置 (修改域名和路径)
sudo nano /etc/nginx/conf.d/my-project.conf

# 测试配置
sudo nginx -t

# 重启 Nginx
sudo systemctl restart nginx
```

#### 4.8 配置 Supervisor (Django 进程管理)

```bash
# 创建 Supervisor 配置
sudo nano /etc/supervisor/conf.d/my-project-django.conf
```

配置内容:
```ini
[program:my-project-django]
command=/www/wwwroot/my-project/backend/Project/BackendProject/venv/bin/gunicorn \
          --workers 3 \
          --bind unix:/tmp/my-project-django.sock \
          myproject.wsgi:application
directory=/www/wwwroot/my-project/backend/Project/BackendProject
user=www-data
autostart=true
autorestart=true
stderr_logfile=/www/wwwroot/my-project/logs/django-error.log
stdout_logfile=/www/wwwroot/my-project/logs/django-access.log
```

启动服务:
```bash
# 重新加载配置
sudo supervisorctl reread
sudo supervisorctl update

# 启动 Django
sudo supervisorctl start my-project-django
```

#### 4.9 配置 SSL 证书 (有域名时)

```bash
# 申请 Let's Encrypt 证书
sudo certbot --nginx -d example.com -d www.example.com

# 自动续期 (已自动配置)
sudo certbot renew --dry-run
```

#### 4.10 一键启动所有服务

```bash
# 使用技能提供的一键启动脚本
bash /path/to/db-deploy/scripts/start.sh
```

---

### 步骤 5: 配置自动部署 (可选)

#### 5.1 配置 GitHub Secrets

在 GitHub 仓库: `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

添加以下 Secrets:

| Secret 名称 | 值 | 说明 |
|------------|---|------|
| `SERVER_HOST` | `YOUR_SERVER_IP` | 服务器 IP |
| `SERVER_PORT` | `22` | SSH 端口 |
| `SERVER_USER` | `root` | SSH 用户 |
| `SERVER_SSH_KEY` | `-----BEGIN OPENSSH PRIVATE KEY-----...` | SSH 私钥内容 |
| `DJANGO_SECRET_KEY` | `your_django_secret_key` | Django 密钥 |
| `DB_NAME` | `my_database` | 数据库名 |
| `DB_USER` | `db_user` | 数据库用户 |
| `DB_PASSWORD` | `your_secure_password` | 数据库密码 |

#### 5.2 创建 GitHub Actions 工作流

```bash
# 在本地项目创建 .github/workflows 目录
mkdir -p .github/workflows

# 复制工作流模板
cp /path/to/db-deploy/templates/github-action.yml .github/workflows/deploy.yml

# 提交并推送
git add .github/workflows/deploy.yml
git commit -m "feat: add GitHub Actions workflow"
git push origin main
```

---

### 步骤 6: 后续更新流程

#### 方式 1: 自动部署 (GitHub Actions)

```bash
# 本地修改代码
vim some_file.py

# 提交并推送
git add .
git commit -m "fix: bug fix"
git push origin main

# ✅ GitHub Actions 自动触发部署
```

#### 方式 2: 手动更新

```bash
# 登录服务器
ssh root@YOUR_SERVER_IP

# 进入项目目录
cd /www/wwwroot/my-project/backend
git pull origin main

# 或更新前端
cd /www/wwwroot/my-project/frontend
git pull origin main

# 重启服务
sudo supervisorctl restart my-project-django
sudo nginx -s reload
```

#### 方式 3: 使用部署脚本

```bash
# 在服务器上运行
bash /www/wwwroot/db-deploy/scripts/deploy.sh --update
```

---

## 🔧 部署流程详解

### 0. 选择 Runner 类型

在配置 GitHub Actions 自动部署前,需要选择使用的 Runner 类型:

#### Runner 类型对比

| 特性 | GitHub 托管 Runner | 自托管 Runner |
|------|-------------------|--------------|
| **IP 白名单** | ❌ 5509 个 IP 段,无法全部添加 | ✅ 无需白名单 (服务器主动连 GitHub) |
| **部署速度** | ⚡ 快 (云环境) | 🚀 更快 (本地环境) |
| **成本** | ❌ 公开仓库免费,私有仓库收费 | ✅ 完全免费 |
| **网络访问** | ❌ 无法访问内网服务 | ✅ 可访问内网 (数据库/缓存) |
| **维护成本** | ✅ 无需维护 | ⚠️ 需要维护服务器 |
| **环境控制** | ⚠️ 固定环境 | ✅ 完全自定义 |
| **适用场景** | 小项目、公开仓库 | 生产环境、内网服务 |

#### 推荐方案

**使用自托管 Runner (推荐)** 如果:
- ✅ 云服务器安全组有 IP 限制 (无法添加 5509 个 GitHub IP)
- ✅ 需要访问内网服务 (MySQL/Redis)
- ✅ 有自己的服务器
- ✅ 想要更快的部署速度
- ✅ 需要自定义环境 (预装依赖)

**使用 GitHub 托管 Runner** 如果:
- ✅ 公开仓库 (免费)
- ✅ 构建量小 (< 500 分钟/月)
- ✅ 无特殊网络需求
- ✅ 不想维护服务器

#### 快速部署自托管 Runner

如果您选择自托管 Runner,可以使用专用技能一键部署:

```bash
# 获取 Token
# GitHub 仓库 → Settings → Actions → Self-hosted runners → New runner
# 复制 Token

# SSH 登录服务器
ssh ubuntu@YOUR_SERVER_IP

# 一键部署 (需要 sudo 权限)
bash /path/to/scripts/deploy-github-runner.sh
```

详细文档: [github-actions-runner 技能](../../github-actions-runner/SKILL.md)

#### 配置 Workflow 文件

选择 Runner 后,修改 `.github/workflows/deploy.yml`:

**自托管 Runner**:
```yaml
jobs:
  deploy:
    runs-on: self-hosted  # 使用自己的服务器
```

**GitHub 托管 Runner**:
```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest  # 使用 GitHub 的服务器
```

---

### 方式一: 自动部署 (GitHub Actions)

**优点**: 推送代码即自动部署，无需手动操作
**适用**: 生产环境、团队协作

#### 0. Commit Message 部署规则

**重要**: 使用自托管 Runner 时，通过 commit message 控制部署行为：

| Commit Message 包含 | 部署内容 | 示例 |
|-------------------|---------|------|
| `deploy-all` | 前端 + 后端 | `feat: 新功能 deploy-all` |
| `deploy-frontend` | 仅前端 | `fix: UI 修复 deploy-frontend` |
| `deploy-backend` | 仅后端 | `fix: API 修复 deploy-backend` |
| `[skip-frontend]` | 跳过前端 | `chore: 配置更新 [skip-frontend]` |
| `[skip-backend]` | 跳过后端 | `docs: 文档更新 [skip-backend]` |
| 无标记 | 不部署 | `feat: 其他更改` |

**最佳实践**:
```bash
# 开发时频繁提交 - 不部署
git commit -m "feat: 添加用户界面"
git commit -m "fix: 修复样式问题"
git push origin main  # 不会触发部署

# 完成功能后 - 部署
git commit -m "feat: 用户模块完成 deploy-all"
git push origin main  # 触发前端+后端部署
```

#### 1. 配置 GitHub Secrets

在 GitHub 仓库: `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

必需的 Secrets:
| Secret 名称 | 说明 | 示例 |
|------------|------|------|
| `SERVER_HOST` | 服务器 IP | `YOUR_SERVER_IP` |
| `SERVER_PORT` | SSH 端口 | `22` |
| `SERVER_USER` | SSH 用户 | `root` |
| `SERVER_SSH_KEY` | SSH 私钥 | 完整私钥内容 |
| `DJANGO_SECRET_KEY` | Django 密钥 | 随机字符串 |
| `DB_NAME` | 数据库名 | `my_database` |
| `DB_USER` | 数据库用户 | `db_user` |
| `DB_PASSWORD` | 数据库密码 | `secure_password` |
| `DOMAIN` | 主域名 | `example.com` |

#### 2. 创建 GitHub Actions 工作流

**重要**: 根据 Runner 类型选择不同的配置：

**方案 A: 自托管 Runner（推荐）**

```yaml
name: 全自动部署

on:
  push:
    branches: [ main ]
  workflow_dispatch:  # 允许手动触发

jobs:
  # 前端部署
  deploy-frontend:
    name: 🎨 部署前端
    runs-on: self-hosted  # 使用自己的服务器
    # 只有 commit message 包含标记时才部署
    if: |
      (
        contains(github.event.head_commit.message, 'deploy-all') == true ||
        contains(github.event.head_commit.message, 'deploy-frontend') == true
      ) &&
      contains(github.event.head_commit.message, '[skip-frontend]') == false

    steps:
      - uses: actions/checkout@v3

      - name: 部署到服务器
        uses: appleboy/ssh-action@v0.1.0
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /var/www/my-project/Project/FrontendProject

            # 清理旧的编译产物（使用 sudo 解决权限问题）
            sudo rm -rf dist/

            # 编译前端
            npm run build:prod

            # 验证编译成功
            if [ ! -d "dist" ]; then
              echo "✗ 编译失败"
              exit 1
            fi

            # 设置权限
            sudo chown -R www-data:www-data dist/
            sudo chmod -R 755 dist/

  # 后端部署
  deploy-backend:
    name: 🔧 部署后端
    runs-on: self-hosted
    if: |
      (
        contains(github.event.head_commit.message, 'deploy-all') == true ||
        contains(github.event.head_commit.message, 'deploy-backend') == true
      ) &&
      contains(github.event.head_commit.message, '[skip-backend]') == false

    steps:
      - uses: actions/checkout@v3

      - name: 部署后端
        uses: appleboy/ssh-action@v0.1.0
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /var/www/my-project/Project/BackendProject

            # 拉取代码
            git pull origin main

            # 数据库迁移
            python manage.py makemigrations
            python manage.py migrate

            # 重启服务
            sudo supervisorctl restart my-project:*
```

**方案 B: GitHub 托管 Runner**

```yaml
name: Auto Deploy

on:
  push:
    branches: [ main ]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest  # 使用 GitHub 的服务器
    steps:
      - name: Deploy to server
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.SERVER_HOST }}
          port: ${{ secrets.SERVER_PORT }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          script: |
            cd /www/wwwroot/my-project
            git pull origin main
            # ... 其他部署命令
```

#### 3. 自托管 Runner 关键配置

**权限处理**:
```yaml
# 前端编译时需要删除旧的 dist 目录
# 如果 dist 是 www-data 用户所有，github-runner 用户需要 sudo
sudo rm -rf dist/

# 确保编译后文件权限正确
sudo chown -R www-data:www-data dist/
sudo chmod -R 755 dist/
```

**确保 Runner 用户有 sudo 权限**:
```bash
# 在服务器上配置
echo "github-runner ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/github-runner
sudo chmod 440 /etc/sudoers.d/github-runner
```

#### 4. 常见权限问题及解决方案

**问题 1: 前端编译权限错误** ❗ 最常见

错误信息：
```
EACCES: permission denied, rmdir '/var/www/my-project/Project/FrontendProject/dist/assets'
[vite:prepare-out-dir] Build failed
```

**原因**:
- `dist` 目录属于 `www-data` 用户（Nginx 运行用户）
- `github-runner` 用户无法删除 `www-data` 的文件
- Vite 编译前需要清空 `dist` 目录

**解决方案**:
```yaml
# 方案 A: 编译前使用 sudo 删除（推荐）
- name: 清理旧的编译产物
  run: sudo rm -rf dist/

# 方案 B: 修改目录所有者
- name: 修改目录权限
  run: |
    # 临时修改所有者为 github-runner
    sudo chown -R github-runner:github-roworker .
    npm run build:prod
    # 编译后改回 www-data
    sudo chown -R www-data:www-data dist/
```

**问题 2: Django 静态文件收集权限**

错误信息：
```
PermissionError: [Errno 13] Permission denied: '/var/www/my-project/static/admin'
```

**原因**: 静态文件目录权限不足

**解决方案**:
```yaml
- name: 收集静态文件
  run: |
    # 使用 sudo 收集静态文件
    sudo python manage.py collectstatic --noinput

    # 设置正确的所有者
    sudo chown -R www-data:www-data static/
    sudo chmod -R 755 static/
```

**问题 3: git pull 权限错误**

错误信息：
```
error: cannot open .git/ORIG_HEAD: Permission denied
```

**原因**: `.git` 目录权限问题

**解决方案**:
```bash
# 在服务器上修复 .git 目录权限
cd /var/www/my-project
sudo chown -R github-runner:github-runner .git/
```

**问题 4: Supervisor 重启失败**

错误信息：
```
sudo: supervisorctl: command not found
```

**原因**: Supervisor 不在 PATH 中

**解决方案**:
```yaml
- name: 重启服务
  run: |
    # 使用完整路径
    /usr/bin/supervisorctl restart my-project:*

    # 或使用 sudo -E 保留环境变量
    sudo -E supervisorctl restart my-project:*
```

#### 5. 权限检查清单

部署前检查：
```bash
# 1. 检查 Runner 用户
ssh ubuntu@YOUR_SERVER
id github-runner  # 确认用户存在

# 2. 检查 sudo 权限
sudo -u github-runner sudo -n whoami
# 应该返回: root

# 3. 检查目录权限
ls -la /var/www/my-project/Project/FrontendProject/dist
# 应该属于 www-data:www-data

# 4. 测试删除权限
sudo -u github-runner bash -c "cd /var/www/my-project/Project/FrontendProject && sudo rm -rf test_dir && echo '✓ sudo 权限正常'"
# 应该显示: ✓ sudo 权限正常

# 5. 检查 .git 目录
ls -la /var/www/my-project/.git/HEAD
# 应该可读
```

#### 6. Workflow 文件管理

**最佳实践**:
- ✅ 只保留一个主要的部署 workflow（如 `deploy-all.yml`）
- ✅ 删除测试用的 workflow（避免每次推送都触发）
- ✅ 使用清晰的 workflow 名称和 job 名称
- ✅ 添加注释说明触发条件

**避免的问题**:
```yaml
# ❌ 错误：多个 workflow 同时触发
# test-runner.yml     - 每次 push 都运行
# deploy-all.yml      - 每次 push 都检查是否部署

# ✅ 正确：只保留必要的 workflow
# deploy-all.yml      - 唯一的部署 workflow
```

#### 7. 推送代码触发部署

```bash
# 开发时 - 不部署
git add .
git commit -m "feat: 添加新功能"
git push origin main  # 不会触发部署

# 完成后 - 部署
git add .
git commit -m "feat: 功能完成 deploy-all"
git push origin main  # 触发前端+后端部署
```

### 方式二: 手动部署 (脚本)

**优点**: 完全控制，适合调试
**适用**: 开发环境、首次部署

```bash
# 完整部署
bash scripts/deploy.sh --full

# 仅更新后端
bash scripts/deploy.sh --backend

# 仅更新前端
bash scripts/deploy.sh --frontend

# 查看状态
bash scripts/deploy.sh --status

# 查看日志
bash scripts/deploy.sh --logs
```

### 方式三: 交互式部署

```bash
# 交互式配置向导
bash scripts/init-config.sh

# 按提示输入配置信息
# 1. 服务器信息
# 2. GitHub 仓库信息
# 3. 数据库配置
# 4. 域名配置
# 5. 其他配置

# 自动生成配置文件并部署
```

## 📝 部署步骤说明

### 初始化部署 (首次)

```bash
# 1. 系统依赖安装
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3-pip mysql-server redis-server nginx git supervisor certbot python3-certbot-nginx

# 2. 创建项目目录
sudo mkdir -p ${PROJECT_ROOT}/{backend,frontend,logs,backups}

# 3. 配置 MySQL
sudo mysql -e "CREATE DATABASE ${DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
sudo mysql -e "CREATE USER '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';"
sudo mysql -e "GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'localhost';"
sudo mysql -e "FLUSH PRIVILEGES;"

# 4. 克隆代码
cd ${PROJECT_ROOT}
git clone https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}.git backend
git clone https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}-frontend.git frontend

# 5. 部署后端
cd backend/Project/BackendProject
python3.10 -m venv ${BACKEND_VENV_NAME}
source ${BACKEND_VENV_NAME}/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 编辑配置
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput

# 6. 部署前端
cd ${PROJECT_ROOT}/frontend/Project/FrontendProject
npm install
npm run build

# 7. 配置 Nginx
sudo cp templates/nginx.conf /etc/nginx/conf.d/${PROJECT_NAME}.conf
# 编辑配置中的域名和路径
sudo nginx -t
sudo systemctl restart nginx

# 8. 配置 Supervisor
sudo cp templates/supervisor.conf /etc/supervisor/conf.d/${PROJECT_NAME}.conf
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start ${PROJECT_NAME}:*

# 9. 配置 SSL (有域名时)
sudo certbot --nginx -d ${DOMAIN} -d ${WWW_DOMAIN}
```

### 更新部署 (后续)

```bash
# 使用部署脚本
bash scripts/deploy.sh --update

# 或手动更新
cd ${PROJECT_ROOT}/backend && git pull
cd ${PROJECT_ROOT}/frontend && git pull

# 重启服务
sudo supervisorctl restart ${PROJECT_NAME}:*
sudo nginx -s reload
```

## 🔐 安全配置

### SSH 密钥配置

```bash
# 本地生成密钥
ssh-keygen -t ed25519 -C "your_email@example.com"

# 复制公钥到服务器
ssh-copy-id -i ~/.ssh/id_ed255.pub user@server

# 配置 SSH 别名
cat >> ~/.ssh/config << EOF
Host ${PROJECT_NAME}-server
    HostName ${SERVER_HOST}
    Port ${SERVER_PORT}
    User ${SERVER_USER}
    IdentityFile ~/.ssh/id_ed255
EOF

# 测试连接
ssh ${PROJECT_NAME}-server
```

### 防火墙配置

```bash
# 配置 UFW 防火墙
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ${SERVER_PORT}/tcp  # SSH
sudo ufw allow 80/tcp              # HTTP
sudo ufw allow 443/tcp             # HTTPS
sudo ufw enable
```

### 数据库安全

```bash
# 禁用远程 root 登录
sudo mysql -e "DELETE FROM mysql.user WHERE User='root' AND Host NOT IN ('localhost', '127.0.0.1', '::1');"

# 删除测试数据库
sudo mysql -e "DROP DATABASE IF EXISTS test; DELETE FROM mysql.db WHERE Db='test' OR Db='test\\_%';"

# 刷新权限
sudo mysql -e "FLUSH PRIVILEGES;"
```

## 📊 监控和日志

### 日志位置

| 服务 | 错误日志 | 访问日志 |
|-----|---------|---------|
| Django | `${PROJECT_ROOT}/logs/django-error.log` | `${PROJECT_ROOT}/logs/django-access.log` |
| Nginx | `/var/log/nginx/error.log` | `/var/log/nginx/access.log` |
| Supervisor | journalctl | supervisorctl tail |

### 监控命令

```bash
# 查看所有服务状态
bash scripts/deploy.sh --status

# 实时查看日志
tail -f ${PROJECT_ROOT}/logs/*.log

# Supervisor 状态
sudo supervisorctl status all

# 系统资源
htop
df -h
free -h
```

## 💾 备份和恢复

### 自动备份

```bash
# 配置定时任务 (crontab -e)
# 每天凌晨 2 点备份数据库
0 2 * * * /path/to/scripts/backup.sh --database

# 每周日凌晨 3 点备份文件
0 3 * * 0 /path/to/scripts/backup.sh --files
```

### 手动备份

```bash
# 备份数据库
bash scripts/backup.sh --database

# 备份文件
bash scripts/backup.sh --files

# 完整备份
bash scripts/backup.sh --full
```

### 恢复数据

```bash
# 恢复数据库
mysql -u ${DB_USER} -p ${DB_NAME} < backups/db/db_backup_20250105.sql

# 恢复文件
tar -xzf backups/files/files_backup_20250105.tar.gz -C /
```

## 🐛 故障排查

### 常见问题

**问题 1: Django 502 错误**
```bash
# 检查 Django 服务
sudo supervisorctl status ${PROJECT_NAME}:django
sudo supervisorctl tail ${PROJECT_NAME}:django stderr

# 检查 Socket 文件
ls -l /tmp/${PROJECT_NAME}-django.sock
```

**问题 2: 前端空白页**
```bash
# 检查构建
cd ${PROJECT_ROOT}/frontend/Project/FrontendProject
npm run build

# 检查 Nginx 配置
sudo nginx -t
cat /etc/nginx/conf.d/${PROJECT_NAME}.conf
```

**问题 3: 数据库连接失败**
```bash
# 测试连接
mysql -u ${DB_USER} -p ${DB_NAME}

# 检查 MySQL 状态
sudo systemctl status mysql

# 检查 .env 配置
cat ${PROJECT_ROOT}/backend/.env
```

**问题 4: GitHub Actions 失败**
```bash
# 检查 Secrets 是否正确
# 仓库 → Settings → Secrets

# 查看运行日志
# 仓库 → Actions → 选择运行记录

# 本地测试 SSH 连接
ssh -i ~/.ssh/id_ed255 -p ${SERVER_PORT} ${SERVER_USER}@${SERVER_HOST}
```

## 📚 参考文档

- [部署前准备清单](DEPLOYMENT_CHECKLIST.md) - 详细的准备步骤
- [配置模板](templates/) - 各种配置文件模板
- [部署脚本](scripts/) - 自动化部署脚本

## 🔄 多项目管理

如果你需要管理多个项目，可以为每个项目创建独立的配置文件:

```bash
# 项目 1
cp templates/deploy.config.env project1.config.env
# 编辑 project1.config.env

# 项目 2
cp templates/deploy.config.env project2.config.env
# 编辑 project2.config.env

# 使用不同配置部署
bash scripts/deploy.sh --config project1.config.env
bash scripts/deploy.sh --config project2.config.env
```

## ⚙️ 高级配置

### Docker 部署 (可选)

如果需要使用 Docker 部署，可以创建 `docker-compose.yml`:

```yaml
version: '3.8'
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=mysql://db:3306/${DB_NAME}
    depends_on:
      - db

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend

  db:
    image: mysql:8.0
    environment:
      - MYSQL_DATABASE=${DB_NAME}
      - MYSQL_USER=${DB_USER}
      - MYSQL_PASSWORD=${DB_PASSWORD}
    volumes:
      - db_data:/var/lib/mysql

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"

volumes:
  db_data:
```

### CI/CD 管道 (可选)

支持多种 CI/CD 平台:
- GitHub Actions
- GitLab CI
- Jenkins
- CircleCI

## 💡 最佳实践

1. **环境分离**: 开发、测试、生产环境使用不同配置
2. **版本控制**: 所有配置文件纳入版本控制 (敏感信息使用 Secrets)
3. **自动化**: 尽可能使用 GitHub Actions 自动部署
4. **监控**: 配置日志和监控系统
5. **备份**: 定期备份，测试恢复流程
6. **文档**: 保持文档更新，记录变更
7. **安全**: 定期更新系统和依赖，使用强密码

## 🆘 获取帮助

如遇问题，按以下顺序排查:

1. 查看相关日志
2. 检查配置文件
3. 参考故障排查章节
4. 查看项目 GitHub Issues
5. 联系技术支持
