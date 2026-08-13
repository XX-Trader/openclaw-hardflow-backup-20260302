---
name: db-deploy
displayName: "服务器部署"
version: "1.0.0"
description: 全栈项目自动部署技能。支持 Django 后端、Vue3 前端、MySQL 数据库、Redis 缓存、Nginx 反向代理和 Python 脚本的完整部署流程。当用户请求部署、更新、或维护 Web 项目时使用此技能。支持多仓库配置、GitHub Actions 自动部署、SSL 证书自动配置。
description_zh: "db-deploy技能，详见 SKILL.md"
author: "maintainers"
license: "MIT"
updated_at: "2026-01-25"

triggers:
  keywords:
    - "部署项目"
    - "部署到服务器"
    - "生产部署"
    - "部署到生产"
    - "线上部署"
    - "服务器部署"
    - "nginx部署"
    - "上线"
  auto_trigger: true
  confidence_threshold: 0.8

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
# 申请 Let's Encrypt 证书（包含常见子域名：根域名 @、www、api）
sudo certbot --nginx \
  -d example.com \
  -d www.example.com \
  -d api.example.com

# 自动续期 (已自动配置)
sudo certbot renew --dry-run
```

**DNS 配置参考**:
```
类型    主机记录    记录值              说明
A       @          YOUR_SERVER_IP      根域名 (example.com)
A       www        YOUR_SERVER_IP      www 子域名 (www.example.com)
A       api        YOUR_SERVER_IP      api 子域名 (api.example.com)
```

**扩展其他子域名**:
如果需要添加更多子域名（如 `app`、`admin`、`staging` 等）:
```bash
# 重新申请证书，添加新的 -d 参数
sudo certbot --nginx \
  -d example.com \
  -d www.example.com \
  -d api.example.com \
  -d app.example.com \
  -d admin.example.com
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

## 🚀 基于 GitHub Actions 的部署流程（推荐）

### 部署流程概览

```
┌─────────────────────────────────────────────────────────────┐
│              GitHub Actions 自动部署完整流程                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  本地开发                              服务器               │
│  ─────────                              ───────               │
│                                                             │
│  1. 创建部署 commit                                        │
│     git commit -m "feat: xxx deploy-all"                   │
│           │                                                 │
│           ↓                                                 │
│  2. 推送到 GitHub                                          │
│     git push origin main                                   │
│           │                                                 │
│           ↓                                                 │
│  3. GitHub Actions 触发                                    │
│     - 检出代码                                             │
│     - 连接服务器                                           │
│     - 执行部署脚本                                         │
│           │                                                 │
│           ↓                                                 │
│  4. 等待部署完成                                           │
│     gh run watch                                          │
│           │                                                 │
│           ↓                                                 │
│  5. 查看部署日志                                           │
│     gh run view --log                                      │
│           │                                                 │
│           ↓                                                 │
│  6. 如果失败，SSH 登录服务器排查                            │
│     ssh server                                             │
│     - 查看错误日志                                         │
│     - 修复问题                                             │
│     - 手动执行失败的步骤                                   │
│           │                                                 │
│           ↓                                                 │
│  7. 验证部署成功                                           │
│     curl https://your-domain.com/                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 步骤 1: 触发部署

#### 1.1 使用 Commit Message 触发

根据部署需求选择合适的 commit message 关键字：

| 关键字 | 部署内容 | 使用场景 |
|--------|---------|----------|
| `deploy-all` | 前端 + 后端 | 功能完成，完整部署 |
| `deploy-frontend` | 仅前端 | UI 修改或样式调整 |
| `deploy-backend` | 仅后端 | API 修改或业务逻辑 |
| `[skip-frontend]` | 跳过前端 | 仅后端改动 |
| `[skip-backend]` | 跳过后端 | 仅前端改动 |

**示例**：
```bash
# 完整部署
git commit -m "feat: 新增用户管理功能 deploy-all"

# 仅前端部署
git commit -m "fix: 修复登录页面样式 deploy-frontend"

# 仅后端部署
git commit -m "fix: 修复 API 接口问题 deploy-backend"

# 跳过前端部署
git commit -m "chore: 更新数据库配置 [skip-frontend]"
```

#### 1.2 推送代码

```bash
# 推送到远程仓库
git push origin main

# 或使用 gh 命令行工具
gh repo view --web  # 在浏览器中查看仓库
```

### 步骤 2: 监控部署进度

#### 2.1 查看运行状态

```bash
# 查看最近的运行记录
gh run list --limit 5

# 查看特定运行的详情
gh run view <run-id>

# 实时监控部署进度（推荐）
gh run watch <run-id> --interval 5
```

**输出示例**：
```
✓ 🎨 部署前端 in 45s
✓ 🔧 部署后端 in 30s
✓ 📊 部署汇总 in 5s
```

#### 2.2 判断部署状态

- `✓ 成功` - 所有步骤正常完成
- `X 失败` - 某个步骤出错，需要排查
- `⏭️ 跳过` - 符合跳过条件（如 commit message 包含 `[skip-frontend]`）

### 步骤 3: 查看部署日志

#### 3.1 查看完整日志

```bash
# 查看特定运行的日志
gh run view <run-id> --log

# 查看特定 job 的日志
gh run view --job=<job-id> --log

# 保存日志到文件
gh run view <run-id> --log > deploy-log.txt
```

#### 3.2 关键日志位置

**前端部署关键日志**：
```
🎨 部署前端
  → 清理旧的编译产物
  → 安装依赖 (npm install)
  → 编译前端 (npm run build:prod)
  → 设置权限
```

**后端部署关键日志**：
```
🔧 部署后端
  → 拉取代码 (git pull)
  → 更新依赖 (pip install)
  → 数据库迁移 (python manage.py migrate)
  → 重启服务 (supervisorctl restart)
```

### 步骤 4: 排查部署失败

#### 4.1 常见失败原因

**前端失败**：
1. `npm install` 失败 - 依赖安装错误
2. `npm run build` 失败 - 编译错误
3. 权限错误 - 无法删除/创建文件

**后端失败**：
1. `git pull` 冲突 - 代码合并问题
2. 数据库迁移失败 - 字段冲突或 SQL 错误
3. 依赖安装失败 - pip 安装错误
4. 服务重启失败 - Supervisor 或 Gunicorn 错误

#### 4.2 排查步骤

**步骤 1: 分析错误日志**

```bash
# 查看失败日志
gh run view <run-id> --log | grep -A 20 "err:"

# 保存完整日志以便分析
gh run view <run-id> --log > error-log.txt
```

**步骤 2: SSH 登录服务器**

```bash
# 使用自定义 SSH 配置
~/.ssh/my-ssh.sh HOST_A

# 或直接使用 ssh 命令
ssh ubuntu@YOUR_SERVER_IP
```

**步骤 3: 在服务器上排查**

```bash
# 查看项目目录
cd /var/www/DaBaiLiangHua_quant

# 检查 Git 状态
git status
git log -1 --oneline

# 查看前端编译日志
cd Project/ShengBeiVue
npm run build:prod 2>&1 | tee build.log

# 查看后端迁移日志
cd Project/ShengBeiDjango
python3 manage.py migrate --plan  # 查看迁移计划
python3 manage.py migrate --verbosity 2  # 详细输出
```

**步骤 4: 手动修复并重新部署**

```bash
# 前端问题修复
cd Project/ShengBeiVue
npm install  # 重新安装依赖
npm run build:prod  # 重新构建
sudo chown -R www-data:www-data dist/  # 修复权限

# 后端问题修复
cd Project/ShengBeiDjango
git pull origin main  # 拉取代码
python3 manage.py migrate  # 执行迁移
sudo supervisorctl restart django  # 重启服务
```

### 步骤 5: Django 迁移文件检查（重要！）

Django 迁移文件很容易出问题，部署前必须检查！

#### 5.1 检查新增的迁移文件

**在推送代码前检查**：
```bash
# 本地检查
cd Project/ShengBeiDjango

# 查看未应用的迁移
python manage.py showmigrations | grep -E "^\[ \]"

# 查看新增的迁移文件
ls -lt pm_robot/migrations/*.py | head -5
```

#### 5.2 验证迁移文件内容

**检查字段定义**：
```bash
# 查看最新迁移文件的内容
cat pm_robot/migrations/00XX_migration_name.py

# 重点检查：
# 1. models 字段类型是否正确
# 2. default 值是否合理
# 3. null 约束是否正确
# 4. 外键关系是否正确
```

**常见问题**：
1. ❌ 字段缺少 `default` 值（非空字段必须提供）
2. ❌ 字段类型与数据库不兼容
3. ❌ 外键引用的表不存在
4. ❌ 迁移依赖关系错误

#### 5.3 测试迁移

**在本地或测试环境先测试**：
```bash
# 查看迁移计划
python manage.py migrate --plan

# 模拟执行（不真正执行）
python manage.py migrate --fake-initial

# 真正执行
python manage.py migrate --verbosity 2
```

#### 5.4 数据库字段冲突处理

如果遇到字段已存在或缺失：

**情况 1: 字段已存在**
```bash
# 错误信息：duplicate column name: xxx
# 解决方案：标记迁移为已应用
python manage.py migrate <app_name> --fake <migration_name>
```

**情况 2: 字段缺失**
```bash
# 错误信息：column xxx does not exist
# 解决方案：手动添加字段
mysql -u user -p database << SQL
ALTER TABLE table_name
ADD COLUMN column_name COLUMN_TYPE
COMMENT '字段说明';
SQL
```

**情况 3: 字段类型不匹配**
```bash
# 错误信息：type mismatch
# 解决方案：修改字段类型
mysql -u user -p database << SQL
ALTER TABLE table_name
MODIFY COLUMN column_name NEW_COLUMN_TYPE;
SQL
```

#### 5.5 迁移文件最佳实践

1. **保持迁移顺序** - 确保迁移文件按时间顺序命名
2. **避免数据丢失** - 添加字段前先备份数据
3. **提供默认值** - 非空字段必须有合理的默认值
4. **测试迁移** - 在本地先测试，确认无误后再推送
5. **记录变更** - 在迁移文件中添加注释说明变更原因

### 步骤 6: 验证部署成功

#### 6.1 自动验证

```bash
# 检查服务状态
sudo supervisorctl status django
sudo systemctl status nginx
sudo systemctl status mysql
sudo systemctl status redis

# 检查端口监听
sudo ss -tlnp | grep -E ':(80|443|8000|3306|6379)'

# 测试 API 访问
curl -I http://localhost/api/
curl -I https://dabaiquant.com/api/
```

#### 6.2 功能验证

访问网站并测试关键功能：
1. 登录功能
2. 数据查询
3. 表单提交
4. 文件上传/下载
5. WebSocket 连接（如果使用）

### 步骤 7: 部署后清理

```bash
# 清理临时文件
rm -rf *.pyc
rm -rf __pycache__/
find . -type d -name "__pycache__" -exec rm -rf {} +

# 清理 Git 日志（可选）
git gc --prune=now

# 更新文档
# 记录本次部署的变更和遇到的问题
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

### Django 迁移问题（常见且重要）

Django 迁移文件是部署中最容易出现问题的地方，需要特别关注！

#### 问题 1: 数据库字段不存在

**错误信息**：
```
django.db.utils.OperationalError: (1054, "Unknown column 'table_name.field_name' in 'field list'")
```

**原因**：
- 代码中定义了新字段，但数据库中不存在
- 迁移文件未执行或执行失败

**解决方案**：
```bash
# 1. 检查待执行的迁移
cd /var/www/DaBaiLiangHua_quant/Project/ShengBeiDjango
python manage.py showmigrations | grep -E "^\[ \]"

# 2. 查看迁移计划
python manage.py migrate --plan

# 3. 执行迁移
python manage.py migrate --verbosity 2

# 4. 如果迁移失败，手动添加字段
mysql -u user -p database << SQL
ALTER TABLE table_name
ADD COLUMN field_name field_type
NOT NULL DEFAULT default_value
COMMENT '字段说明';
SQL
```

#### 问题 2: 字段已存在

**错误信息**：
```
django.db.utils.OperationalError: (1060, "Duplicate column name 'field_name'")
```

**原因**：
- 数据库中已有该字段，但迁移文件认为需要添加
- 可能是手动修改了数据库，但未更新迁移状态

**解决方案**：
```bash
# 方案 1: 标记迁移为已应用（如果字段已存在且正确）
python manage.py migrate app_name --fake migration_name

# 方案 2: 删除字段后重新迁移（如果字段定义不正确）
mysql -u user -p database << SQL
ALTER TABLE table_name DROP COLUMN field_name;
SQL

# 然后重新执行迁移
python manage.py migrate
```

#### 问题 3: 迁移依赖冲突

**错误信息**：
```
django.db.migrations.exceptions.InconsistentMigrationHistory
```

**原因**：
- 迁移历史记录与实际数据库状态不一致
- 可能是不同分支合并导致的迁移冲突

**解决方案**：
```bash
# 方案 1: 重建迁移历史（仅开发环境）
python manage.py migrate app_name zero
python manage.py migrate app_name --fake-initial

# 方案 2: 标记所有迁移为已应用（生产环境谨慎使用）
python manage.py migrate --fake

# 方案 3: 删除数据库并重新迁移（仅开发环境）
mysql -u user -p << SQL
DROP DATABASE database_name;
CREATE DATABASE database_name CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
SQL
python manage.py migrate
```

#### 问题 4: 非空字段无默认值

**错误信息**：
```
django.db.migrations.exceptions.InconsistentMigrationHistory:
You are trying to add a non-nullable field 'field_name' without a default
```

**原因**：
- 添加非空字段时，未提供默认值
- Django 不知道如何为现有记录填充该字段

**解决方案**：
```python
# 迁移文件中需要提供默认值
# 方案 1: 提供默认值
operations = [
    migrations.AddField(
        model_name='mymodel',
        name='field_name',
        field=models.IntegerField(default=0),  # 添加 default
    ),
]

# 方案 2: 分两步迁移（先允许空，再填充数据）
# Step 1: 添加允许 NULL 的字段
migrations.AddField(
    model_name='mymodel',
    name='field_name',
    field=models.IntegerField(null=True),
),
# Step 2: 迁移数据后改为非空
migrations.RunPython(migrate_data),
migrations.AlterField(
    model_name='mymodel',
    name='field_name',
    field=models.IntegerField(default=0),
),
```

#### 问题 5: 外键约束失败

**错误信息**：
```
django.db.utils.IntegrityError: (1452, 'Cannot add or update a child row:
a foreign key constraint fails')
```

**原因**：
- 外键引用的表或记录不存在
- 数据不一致

**解决方案**：
```bash
# 1. 检查外键表是否存在
mysql -u user -p database -e "SHOW TABLES LIKE 'related_table';"

# 2. 检查外键记录是否存在
mysql -u user -p database -e "SELECT COUNT(*) FROM related_table;"

# 3. 清理无效数据或添加缺失记录
mysql -u user -p database << SQL
-- 删除无效的外键引用
DELETE FROM table_name WHERE foreign_key_field NOT IN (SELECT id FROM related_table);

-- 或添加缺失的记录
INSERT INTO related_table (id, name) VALUES (missing_id, 'Default Name');
SQL

# 4. 重新执行迁移
python manage.py migrate
```

#### 迁移文件检查清单

**推送代码前必须检查**：

```bash
# 1. 检查是否有未提交的迁移
git status pm_robot/migrations/

# 2. 查看迁移文件内容
cat pm_robot/migrations/00XX_*.py

# 3. 检查字段定义
# - 字段类型是否正确
# - default 值是否合理
# - null 约束是否正确
# - 外键关系是否正确

# 4. 本地测试迁移
python manage.py migrate --plan
python manage.py migrate --fake-initial

# 5. 验证表结构
python manage.py dbshell
DESCRIBE table_name;
EXIT;

# 6. 确认无误后再推送
git add pm_robot/migrations/
git commit -m "feat: add migration for xxx"
git push origin main
```

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

**问题 5: 前端编译失败（依赖缺失）**
```bash
# 登录服务器
ssh ubuntu@YOUR_SERVER_IP

# 进入前端目录
cd /var/www/DaBaiLiangHua_quant/Project/ShengBeiVue

# 重新安装依赖
npm install

# 如果特定包缺失，手动安装
npm install package-name

# 重新构建
npm run build:prod
```

**问题 6: 后端服务无法启动**
```bash
# 查看详细错误日志
sudo supervisorctl tail django stderr

# 常见原因：
# 1. settings_local.py 配置错误
#    - 解决：删除或重命名 settings_local.py
# 2. 数据库连接失败
#    - 解决：检查 .env 配置，测试数据库连接
# 3. 端口被占用
#    - 解决：sudo lsof -i :8000 查看并杀死占用进程
# 4. Python 依赖缺失
#    - 解决：pip install -r requirements.txt
```

### 快速排查命令

```bash
# 一键检查所有服务
sudo supervisorctl status all
sudo systemctl status nginx mysql redis --no-pager

# 查看所有日志
tail -f /var/log/supervisor/*.log
tail -f /var/log/nginx/*.log

# 检查端口监听
sudo ss -tlnp | grep -E ':(80|443|8000|3306|6379)'

# 测试网站访问
curl -I http://localhost/
curl -I https://your-domain.com/
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
