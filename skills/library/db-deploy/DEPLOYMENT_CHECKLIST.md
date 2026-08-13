# 全栈项目部署前准备清单

> 本清单适用于任何基于 Django + Vue/React 的全栈项目部署

## 📋 快速开始

**推荐方式**: 使用交互式配置向导
```bash
bash scripts/init-config.sh
```

向导会引导你完成所有配置并自动生成 `deploy.config.env` 配置文件。

---

## 📝 必需信息收集

### 1. 项目基本信息

| 配置项 | 说明 | 示例 |
|-------|------|------|
| **项目名称** | 用于标识项目 | `my-project` |
| **项目类型** | 部署类型 | `fullstack` / `backend` / `frontend` |
| **项目根目录** | 服务器上的部署路径 | `/www/wwwroot/my-project` |

---

### 2. 服务器信息

| 配置项 | 说明 | 示例 |
|-------|------|------|
| **服务器 IP** | 公网 IP 地址 | `YOUR_SERVER_IP` |
| **SSH 端口** | SSH 服务端口 | `22` (建议修改) |
| **SSH 用户** | 登录用户名 | `root` |
| **认证方式** | 密钥或密码 | **推荐使用 SSH 密钥** |

#### SSH 密钥配置（推荐）

```bash
# 1. 本地生成密钥对
ssh-keygen -t ed25519 -C "your_email@example.com"

# 2. 将公钥复制到服务器
ssh-copy-id -i ~/.ssh/id_ed255.pub user@server_ip

# 3. 配置 SSH 别名
cat >> ~/.ssh/config << 'EOF'
Host my-project-server
    HostName YOUR_SERVER_IP
    Port YOUR_SSH_PORT
    User YOUR_USERNAME
    IdentityFile ~/.ssh/id_ed255
    ServerAliveInterval 60
    ServerAliveCountMax 3
EOF

# 4. 测试连接
ssh my-project-server
```

**验证连接**:
```bash
ssh -i ~/.ssh/id_ed255 -p PORT user@host "uname -a"
```

---

### 3. GitHub 仓库信息

| 配置项 | 说明 | 示例 |
|-------|------|------|
| **GitHub 用户/组织** | 所有者 | `github-username` |
| **仓库名称** | 仓库名 | `my-project` |
| **部署分支** | 部署使用的分支 | `main` / `master` |
| **是否前后端分离** | 前后端是否在不同仓库 | `Y` / `N` |

如果前后端分离，还需提供:
| 配置项 | 说明 | 示例 |
|-------|------|------|
| **前端仓库名** | 前端仓库 | `my-project-frontend` |
| **前端部署分支** | 前端部署分支 | `main` |

---

### 4. 数据库信息

#### MySQL 配置

| 配置项 | 说明 | 示例 |
|-------|------|------|
| **数据库类型** | `mysql` / `postgresql` / `sqlite` | `mysql` |
| **数据库名** | 数据库名称 | `my_database` |
| **数据库用户** | 数据库用户 | `db_user` |
| **数据库密码** | 16 位以上随机密码 | `SecurePass123!@#` |
| **数据库主机** | 通常是 localhost | `localhost` |
| **数据库端口** | MySQL 默认 3306 | `3306` |

**生成安全密码**:
```bash
# 方法 1: OpenSSL
openssl rand -base64 24

# 方法 2: Python
python3 -c "import secrets; print(secrets.token_urlsafe(24))"

# 方法 3: 在线工具
# 访问: https://generate-random.org/password-generator
```

---

### 5. Django 配置（如果使用 Django）

| 配置项 | 说明 | 示例 |
|-------|------|------|
| **SECRET_KEY** | 50 位随机字符串 | `django-insecure-xxx...` |
| **Settings 模块** | settings 文件路径 | `myproject.settings` |
| **DEBUG** | 调试模式 | `False` (生产) |
| **ALLOWED_HOSTS** | 允许的主机 | 留空自动使用域名 |

**生成 Django SECRET_KEY**:
```bash
# 方法 1: Django 内置
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# 方法 2: 使用脚本
# 配置向导会自动生成
```

---

### 6. 域名信息（可选）

如果有域名，配置以下信息:

| 配置项 | 说明 | 示例 |
|-------|------|------|
| **是否使用域名** | `Y` / `N` | `Y` |
| **主域名** | 主域名 | `example.com` |
| **www 子域名** | www 域名 | `www.example.com` |
| **API 子域名** | API 域名（可选） | `api.example.com` |
| **启用 SSL** | 是否使用 HTTPS | `Y` (推荐) |
| **SSL 邮箱** | 证书联系邮箱 | `admin@example.com` |

**域名 DNS 解析配置**:

在域名服务商（阿里云、腾讯云、GoDaddy 等）添加 A 记录:

```
类型    主机记录    记录值              TTL
A       @          YOUR_SERVER_IP      600
A       www        YOUR_SERVER_IP      600
A       api        YOUR_SERVER_IP      600
```

**验证 DNS 解析**:
```bash
# 等待 5-10 分钟后验证
ping example.com
nslookup example.com
dig example.com

# Windows
nslookup example.com
```

---

## 🔑 GitHub Personal Access Token (PAT)

### 申请 GitHub PAT

**用途**: GitHub Actions 自动部署时访问仓库

**申请步骤**:

1. 访问: https://github.com/settings/tokens
2. 点击 **"Generate new token"** → **"Generate new token (classic)"**
3. 设置名称: `my-project-deploy-token`
4. **勾选权限 (Scopes)**:
   - ✅ `repo` - 完整仓库访问权限
   - ✅ `workflow` - GitHub Actions 权限
   - ✅ `write:packages` - 如果有私有包
5. 点击生成并**立即复制**（只显示一次）

**PAT 权限说明**:

| 权限 | 说明 |
|-----|------|
| `repo` | 读写代码仓库 |
| `workflow` | 管理 GitHub Actions |
| `admin:repo_hook` | 管理 Webhook (可选) |

---

## 🔧 本地开发环境

### 1. VSCode 必装插件

| 插件名称 | 用途 | 安装命令 |
|---------|------|----------|
| **Python** | Python 语法高亮、智能提示 | `ext install ms-python.python` |
| **Pylance** | Python 语言服务器 | `ext install ms-python.vscode-pylance` |
| **Django** | Django 模板、标签支持 | `ext install batisteo.vscode-django` |
| **Vue - Official** | Vue3 语法支持 | `ext install Vue.volar` |
| **ESLint** | JavaScript/Vue 代码检查 | `ext install dbaeumer.vscode-eslint` |
| **Prettier** | 代码格式化 | `ext install esbenp.prettier-vscode` |
| **GitLens** | Git 增强 | `ext install eamodio.gitlens` |
| **Remote - SSH** | 远程服务器开发 | `ext install ms-vscode-remote.remote-ssh` |
| **Thunder Client** | API 测试 | `ext install rangav.vscode-thunder-client` |

### 2. 本地环境版本要求

| 软件 | 最低版本 | 推荐版本 | 检查命令 |
|-----|---------|---------|---------|
| **Python** | 3.10 | 3.10+ | `python --version` |
| **Node.js** | 16 | 18 LTS / 20 LTS | `node --version` |
| **npm** | 8 | 10 | `npm --version` |
| **Git** | 2.30 | 2.40+ | `git --version` |

---

## 🚀 GitHub 仓库设置

### 1. 创建 GitHub 仓库

**方式一**: 通过 GitHub 网页创建
1. 访问: https://github.com/new
2. 仓库名: `my-project` (或你的项目名)
3. 可见性: **Private** (私有)
4. **不要**初始化 README (本地已有代码)

**方式二**: 使用 GitHub CLI
```bash
# 安装 GitHub CLI
# Windows: scoop install gh
# macOS: brew install gh
# Linux: 参考官方文档

# 登录
gh auth login

# 创建仓库
gh repo create my-project --private --source=. --remote=origin --push
```

### 2. 配置 GitHub Secrets

在 GitHub 仓库: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

#### 必需的 Secrets

| Secret 名称 | 值 | 说明 |
|------------|-----|------|
| `SERVER_HOST` | `YOUR_SERVER_IP` | 服务器 IP |
| `SERVER_PORT` | `22` | SSH 端口 |
| `SERVER_USER` | `root` | SSH 用户 |
| `SERVER_SSH_KEY` | (见下方) | SSH 私钥 |
| `PROJECT_NAME` | `my-project` | 项目名称 |
| `DOMAIN` | `example.com` | 域名 |
| `DB_NAME` | `my_database` | 数据库名 |
| `DB_USER` | `db_user` | 数据库用户 |
| `DB_PASSWORD` | `password` | 数据库密码 |
| `DJANGO_SECRET_KEY` | (见下方) | Django 密钥 |

#### 配置 SERVER_SSH_KEY

**步骤**:
1. 复制本地 SSH 私钥:
   ```bash
   # Windows
   cat ~/.ssh/id_ed255 | clip

   # macOS
   cat ~/.ssh/id_ed255 | pbcopy

   # Linux
   cat ~/.ssh/id_ed255 | xclip -selection clipboard
   ```

2. 在 GitHub 添加 Secret:
   - 名称: `SERVER_SSH_KEY`
   - 值: 粘贴私钥内容（**包括** `-----BEGIN` 和 `-----END` 行）

#### 配置 DJANGO_SECRET_KEY

**生成方法**:
```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 3. 添加 GitHub Actions 工作流

```bash
# 1. 在项目根目录创建工作流目录
mkdir -p .github/workflows

# 2. 复制模板
cp templates/github-action.yml .github/workflows/deploy.yml

# 3. 编辑工作流文件（如需自定义）
vim .github/workflows/deploy.yml

# 4. 提交并推送
git add .github/workflows/deploy.yml
git commit -m "feat: add GitHub Actions deployment workflow"
git push origin main
```

---

## 🖥️ 服务器环境检查

### 1. 服务器基础信息

| 配置项 | 最低要求 | 推荐配置 | 检查命令 |
|-------|---------|---------|---------|
| **操作系统** | Ubuntu 20.04 | Ubuntu 22.04 LTS | `cat /etc/os-release` |
| **内存** | 2GB | 4GB+ | `free -h` |
| **磁盘** | 40GB | 100GB+ | `df -h` |
| **CPU** | 2 核 | 4 核+ | `nproc` |

### 2. 网络端口检查

| 端口 | 用途 | 状态 |
|-----|------|------|
| **22** | SSH | 开放 |
| **80** | HTTP | 开放 |
| **443** | HTTPS | 开放 |
| **3306** | MySQL | 本地 |
| **6379** | Redis | 本地 |

**检查命令**:
```bash
sudo netstat -tuln | grep -E ':(22|80|443|3306|6379)\s'
```

### 3. 防火墙配置

```bash
# 配置 UFW 防火墙
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable

# 查看状态
sudo ufw status verbose
```

---

## 📊 第三方服务配置（可选）

### 1. 外部服务 API（如需）

如果项目需要连接外部服务 API：

| 配置项 | 说明 |
|-------|------|
| **服务名称** | 如: source-control、notification 等 |
| **API Key** | 通过环境变量或密钥服务注入 |
| **API Secret** | 不写入仓库或部署日志 |
| **Endpoint** | 使用环境对应的正式地址 |
| **权限** | 只授予当前功能所需最小权限 |
| **禁止权限** | 禁止无关管理权限 |

### 2. 邮件服务（如需）

| 配置项 | 说明 | 示例 |
|-------|------|------|
| **SMTP 主机** | 邮件服务器 | `smtp.gmail.com` |
| **SMTP 端口** | SMTP 端口 | `587` |
| **SMTP 用户** | 邮箱地址 | `your@gmail.com` |
| **SMTP 密码** | 应用密码 | `app-password` |

### 3. 监控服务（如需）

| 服务 | 用途 |
|-----|------|
| **Sentry** | 错误追踪 |
| **Datadog** | 应用监控 |
| **New Relic** | 性能监控 |
| **Slack** | 团队通知 |

---

## ✅ 部署前最终确认

使用以下清单确认所有准备工作完成:

### 服务器配置
- [ ] 服务器 IP 和 SSH 连接测试成功
- [ ] SSH 密钥已配置（推荐）
- [ ] 服务器资源满足要求
- [ ] 防火墙已配置

### 代码仓库
- [ ] GitHub 仓库已创建
- [ ] 本地代码已推送到 GitHub
- [ ] GitHub Secrets 已全部配置
- [ ] GitHub Actions 工作流已添加

### 域名配置（如适用）
- [ ] 域名已购买
- [ ] DNS 解析已配置
- [ ] 解析已生效（ping 测试通过）

### 数据库
- [ ] 数据库密码已生成并保存
- [ ] Django SECRET_KEY 已生成

### 本地环境
- [ ] VSCode 必装插件已安装
- [ ] 本地开发环境版本符合要求

### 安全
- [ ] 所有密码和密钥已安全保存
- [ ] 敏感信息未提交到代码库

---

## 🎯 快速部署流程

准备就绪后，按以下步骤部署:

### 方式一: 使用配置向导（推荐）

```bash
# 1. 运行配置向导
bash scripts/init-config.sh

# 2. 按提示输入配置信息

# 3. 生成配置文件后部署
bash scripts/deploy.sh --config deploy.config.env
```

### 方式二: 手动部署

```bash
# 1. 复制配置模板
cp templates/deploy.config.env deploy.config.env

# 2. 编辑配置文件
vim deploy.config.env

# 3. 使用配置部署
bash scripts/deploy.sh --config deploy.config.env
```

### 方式三: GitHub Actions 自动部署

```bash
# 1. 配置 GitHub Secrets (见上文)

# 2. 添加 GitHub Actions 工作流
cp templates/github-action.yml .github/workflows/deploy.yml

# 3. 推送代码触发部署
git add .
git commit -m "feat: trigger auto deployment"
git push origin main
```

---

## 📚 参考文档

- [SKILL.md](SKILL.md) - 完整部署指南
- [templates/](templates/) - 配置文件模板
- [scripts/](scripts/) - 部署脚本

---

## ❓ 常见问题

### Q1: 忘记复制 GitHub PAT?
**A**: 需要删除旧的并重新生成，旧令牌无法再次查看。

### Q2: SSH 连接被拒绝?
**A**: 检查:
1. 防火墙是否开放 SSH 端口
2. SSH 服务是否运行: `sudo systemctl status ssh`
3. 密钥是否正确配置

### Q3: 域名解析不生效?
**A**: DNS 传播需要 5-10 分钟，最长 48 小时。可用 `ping` 命令测试。

### Q4: GitHub Actions 失败?
**A**:
1. 检查 Secrets 是否正确配置
2. 查看运行日志: 仓库 → Actions → 选择记录
3. 本地测试 SSH 连接

### Q5: 如何查看服务器日志?
**A**:
```bash
# Django 日志
tail -f /www/wwwroot/my-project/logs/django-error.log

# Nginx 日志
tail -f /var/log/nginx/error.log

# Supervisor 日志
sudo supervisorctl tail my-project:django
```

---

## 🔐 安全建议

1. ✅ **使用 SSH 密钥**而非密码登录
2. ✅ **定期更新**系统和依赖包
3. ✅ **配置防火墙**只开放必要端口
4. ✅ **启用 SSL/TLS**加密传输
5. ✅ **定期备份**数据库和重要文件
6. ✅ **使用强密码**（16 位以上）
7. ✅ **限制数据库**远程访问
8. ✅ **监控日志**及时发现异常

---

## 📞 获取帮助

如遇问题:
1. 查看项目文档
2. 检查日志文件
3. 参考 [SKILL.md](SKILL.md) 故障排查章节
4. 联系技术支持
