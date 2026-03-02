# Django + Vue Windows 本地开发部署方案

> 适用于 Windows 10/11 的 Django + Vue 全栈项目本地开发环境快速部署方案

---

## 适用场景

**何时使用此技能**：
- 在 Windows 上本地开发 Django + Vue 项目
- 需要快速搭建完整的开发环境（后端 + 前端 + 数据库 + 缓存）
- 团队成员需要统一的本地开发环境配置
- 项目需要可移植的部署脚本（不依赖硬编码路径）

**技术栈要求**：
- 后端：Django 4.2+
- 前端：Vue 3 + Vite
- 数据库：MySQL 8.0+
- 缓存：Redis (WSL)
- 操作系统：Windows 10/11

---

## 核心设计原则

### 1. 环境变量驱动路径

所有脚本使用 `%CD%` 和 `%~dp0` 确保可移植性：

```batch
# 推荐方式：可移植
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

# 不推荐：硬编码路径
set "PROJECT_DIR=C:\Users\Superman\Projects\MyProject"
```

### 2. 服务分离启动

每个服务独立脚本，便于：
- 单独调试某个服务
- 按需启动（如不需要 Redis 时不启动）
- 清晰的错误定位

### 3. 彩色终端输出

使用 ANSI 颜色码提升用户体验：

```batch
set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "BLUE=[94m"
set "NC=[0m"

echo %GREEN%[✓] 操作成功%NC%
echo %RED%[错误] 操作失败%NC%
```

### 4. 完整的错误处理

每个关键步骤都有错误检查和用户提示：

```batch
command_here
if errorlevel 1 (
    echo %RED%[错误] 详细描述%NC%
    echo %YELLOW%建议解决方案%NC%
    pause
    exit /b 1
)
```

---

## 部署脚本清单

### 脚本结构

```
Project/
├── scripts/
│   ├── start-all.bat          # 一键启动所有服务 [主控脚本]
│   ├── start-mysql.bat        # MySQL 服务管理
│   ├── start-redis.bat        # Redis 服务管理 (WSL)
│   └── .env.local.example     # 环境配置模板
├── ShengBeiDjango/
│   └── scripts/
│       └── start-backend.bat  # Django 后端启动
└── ShengBeiVue/
    └── scripts/
        └── start-frontend.bat # Vue 前端启动
```

---

## 脚本详解

### 1. start-all.bat - 主控脚本

**功能**：一键启动所有服务

**启动顺序**：
1. MySQL（必需，同步启动）
2. Redis（必需，异步启动）
3. Django 后端（必需，异步启动）
4. Vue 前端（必需，异步启动）

**关键代码**：

```batch
@echo off
SETLOCAL EnableDelayedExpansion

# 颜色定义
set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "BLUE=[94m"
set "CYAN=[96m"
set "NC=[0m"

# 检查项目目录
if not exist "ShengBeiDjango\" (
    echo %RED%[错误] 未找到 ShengBeiDjango 目录！%NC%
    pause
    exit /b 1
)

# 1. 启动 MySQL（同步）
call "%~dp0start-mysql.bat"

# 2. 启动 Redis（异步）
start "Redis Server" cmd /k "call "%~dp0start-redis.bat""
timeout /t 3 /nobreak >nul

# 3. 启动后端（异步）
start "Django Backend" cmd /k "cd /d "%~dp0..\ShengBeiDjango" && call scripts\start-backend.bat"
timeout /t 5 /nobreak >nul

# 4. 启动前端（异步）
start "Vue Frontend" cmd /k "cd /d "%~dp0..\ShengBeiVue" && call scripts\start-frontend.bat"
timeout /t 3 /nobreak >nul

echo %GREEN%[✓] 所有服务已启动%NC%
pause
```

**使用方式**：
```cmd
cd Project
start-all.bat
```

---

### 2. start-mysql.bat - MySQL 服务管理

**功能**：
- 检测 MySQL 服务（MySQL80, MySQL, mysql57）
- 启动服务（如未运行）
- 显示连接信息

**关键代码**：

```batch
# 检测服务
sc query MySQL80 >nul 2>&1
if not errorlevel 1 (
    set "MYSQL_SERVICE=MySQL80"
    goto :service_found
)

sc query MySQL >nul 2>&1
if not errorlevel 1 (
    set "MYSQL_SERVICE=MySQL"
    goto :service_found
)

echo %RED%[错误] 未找到 MySQL 服务！%NC%
pause
exit /b 1

:service_found
# 检查服务状态
sc query %MYSQL_SERVICE% | findstr STATE | findstr RUNNING >nul 2>&1
if not errorlevel 1 (
    echo %GREEN%[✓] MySQL 服务已运行%NC%
) else (
    echo %YELLOW%[*] 启动 MySQL 服务...%NC%
    net start %MYSQL_SERVICE%
)
```

**连接信息输出**：
```
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=shengbei
DB_USER=shengbei
DB_PASSWORD=ShengBei@2026
```

---

### 3. start-redis.bat - Redis 服务管理（WSL）

**功能**：
- 检查 WSL 环境
- 自动安装 Redis（如未安装）
- 配置并启动 Redis 服务
- 测试连接

**关键代码**：

```batch
# 检查 WSL
wsl --version >nul 2>&1
if errorlevel 1 (
    echo %RED%[错误] 未找到 WSL！%NC%
    echo %YELLOW%请先安装 WSL:%NC%
    echo wsl --install
    pause
    exit /b 1
)

# 检查 Redis
wsl redis-cli --version >nul 2>&1
if errorlevel 1 (
    echo %YELLOW%[*] 安装 Redis...%NC%
    wsl sudo apt-get update
    wsl sudo apt-get install -y redis-server
    wsl sudo sed -i 's/supervised no/supervised systemd/g' /etc/redis/redis.conf
)

# 启动 Redis
wsl sudo service redis-server start

# 测试连接
wsl redis-cli ping
```

**WSL 安装指导**：
```powershell
# 以管理员身份运行 PowerShell
wsl --install
# 重启计算机
```

---

### 4. start-backend.bat - Django 后端启动

**功能**：
- 检查 Python 环境
- 创建/激活虚拟环境
- 安装依赖
- 执行数据库迁移
- 启动 Django 开发服务器
- 可选：启动 Celery Worker 和 Beat

**关键代码**：

```batch
# 设置项目目录
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

# 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo %RED%[错误] 未找到 Python！%NC%
    pause
    exit /b 1
)

# 虚拟环境
if not exist "venv\" (
    python -m venv venv
)
call venv\Scripts\activate.bat

# 安装依赖
pip install -r requirements.txt --quiet

# 数据库迁移
python manage.py showmigrations pm_robot | findstr "[X]" >nul 2>&1
if errorlevel 1 (
    python manage.py makemigrations
    python manage.py migrate
)

# 启动 Celery（可选）
start "Celery Worker" cmd /k "call venv\Scripts\activate.bat && celery -A ShengBeiDjango worker --loglevel=info"
start "Celery Beat" cmd /k "call venv\Scripts\activate.bat && celery -A ShengBeiDjango beat --loglevel=info"

# 启动 Django
python manage.py runserver 0.0.0.0:8000
```

**启动模式选择**：
```
1. 开发服务器（默认，端口 8000）
2. 生产服务器（Gunicorn）
```

---

### 5. start-frontend.bat - Vue 前端启动

**功能**：
- 检查 Node.js 版本（20.19.0 或 ≥22.12.0）
- 安装依赖（如需要）
- 选择启动端口（8080-8083）
- 启动 Vite 开发服务器
- 支持生产构建和预览

**关键代码**：

```batch
# 检查 Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo %RED%[错误] 未找到 Node.js！%NC%
    pause
    exit /b 1
)

# 安装依赖
if not exist "node_modules\" (
    npm install
)

# 端口选择
echo 1. 端口 8080
echo 2. 端口 8081
echo 3. 端口 8082
echo 4. 端口 8083
set /p "CHOICE="请选择端口 (1-4): "

if "%CHOICE%"=="1" set "VITE_PORT=8080"
if "%CHOICE%"=="2" set "VITE_PORT=8081"
if "%CHOICE%"=="3" set "VITE_PORT=8082"
if "%CHOICE%"=="4" set "VITE_PORT=8083"

# 启动 Vite
npm run dev -- --port %VITE_PORT%
```

**版本检查逻辑**：
```javascript
// Node.js 版本要求：^20.19.0 或 >=22.12.0
```

---

### 6. .env.local.example - 环境配置模板

**必需配置项**：

```bash
# Django 配置
DJANGO_SECRET_KEY=              # 必须：python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# 数据库配置
DB_ENGINE=django.db.backends.mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=shengbei
DB_USER=shengbei
DB_PASSWORD=                    # 必须：MySQL 密码

# Redis 配置
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0

# API 加密配置
API_SECRET_MASTER_KEY=          # 必须：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Celery 配置
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0

# CORS 配置
CORS_ALLOWED_ORIGINS=http://localhost:8080,http://localhost:8081,http://localhost:8082,http://localhost:8083
```

**密钥生成命令**：

```bash
# Django Secret Key
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# API Secret Master Key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## 快速开始指南

### 前置准备

1. **安装 Python 3.10+**
   - 下载：https://www.python.org/downloads/
   - 安装时勾选 "Add Python to PATH"

2. **安装 Node.js**
   - 下载：https://nodejs.org/
   - 版本要求：20.19.0 或 ≥22.12.0

3. **安装 MySQL 8.0+**
   - 下载：https://dev.mysql.com/downloads/mysql/
   - 记住 root 密码

4. **安装 WSL**
   - 以管理员运行 PowerShell：`wsl --install`
   - 重启计算机

5. **克隆项目**
   ```cmd
   git clone <repository-url>
   cd DaBaiLiangHua_quant/Project
   ```

### 配置环境

1. **复制环境配置**
   ```cmd
   copy .env.local.example .env.local
   ```

2. **修改配置文件**
   - 生成 Django Secret Key
   - 生成 API Secret Master Key
   - 设置数据库密码
   - 更新 `.env.local` 文件

3. **创建数据库**
   ```sql
   CREATE DATABASE shengbei CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'shengbei'@'localhost' IDENTIFIED BY 'ShengBei@2026';
   GRANT ALL PRIVILEGES ON shengbei.* TO 'shengbei'@'localhost';
   FLUSH PRIVILEGES;
   ```

### 启动服务

**一键启动（推荐）**：
```cmd
cd Project
start-all.bat
```

**分步启动**：
```cmd
# 1. 启动 MySQL
cd scripts
start-mysql.bat

# 2. 启动 Redis
start-redis.bat

# 3. 启动后端
cd ..\ShengBeiDjango\scripts
start-backend.bat

# 4. 启动前端
cd ..\..\ShengBeiVue\scripts
start-frontend.bat
```

### 访问服务

- **前端应用**：http://localhost:8083
- **后端 API**：http://localhost:8000
- **管理后台**：http://localhost:8000/admin

---

## 常见问题排查

### 问题 1：MySQL 服务启动失败

**症状**：`start-mysql.bat` 提示服务不存在

**排查步骤**：
1. 检查 MySQL 是否已安装
2. 查找服务名称：`sc query | findstr -i mysql`
3. 修改脚本中的服务名称（MySQL80/MySQL/mysql57）

**解决方案**：
```cmd
# 手动启动 MySQL
net start MySQL80

# 或修改服务名称后重试
```

---

### 问题 2：Redis 连接失败

**症状**：后端启动时提示 Redis 连接错误

**排查步骤**：
1. 检查 WSL 是否安装：`wsl --version`
2. 检查 Redis 是否安装：`wsl redis-cli --version`
3. 手动启动 Redis：`wsl sudo service redis-server start`

**解决方案**：
```cmd
# 测试 Redis 连接
wsl redis-cli ping
# 应返回 PONG
```

---

### 问题 3：Python 虚拟环境创建失败

**症状**：`python -m venv venv` 报错

**排查步骤**：
1. 检查 Python 版本：`python --version`
2. 确保 Python ≥ 3.10
3. 检查是否有 venv 模块

**解决方案**：
```cmd
# 重新安装 Python
# 或使用 virtualenv
pip install virtualenv
virtualenv venv
```

---

### 问题 4：前端端口被占用

**症状**：`Error: listen EADDRINUSE: address already in use :::8083`

**排查步骤**：
1. 查找占用进程：`netstat -ano | findstr :8083`
2. 结束进程或更换端口

**解决方案**：
```cmd
# 结束进程
taskkill /PID <进程ID> /F

# 或选择其他端口
```

---

### 问题 5：数据库迁移失败

**症状**：`python manage.py migrate` 报错

**排查步骤**：
1. 检查数据库配置：`.env.local`
2. 测试数据库连接
3. 检查数据库是否已创建

**解决方案**：
```cmd
# 测试连接
mysql -u shengbei -p -e "SHOW DATABASES;"

# 重置迁移
python manage.py migrate --fake-initial
```

---

## 最佳实践

### 1. 开发工作流

```cmd
# 1. 拉取最新代码
git pull

# 2. 更新依赖（后端）
cd ShengBeiDjango
pip install -r requirements.txt

# 3. 更新依赖（前端）
cd ..\ShengBeiVue
npm install

# 4. 执行数据库迁移
cd ..\ShengBeiDjango
python manage.py migrate

# 5. 启动服务
cd ..\scripts
start-all.bat
```

### 2. 代码规范

**Python**：
- PEP 8 规范
- 4 空格缩进
- 行长 ≤ 120

**JavaScript/Vue**：
- ESLint 配置
- 2 空格缩进
- 组件名 PascalCase

### 3. Git 提交规范

```
feat(module): 简短描述

详细说明（可选）

Closes #issue
```

### 4. 安全注意事项

- ⚠️ 永远不要提交 `.env.local` 到 Git
- ⚠️ 生产环境 `DEBUG=False`
- ⚠️ 定期更新依赖包
- ⚠️ 使用强密码

---

## 扩展与定制

### 添加新的启动脚本

**模板**：
```batch
@echo off
SETLOCAL EnableDelayedExpansion

# 颜色定义
set "GREEN=[92m"
set "RED=[91m"
set "NC=[0m"

# 检查环境
echo %YELLOW%[*] 检查环境...%NC%

# 执行操作
echo %GREEN%[✓] 操作成功%NC%

# 错误处理
if errorlevel 1 (
    echo %RED%[错误] 操作失败%NC%
    pause
    exit /b 1
)

pause
```

### 集成到其他项目

**步骤**：
1. 复制 `scripts/` 目录
2. 修改服务名称和路径
3. 更新 `.env.local.example`
4. 调整端口配置

### 添加新的服务

**示例：添加 MongoDB 服务**

1. 创建 `start-mongodb.bat`
2. 在 `start-all.bat` 中添加启动逻辑
3. 更新文档

---

## 相关资源

### 文档链接
- Django 官方文档：https://docs.djangoproject.com/
- Vue 官方文档：https://vuejs.org/
- Vite 官方文档：https://vitejs.dev/
- MySQL 文档：https://dev.mysql.com/doc/
- Redis 文档：https://redis.io/docs/

### 工具下载
- Python：https://www.python.org/downloads/
- Node.js：https://nodejs.org/
- MySQL：https://dev.mysql.com/downloads/mysql/
- Git：https://git-scm.com/downloads

---

## 更新日志

**v1.0.0** (2026-01-05)
- ✅ 初始版本
- ✅ 支持 Django + Vue 全栈项目
- ✅ MySQL + Redis 服务管理
- ✅ 完整的错误处理
- ✅ 彩色终端输出
- ✅ 可移植路径设计

---

**维护者**：Claude AI
**适用版本**：Windows 10/11, Python 3.10+, Node.js 20.19.0+, Django 4.2+, Vue 3
**最后更新**：2026-01-05
