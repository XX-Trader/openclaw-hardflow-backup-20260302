---
name: windows-fullstack-deploy
description: Windows 本地开发环境自动化部署技能。支持 Django/FastAPI/Flask 后端、Vue3/React 前端、MySQL 数据库、Redis 缓存的完整本地开发流程。当用户在 Windows 上搭建本地开发环境时使用此技能。支持项目自动检测、配置文件驱动、一键启动所有服务。
license: MIT
---

# Windows 全栈项目本地部署技能

## 🎯 技能特性

- ✅ 支持多种后端框架（Django、FastAPI、Flask）
- ✅ 支持多种前端框架（Vue3、React、Angular）
- ✅ 配置文件驱动，易于管理
- ✅ 项目自动检测，零配置启动
- ✅ 一键启动所有服务
- ✅ 完整的错误处理和用户引导
- ✅ 可移植路径设计（使用环境变量）

## 📁 技能文件结构

```
windows-fullstack-deploy/
├── SKILL.md                      # 本文件
├── CHECKLIST.md                  # 部署前准备清单
├── templates/                    # 配置模板
│   ├── deploy.config.json        # 部署配置模板（JSON 格式）
│   ├── .env.local.example        # 环境变量模板
│   └── project-structure.json    # 项目结构定义
└── scripts/                      # 脚本文件
    ├── init-config.bat           # 初始化配置向导
    ├── detect-project.bat        # 项目自动检测
    ├── start-all.bat             # 一键启动所有服务
    ├── stop-all.bat              # 一键停止所有服务
    ├── start-mysql.bat           # MySQL 服务管理
    ├── start-redis.bat           # Redis 服务管理（WSL）
    ├── start-backend.bat         # 后端启动脚本
    └── start-frontend.bat        # 前端启动脚本
```

## 🚀 快速开始

### 方式一：自动检测（推荐）

**适用于标准项目结构**：
```
your-project/
├── backend/       # Django/FastAPI/Flask
├── frontend/      # Vue/React
└── deploy.config.json（自动生成）
```

**使用步骤**：
```cmd
# 1. 进入项目目录
cd your-project

# 2. 复制技能脚本到项目
# 将 scripts/ 目录复制到项目根目录

# 3. 运行初始化向导
scripts\init-config.bat

# 4. 一键启动所有服务
scripts\start-all.bat
```

### 方式二：手动配置

**适用于自定义项目结构**：

```cmd
# 1. 复制配置模板
copy templates\deploy.config.json deploy.config.json

# 2. 编辑配置文件
# 修改后端路径、前端路径、端口等

# 3. 启动服务
scripts\start-all.bat
```

## 📋 项目结构说明

### 标准项目结构（自动检测）

```
your-project/
├── backend/                    # 后端项目
│   ├── manage.py              # Django 标识文件
│   ├── requirements.txt
│   └── venv/                  # 虚拟环境
├── frontend/                   # 前端项目
│   ├── package.json           # 前端配置
│   ├── node_modules/
│   └── src/
└── deploy.config.json         # 部署配置（自动生成）
```

### 自定义项目结构

```
your-weird-project/
├── server/                    # 自定义后端目录
├── client/                    # 自定义前端目录
└── deploy.config.json         # 配置文件指定路径
```

**deploy.config.json 配置示例**：
```json
{
  "version": "1.0",
  "projectName": "MyProject",
  "projectType": "fullstack",
  "autoDetected": false,

  "services": {
    "backend": {
      "enabled": true,
      "type": "django",
      "path": "server",           // 自定义路径
      "port": 8000
    },
    "frontend": {
      "enabled": true,
      "type": "vue",
      "path": "client",           // 自定义路径
      "port": 8083
    }
  }
}
```

## 🔧 支持的框架组合

### 后端框架

| 框架 | 检测文件 | 启动命令 |
|------|---------|---------|
| **Django** | `manage.py` | `python manage.py runserver` |
| **FastAPI** | `main.py` (含 fastapi) | `uvicorn main:app --reload` |
| **Flask** | `app.py` 或 `wsgi.py` | `python app.py` |

### 前端框架

| 框架 | 检测方式 | 启动命令 |
|------|---------|---------|
| **Vue3** | `package.json` 包含 `vue` | `npm run dev` |
| **React** | `package.json` 包含 `react` | `npm start` |
| **Vite** | `package.json` 包含 `vite` | `npm run dev` |

## 📝 配置文件详解

### deploy.config.json 完整配置

```json
{
  "version": "1.0",
  "projectName": "MyProject",
  "projectType": "fullstack",
  "autoDetected": true,

  "services": {
    "backend": {
      "enabled": true,
      "type": "django",
      "path": "backend",
      "port": 8000,
      "virtualEnv": true,
      "venvName": "venv",
      "commands": {
        "install": "pip install -r requirements.txt",
        "migrate": "python manage.py migrate",
        "start": "python manage.py runserver 0.0.0.0:8000",
        "createsuperuser": "python manage.py createsuperuser"
      }
    },

    "frontend": {
      "enabled": true,
      "type": "vue",
      "path": "frontend",
      "port": 8083,
      "buildTool": "vite",
      "commands": {
        "install": "npm install",
        "start": "npm run dev",
        "build": "npm run build"
      }
    },

    "database": {
      "type": "mysql",
      "enabled": true,
      "serviceName": "MySQL80",
      "port": 3306,
      "autoStart": true
    },

    "cache": {
      "type": "redis",
      "enabled": true,
      "useWSL": true,
      "port": 6379,
      "autoStart": true
    }
  },

  "environment": {
    "pythonVersion": "3.10",
    "nodeVersion": "20.19.0",
    "mysqlRequired": true,
    "redisRequired": true
  }
}
```

### .env.local.example 环境变量模板

```bash
# ========================================
# 本地开发环境配置
# ========================================

# Django 配置
DJANGO_SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# 数据库配置
DB_ENGINE=django.db.backends.mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=your_database
DB_USER=your_user
DB_PASSWORD=your_password

# Redis 配置
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0

# CORS 配置
CORS_ALLOWED_ORIGINS=http://localhost:8080,http://localhost:8083
```

## 🔄 部署流程

### 首次部署（初始化）

```cmd
# 1. 运行初始化向导
scripts\init-config.bat

# 向导会：
# - 自动检测项目结构
# - 显示检测结果
# - 生成配置文件
# - 提示下一步操作

# 2. 检查配置文件
type deploy.config.json

# 3. 修改环境变量（如需要）
copy templates\.env.local.example .env.local
# 编辑 .env.local

# 4. 一键启动
scripts\start-all.bat
```

### 日常开发启动

```cmd
# 方式一：一键启动所有服务
scripts\start-all.bat

# 方式二：分别启动
scripts\start-mysql.bat      # 启动 MySQL
scripts\start-redis.bat      # 启动 Redis
scripts\start-backend.bat    # 启动后端
scripts\start-frontend.bat   # 启动前端

# 方式三：只启动前端（前端开发）
scripts\start-frontend.bat

# 方式四：只启动后端（后端开发）
scripts\start-backend.bat
```

### 停止服务

```cmd
# 一键停止所有服务
scripts\stop-all.bat

# 或手动停止
# 在各个服务窗口按 Ctrl+C
```

## 🎨 初始化向导详解

### 自动检测逻辑

**后端检测顺序**：
```batch
# 1. 检测 Django
if exist "backend\manage.py" (
    set BACKEND_TYPE=django
    goto :backend_found
)

# 2. 检测 FastAPI
if exist "backend\main.py" (
    findstr /i "fastapi" backend\main.py >nul
    if not errorlevel 1 (
        set BACKEND_TYPE=fastapi
        goto :backend_found
    )
)

# 3. 检测 Flask
if exist "backend\app.py" (
    set BACKEND_TYPE=flask
    goto :backend_found
)

:backend_not_found
echo [警告] 未检测到后端项目
```

**前端检测顺序**：
```batch
# 1. 检测 package.json
if exist "frontend\package.json" (
    # 2. 检测 Vue
    findstr /i "vue" frontend\package.json >nul
    if not errorlevel 1 (
        set FRONTEND_TYPE=vue
        goto :frontend_found
    )

    # 3. 检测 React
    findstr /i "react" frontend\package.json >nul
    if not errorlevel 1 (
        set FRONTEND_TYPE=react
        goto :frontend_found
    )
)

:frontend_not_found
echo [警告] 未检测到前端项目
```

### 向导交互流程

```
========================================
  Windows 全栈项目部署配置向导
========================================

[1/5] 检测项目结构...
  ✓ 发现 Django 后端: backend/
  ✓ 发现 Vue3 前端: frontend/

[2/5] 检测环境依赖...
  ✓ Python 3.10.12 已安装
  ✓ Node.js 20.19.0 已安装
  ! MySQL 服务未运行（将自动启动）
  ! Redis 未安装（可选）

[3/5] 服务配置:
  后端类型: Django
  后端路径: backend/
  后端端口: 8000

  前端类型: Vue3
  前端路径: frontend/
  前端端口: 8083

  数据库: MySQL (端口 3306)
  缓存: Redis (端口 6379)

[4/5] 是否使用默认配置? (Y/N): Y

[5/5] 生成配置文件...
  ✓ 已创建: deploy.config.json
  ✓ 已创建: .env.local.example

========================================
  配置完成！
========================================

下一步操作:
  1. 检查 deploy.config.json（如需修改）
  2. 配置环境变量（复制 .env.local.example 为 .env.local）
  3. 运行 scripts\start-all.bat 启动所有服务

按任意键开始启动服务...
```

## 🔧 脚本详解

### start-all.bat - 主启动脚本

**功能**：一键启动所有服务

**执行顺序**：
1. 检查配置文件
2. 启动 MySQL（同步，等待完成）
3. 启动 Redis（异步，独立窗口）
4. 启动后端（异步，独立窗口）
5. 启动前端（异步，独立窗口）
6. 显示服务访问地址

**核心代码**：
```batch
@echo off
setlocal EnableDelayedExpansion

# 加载配置
if not exist "deploy.config.json" (
    echo [错误] 未找到配置文件！
    echo 请先运行: scripts\init-config.bat
    pause
    exit /b 1
)

# 启动 MySQL
echo [1/4] 启动 MySQL...
call scripts\start-mysql.bat

# 启动 Redis
echo [2/4] 启动 Redis...
start "Redis Server" cmd /k "scripts\start-redis.bat"
timeout /t 3 /nobreak >nul

# 启动后端
echo [3/4] 启动后端...
start "Backend" cmd /k "scripts\start-backend.bat"
timeout /t 5 /nobreak >nul

# 启动前端
echo [4/4] 启动前端...
start "Frontend" cmd /k "scripts\start-frontend.bat"
timeout /t 3 /nobreak >nul

# 显示访问地址
echo.
echo ========================================
echo  所有服务已启动！
echo ========================================
echo  前端: http://localhost:8083
echo  后端: http://localhost:8000
echo ========================================
pause
```

### start-backend.bat - 后端启动脚本

**功能**：启动后端服务（支持多种框架）

**特性**：
- 自动检测后端类型
- 自动创建虚拟环境
- 自动安装依赖
- 自动执行数据库迁移

### start-frontend.bat - 前端启动脚本

**功能**：启动前端服务（支持多种框架）

**特性**：
- 自动检测前端类型
- 自动安装依赖
- 支持多端口选择
- 支持生产构建

## 📊 项目架构概览

```
本地开发环境 (Windows)
your-project/
├── backend/                    # 后端项目
│   ├── manage.py / main.py    # 入口文件
│   ├── requirements.txt       # Python 依赖
│   └── venv/                  # 虚拟环境
├── frontend/                   # 前端项目
│   ├── package.json           # Node 依赖
│   ├── node_modules/          # 依赖包
│   └── src/                   # 源代码
├── scripts/                    # 部署脚本
│   ├── start-all.bat
│   ├── init-config.bat
│   └── ...
└── deploy.config.json         # 部署配置

系统服务:
├── MySQL 8.0                  # 数据库（端口 3306）
└── Redis (WSL)               # 缓存（端口 6379）
```

## 🔍 常见问题排查

### Q1: 项目检测失败？

**原因**：项目结构不符合标准

**解决方案**：
```cmd
# 方式一：调整项目结构为标准结构
your-project/
├── backend/    # 后端
└── frontend/   # 前端

# 方式二：手动创建配置文件
copy templates\deploy.config.json deploy.config.json
# 编辑 deploy.config.json 指定正确的路径
```

### Q2: MySQL 服务启动失败？

**解决方案**：
```cmd
# 检查 MySQL 服务名称
sc query | findstr -i mysql

# 修改 deploy.config.json
{
  "services": {
    "database": {
      "serviceName": "MySQL57"  // 改为实际的服务名
    }
  }
}
```

### Q3: 前端端口被占用？

**解决方案**：
```cmd
# 方式一：修改配置文件
{
  "services": {
    "frontend": {
      "port": 8084  // 改为其他端口
    }
  }
}

# 方式二：启动时选择端口
scripts\start-frontend.bat
# 选择不同的端口
```

### Q4: 虚拟环境创建失败？

**解决方案**：
```cmd
# 检查 Python 版本
python --version

# 确保 Python 3.10+ 已安装
# 重新安装时勾选 "Add Python to PATH"

# 手动创建虚拟环境
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 💡 最佳实践

### 1. 配置文件管理

**推荐**：
- ✅ 将 `deploy.config.json` 提交到版本控制
- ✅ 将 `.env.local.example` 提交到版本控制
- ❌ 不要提交 `.env.local`（包含敏感信息）

### 2. 服务启动顺序

推荐顺序：MySQL → Redis → Backend → Frontend

### 3. 开发工作流

```cmd
# 每天开始开发
scripts\start-all.bat

# 开发过程中
# 前端热重载自动生效
# 后端需要手动重启（Ctrl+C → 启动）

# 每天结束开发
# 在各个窗口按 Ctrl+C 停止服务
```

### 4. 依赖更新

```cmd
# 更新 Python 依赖
cd backend
pip install --upgrade -r requirements.txt

# 更新 Node 依赖
cd frontend
npm update
```

## 📚 相关文档

- [CHECKLIST.md](CHECKLIST.md) - 部署前准备清单
- [templates/](templates/) - 配置文件模板
- [scripts/](scripts/) - 部署脚本

## 🆘 获取帮助

如遇问题：
1. 查看 [CHECKLIST.md](CHECKLIST.md) 确认环境准备
2. 检查配置文件是否正确
3. 查看各个服务窗口的错误信息
4. 参考常见问题排查章节

---

**技能版本**: 1.0
**最后更新**: 2026-01-05
**适用平台**: Windows 10/11
**支持框架**: Django、FastAPI、Flask、Vue3、React
