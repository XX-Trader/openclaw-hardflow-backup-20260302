# Windows 全栈项目本地部署技能

> **适用场景**: Windows 本地开发环境快速搭建
> **支持框架**: Django、FastAPI、Flask、Vue3、React
> **版本**: 1.0
> **更新时间**: 2026-01-05

---

## 🎯 技能概述

这是一个通用的 Windows 本地开发环境部署技能，基于 `db-deploy` 技能的成熟设计模式，专门针对本地开发场景优化。

### 核心特性

- ✅ **项目自动检测** - 智能识别后端/前端类型
- ✅ **配置文件驱动** - JSON 配置，易于管理
- ✅ **一键启动** - 自动启动所有服务
- ✅ **框架无关** - 支持多种后端/前端框架
- ✅ **可移植设计** - 使用环境变量，无硬编码路径
- ✅ **完整错误处理** - 友好的错误提示

---

## 📁 技能结构

```
windows-fullstack-deploy/
├── SKILL.md                      # 技能主文档（本文档）
├── CHECKLIST.md                  # 部署前准备清单
├── README.md                     # 快速入门指南
├── templates/                    # 配置模板
│   ├── deploy.config.json        # 部署配置模板
│   └── .env.local.example        # 环境变量模板
└── scripts/                      # 脚本工具
    ├── init-config.bat           # 初始化配置向导
    ├── detect-project.bat        # 项目自动检测
    ├── start-all.bat             # 一键启动所有服务
    ├── stop-all.bat              # 一键停止所有服务
    ├── start-mysql.bat           # MySQL 服务管理
    ├── start-redis.bat           # Redis 服务管理（WSL）
    ├── start-backend.bat         # 后端启动脚本
    └── start-frontend.bat        # 前端启动脚本
```

---

## 🚀 快速开始

### 前置准备

**必需软件**:
- Python 3.10+
- Node.js 20.19.0 或 ≥22.12.0
- MySQL 8.0+
- Git

**可选软件**:
- WSL 2（用于运行 Redis）

### 三步启动

#### 步骤 1: 复制脚本到项目

```cmd
# 将技能中的 scripts/ 和 templates/ 复制到项目根目录
# 假设项目结构为:
your-project/
├── backend/
├── frontend/
├── scripts/      # 复制这里
└── templates/    # 复制这里
```

#### 步骤 2: 运行初始化向导

```cmd
cd your-project
scripts\init-config.bat
```

向导会自动:
- 检测项目结构
- 识别后端/前端类型
- 生成 `deploy.config.json`

#### 步骤 3: 一键启动

```cmd
scripts\start-all.bat
```

完成！现在可以访问:
- 前端: http://localhost:8083
- 后端: http://localhost:8000

---

## 📖 使用指南

### 方式一: 标准项目（零配置）

如果你的项目结构是标准的，初始化向导会自动识别：

```
your-project/
├── backend/       # Django/FastAPI/Flask
│   ├── manage.py
│   └── requirements.txt
├── frontend/      # Vue/React
│   └── package.json
└── scripts/       # 部署脚本
```

**使用步骤**:
```cmd
scripts\init-config.bat    # 自动检测
scripts\start-all.bat      # 一键启动
```

### 方式二: 自定义项目（配置文件）

如果你的项目结构不标准，可以手动配置：

```
my-weird-project/
├── server/        # 自定义后端目录
├── client/        # 自定义前端目录
└── deploy.config.json
```

**配置示例**:
```json
{
  "services": {
    "backend": {
      "type": "django",
      "path": "server",      // 指定自定义路径
      "port": 8000
    },
    "frontend": {
      "type": "vue",
      "path": "client",      // 指定自定义路径
      "port": 8083
    }
  }
}
```

### 方式三: 分别启动服务

如果只需要启动某个服务：

```cmd
scripts\start-mysql.bat      # 只启动 MySQL
scripts\start-redis.bat      # 只启动 Redis
scripts\start-backend.bat    # 只启动后端
scripts\start-frontend.bat   # 只启动前端（可选端口）
```

---

## 🔧 支持的框架

### 后端框架

| 框架 | 检测文件 | 启动命令 |
|------|---------|---------|
| Django | `manage.py` | `python manage.py runserver` |
| FastAPI | `main.py` | `uvicorn main:app --reload` |
| Flask | `app.py` 或 `wsgi.py` | `python app.py` |

### 前端框架

| 框架 | 检测方式 | 启动命令 |
|------|---------|---------|
| Vue3 | `package.json` 包含 `vue` | `npm run dev` |
| React | `package.json` 包含 `react` | `npm start` |
| Vite | `package.json` 包含 `vite` | `npm run dev` |

---

## 💡 常见场景

### 场景 1: 新成员加入团队

```cmd
# 1. 克隆项目
git clone <repository-url>
cd your-project

# 2. 复制部署脚本
# (从其他团队成员那里获取 scripts/ 和 templates/)

# 3. 运行初始化
scripts\init-config.bat

# 4. 配置环境变量
copy templates\.env.local.example .env.local
# 编辑 .env.local

# 5. 启动
scripts\start-all.bat
```

### 场景 2: 只开发前端

```cmd
scripts\start-frontend.bat
# 选择端口 4（8083）
```

### 场景 3: 只开发后端

```cmd
scripts\start-mysql.bat      # 先启动数据库
scripts\start-backend.bat    # 启动后端
```

### 场景 4: 切换前端端口

```cmd
scripts\start-frontend.bat
# 选择端口 1/2/3/4 (8080/8081/8082/8083)
```

---

## 🐛 故障排查

### 问题 1: 项目检测失败

**原因**: 项目结构不符合标准

**解决方案**:
1. 手动创建 `deploy.config.json`
2. 从 `templates/deploy.config.json` 复制模板
3. 修改 `backend.path` 和 `frontend.path`

### 问题 2: MySQL 启动失败

**解决方案**:
```cmd
# 检查服务名称
sc query | findstr -i mysql

# 手动启动
net start MySQL80
# 或
net start MySQL
```

### 问题 3: Redis 连接失败

**解决方案**:
```cmd
# 检查 WSL
wsl --version

# 启动 Redis
wsl sudo service redis-server start

# 测试连接
wsl redis-cli ping
```

### 问题 4: 端口被占用

**解决方案**:
```cmd
# 查找占用进程
netstat -ano | findstr :8083

# 结束进程
taskkill /PID <进程ID> /F

# 或选择其他端口
scripts\start-frontend.bat
```

---

## 📚 相关文档

- [SKILL.md](SKILL.md) - 完整技能文档
- [CHECKLIST.md](CHECKLIST.md) - 部署前准备清单

---

## 🆘 获取帮助

1. 查看 [SKILL.md](SKILL.md) 完整文档
2. 查看 [CHECKLIST.md](CHECKLIST.md) 准备清单
3. 检查脚本窗口的错误信息
4. 参考故障排查章节

---

**技能版本**: 1.0
**创建时间**: 2026-01-05
**适用平台**: Windows 10/11
**维护者**: Claude AI
