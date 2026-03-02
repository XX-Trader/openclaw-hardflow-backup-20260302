# Windows 本地开发环境准备清单

> 本清单适用于 Windows 本地开发环境搭建

## 📋 前置准备

### 必需软件

| 软件 | 版本要求 | 用途 | 下载地址 | 检查命令 |
|------|---------|------|---------|---------|
| **Python** | 3.10+ | 后端运行环境 | https://www.python.org/downloads/ | `python --version` |
| **Node.js** | 20.19.0 或 ≥22.12.0 | 前端运行环境 | https://nodejs.org/ | `node --version` |
| **MySQL** | 8.0+ | 数据库 | https://dev.mysql.com/downloads/mysql/ | `mysql --version` |
| **Git** | 最新版 | 版本控制 | https://git-scm.com/downloads | `git --version` |

### 可选软件

| 软件 | 版本要求 | 用途 | 下载地址 |
|------|---------|------|---------|
| **WSL 2** | 最新版 | 运行 Redis（推荐） | 微软商店安装 |
| **Redis** | 最新版 | 缓存（Windows 原生） | https://redis.io/download |

---

## 🔧 软件安装指南

### 1. Python 安装

**下载地址**: https://www.python.org/downloads/

**安装步骤**:
1. 下载 Python 3.10 或更高版本
2. 运行安装程序
3. **重要**: 勾选 "Add Python to PATH"
4. 点击 "Install Now"

**验证安装**:
```cmd
python --version
# 应显示: Python 3.10.x 或更高
```

**注意事项**:
- Windows Store 版本可能有兼容性问题，推荐从官网下载
- 如果已安装 Python 3.9 或更低版本，请升级到 3.10+

---

### 2. Node.js 安装

**下载地址**: https://nodejs.org/

**版本要求**:
- 20.19.0（LTS）
- 或 ≥22.12.0（Current）

**安装步骤**:
1. 下载 LTS 版本（推荐）
2. 运行安装程序
3. 一路 Next 完成安装

**验证安装**:
```cmd
node --version
# 应显示: v20.19.0 或更高

npm --version
# 应显示: 10.x 或更高
```

---

### 3. MySQL 安装

**下载地址**: https://dev.mysql.com/downloads/mysql/

**安装步骤**:
1. 下载 MySQL Installer for Windows
2. 选择 "Custom" 安装
3. 只安装 "MySQL Server" 8.0+
4. 设置 root 密码（请妥善保管）
5. 默认端口 3306

**验证安装**:
```cmd
mysql --version
# 应显示: mysql  Ver 8.0.x
```

**服务检查**:
```cmd
# 检查 MySQL 服务状态
sc query MySQL80

# 或
sc query MySQL
```

---

### 4. Git 安装

**下载地址**: https://git-scm.com/downloads

**安装步骤**:
1. 下载 Windows 版本
2. 运行安装程序
3. 默认选项即可
4. 建议选择 "Use Git from the Windows Command Prompt"

**验证安装**:
```cmd
git --version
# 应显示: git version 2.x.x
```

---

### 5. WSL 安装（可选，用于 Redis）

**推荐使用 WSL 运行 Redis**

**安装步骤**:
1. 以管理员身份运行 PowerShell
2. 执行以下命令:
   ```powershell
   wsl --install
   ```
3. 重启计算机
4. WSL 会自动安装 Ubuntu

**验证安装**:
```cmd
wsl --version
```

---

## 📝 项目配置

### 1. 克隆项目

```cmd
# 克隆项目
git clone <your-repository-url>
cd <your-project>
```

### 2. 运行初始化向导

```cmd
# 运行初始化配置向导
scripts\init-config.bat

# 向导会自动:
# - 检测项目结构
# - 检测后端/前端类型
# - 生成配置文件
```

### 3. 配置环境变量

```cmd
# 复制环境变量模板
copy templates\.env.local.example .env.local

# 编辑 .env.local
notepad .env.local
```

**必须配置项**:
```bash
# Django Secret Key
DJANGO_SECRET_KEY=your-secret-key-here

# 数据库配置
DB_NAME=your_database
DB_USER=your_user
DB_PASSWORD=your_password
```

**生成密钥**:
```cmd
# 生成 Django Secret Key
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## 🚀 首次启动

### 1. 创建数据库

```cmd
# 登录 MySQL
mysql -u root -p

# 创建数据库
CREATE DATABASE your_database CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# 创建用户（可选）
CREATE USER 'your_user'@'localhost' IDENTIFIED BY 'your_password';

# 授权
GRANT ALL PRIVILEGES ON your_database.* TO 'your_user'@'localhost';

# 刷新权限
FLUSH PRIVILEGES;

# 退出
EXIT;
```

### 2. 启动所有服务

```cmd
# 一键启动
scripts\start-all.bat

# 或分别启动
scripts\start-mysql.bat
scripts\start-redis.bat
scripts\start-backend.bat
scripts\start-frontend.bat
```

### 3. 访问服务

- **前端应用**: http://localhost:8083
- **后端 API**: http://localhost:8000
- **管理后台**: http://localhost:8000/admin

---

## ✅ 检查清单

### 环境准备

- [ ] Python 3.10+ 已安装并添加到 PATH
- [ ] Node.js 20.19.0+ 已安装
- [ ] MySQL 8.0+ 已安装并启动
- [ ] Git 已安装
- [ ] WSL 已安装（如使用 Redis）

### 项目配置

- [ ] 项目已克隆到本地
- [ ] 已运行初始化向导
- [ ] `deploy.config.json` 已生成
- [ ] `.env.local` 已创建并配置
- [ ] 数据库已创建

### 服务启动

- [ ] MySQL 服务正在运行
- [ ] Redis 服务正在运行（可选）
- [ ] 后端服务启动成功
- [ ] 前端服务启动成功
- [ ] 可以访问前端页面
- [ ] 可以访问后端 API

---

## 🔍 故障排查

### Python 相关问题

**问题**: `python` 命令未找到

**解决方案**:
```cmd
# 1. 检查 Python 是否安装
where python

# 2. 重新安装 Python，勾选 "Add Python to PATH"

# 3. 手动添加到 PATH
# 系统属性 → 高级 → 环境变量 → Path → 新建
# C:\Users\YourName\AppData\Local\Programs\Python\Python310
# C:\Users\YourName\AppData\Local\Programs\Python\Python310\Scripts
```

### Node.js 相关问题

**问题**: npm 安装依赖失败

**解决方案**:
```cmd
# 1. 清除缓存
npm cache clean --force

# 2. 切换镜像源
npm config set registry https://registry.npmmirror.com

# 3. 重新安装
npm install
```

### MySQL 相关问题

**问题**: MySQL 服务启动失败

**解决方案**:
```cmd
# 1. 检查服务名称
sc query | findstr -i mysql

# 2. 启动服务
net start MySQL80
# 或
net start MySQL

# 3. 查看错误日志
# MySQL Installer → Reconfigure
```

### 端口占用问题

**问题**: 端口已被占用

**解决方案**:
```cmd
# 查找占用端口的进程
netstat -ano | findstr :8083

# 结束进程
taskkill /PID <进程ID> /F

# 或修改配置文件使用其他端口
```

---

## 📚 参考资源

- [Python 官方文档](https://docs.python.org/)
- [Node.js 官方文档](https://nodejs.org/docs)
- [MySQL 官方文档](https://dev.mysql.com/doc/)
- [Git 官方文档](https://git-scm.com/doc)
- [WSL 官方文档](https://docs.microsoft.com/en-us/windows/wsl/)

---

**最后更新**: 2026-01-05
