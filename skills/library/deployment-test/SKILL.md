---
name: deployment-test
displayName: "部署测试"
version: "1.0.0"
description: 全栈项目部署后自动化测试技能。支持交互式快速测试、端口检测、API 接口测试、浏览器 UI 自动化测试、测试报告生成。适用于 Django + Vue 全栈项目部署后的验收测试。
description_zh: "deployment-test技能，详见 SKILL.md"
author: "maintainers"
license: "MIT"
updated_at: "2026-01-25"

triggers:
  keywords:
    - "测试部署"
    - "验收测试"
    - "部署后测试"
    - "测试生产环境"
    - "生产环境测试"
  auto_trigger: true
  confidence_threshold: 0.8

tools:
  required:
    - Bash
    - Read
  optional:
    - mcp__chrome-devtools-mcp__*

permissions:
  level: "full"
  scope:
    - "bash:read"
    - "bash:execute"
---

# 部署后自动化测试技能

## 技能特性

- 通用设计，适用于任何 Django + Vue 全栈项目
- 端口检测 - 检查 MySQL、Redis、后端、前端端口是否监听
- API 测试 - 批量测试后端接口，验证响应格式
- UI 测试 - 浏览器 MCP 自动化测试登录和页面加载
- 报告生成 - 自动生成 Markdown 格式测试报告
- 配置驱动 - 测试参数通过配置文件管理

---

## 技能文件结构

```
deployment-test/
├── SKILL.md                      # 本文件
├── templates/                    # 配置模板
│   ├── test.config.json         # 测试配置模板
│   └── test-report.md           # 测试报告模板
└── scripts/                      # 测试脚本（统一文件夹，测试后手动删除）
    ├── quick-test.bat           # 双击启动快速测试 (推荐)
    ├── quick-test.py            # 交互式快速测试
    ├── run-all-tests.py         # 一键运行所有测试
    ├── test-ports.py            # 端口检测
    ├── test-api.py              # API 测试
    └── test-ui.py               # UI 自动化测试
```

---

## 快速开始

### 方式一：交互式快速测试 (推荐，最简单)

**双击启动**：
```
双击 quick-test.bat 文件
```

**或命令行启动**：
```bash
cd scripts
python quick-test.py
```

**交互流程**：
1. 输入前端网址 (如 http://localhost:8083)
2. 输入后端 API 网址 (如 http://localhost:8000)
3. 是否有测试账号？(y/n)
4. 选择测试范围：完整测试 / 仅端口 / 仅 API / 仅 UI
5. 自动运行测试并生成报告

**示例**：
```
========================================================================
  🚀 网页功能快速测试
========================================================================

请输入前端网址 (默认: http://localhost:8083):
请输入后端 API 网址 (默认: http://localhost:8000):
是否有测试账号？(y/n) (默认: n): y
请输入测试邮箱: test@example.com
请输入测试密码: Test123456

请选择测试范围:
  1. 完整测试 (端口 + API + UI)
  2. 仅测试端口
  3. 仅测试 API
  4. 仅测试 UI
请选择 (1-4) (默认: 1): 1

开始测试？(y/n) (默认: y): y

[运行测试...]

✅ 报告已生成: test_reports/deployment-test-report-20260105-143000.md
```

---

### 方式二：配置文件测试

#### 步骤 1: 配置测试参数

将 `templates/test.config.json` 复制到项目根目录，并修改配置：

```json
{
  "projectName": "MyProject",
  "testDate": "2026-01-05",
  "tester": "Your Name",

  "services": {
    "mysql": {
      "enabled": true,
      "host": "127.0.0.1",
      "port": 3306
    },
    "redis": {
      "enabled": true,
      "host": "127.0.0.1",
      "port": 6379
    },
    "backend": {
      "enabled": true,
      "url": "http://localhost:8000"
    },
    "frontend": {
      "enabled": true,
      "url": "http://localhost:8083"
    }
  },

  "testAccounts": {
    "email": "test@example.com",
    "password": "Test123456"
  },

  "apiEndpoints": [
    {
      "name": "用户登录",
      "method": "POST",
      "path": "/api/accounts/login/",
      "expectedStatus": 200
    },
    {
      "name": "获取机器人列表",
      "method": "GET",
      "path": "/api/pm-robot/list",
      "expectedStatus": 200,
      "needAuth": true
    }
  ],

  "uiTests": [
    {
      "name": "登录功能测试",
      "url": "/login",
      "actions": [
        { "type": "fill", "selector": "#email", "value": "test@example.com" },
        { "type": "fill", "selector": "#password", "value": "Test123456" },
        { "type": "click", "selector": "button[type='submit']" },
        { "type": "waitFor", "target": "navigation" }
      ]
    }
  ]
}
```

### 步骤 2: 运行测试

```bash
# 进入测试脚本目录
cd scripts

# 运行所有测试
python run-all-tests.py
```

### 步骤 3: 查看报告

测试报告将生成在项目根目录的 `test_reports/` 文件夹：

```
test_reports/
└── deployment-test-report-20260105-143000.md
```

---

## 测试模块说明

### 1. 端口检测 (test-ports.py)

**功能**：检查服务端口是否监听

**检测项**：
- MySQL (3306)
- Redis (6379)
- 后端服务 (8000)
- 前端服务 (8083)

**输出示例**：
```markdown
## 端口检测结果

| 服务 | 端口 | 状态 | 响应时间 |
|------|------|------|----------|
| MySQL | 3306 | ✅ 正常 | 2ms |
| Redis | 6379 | ✅ 正常 | 1ms |
| Backend | 8000 | ✅ 正常 | 5ms |
| Frontend | 8083 | ✅ 正常 | 8ms |
```

---

### 2. API 测试 (test-api.py)

**功能**：批量测试后端 API 接口

**测试流程**：
1. 读取 API 文档或配置文件
2. 依次测试每个接口
3. 验证响应状态码
4. 验证响应数据格式
5. 记录测试结果

**测试示例**：
```python
# 测试登录接口
response = requests.post(
    "http://localhost:8000/api/accounts/login/",
    json={
        "email": "test@example.com",
        "password": "Test123456"
    }
)
assert response.status_code == 200
assert response.json()["code"] == 200
```

**输出示例**：
```markdown
## API 测试结果

| 接口名称 | 方法 | 路径 | 预期状态 | 实际状态 | 结果 |
|---------|------|------|----------|----------|------|
| 用户登录 | POST | /api/accounts/login/ | 200 | 200 | ✅ |
| 获取机器人列表 | GET | /api/pm-robot/list | 200 | 200 | ✅ |
| 创建机器人 | POST | /api/pm-robot/create | 200 | 400 | ❌ |

**失败详情**：
- 创建机器人: 响应状态码 400，预期 200
  错误信息: "encrypted_private_key is required"
```

---

### 3. UI 测试 (test-ui.py)

**功能**：使用浏览器 MCP 自动化测试前端 UI

**测试流程**：
1. 打开浏览器
2. 导航到指定页面
3. 执行用户操作（填写表单、点击按钮等）
4. 等待页面响应
5. 截图保存
6. 验证页面元素
7. 关闭浏览器

**测试示例**：
```python
# 测试登录功能
page.goto("http://localhost:8083/login")
page.fill("#email", "test@example.com")
page.fill("#password", "Test123456")
page.click("button[type='submit']")
page.wait_for_load_state("networkidle")
assert page.url == "http://localhost:8083/dashboard"
```

**输出示例**：
```markdown
## UI 测试结果

| 测试名称 | 页面 | 操作 | 结果 | 截图 |
|---------|------|------|------|------|
| 登录功能测试 | /login | 填写表单 → 点击登录 | ✅ | [查看] |
| 机器人列表页 | /robots | 检查表格渲染 | ✅ | [查看] |
| 创建机器人页 | /robots/create | 检查表单显示 | ❌ | [查看] |

**失败详情**：
- 创建机器人页: 未找到 "钱包地址" 输入框
```

---

## 技能使用指南

### 场景一：首次部署测试

```bash
# 1. 配置测试参数
cp templates/test.config.json ../test.config.json
vim ../test.config.json

# 2. 运行完整测试
python run-all-tests.py

# 3. 查看报告
cat ../test_reports/deployment-test-report-*.md
```

### 场景二：仅测试端口

```bash
python test-ports.py
```

### 场景三：仅测试 API

```bash
python test-api.py
```

### 场景四：仅测试 UI

```bash
python test-ui.py
```

---

## 配置详解

### test.config.json 完整配置

```json
{
  "version": "1.0",

  // 项目信息
  "projectName": "MyProject",
  "testDate": "2026-01-05",
  "tester": "Your Name",

  // 服务配置
  "services": {
    "mysql": {
      "enabled": true,
      "host": "127.0.0.1",
      "port": 3306,
      "timeout": 5000
    },
    "redis": {
      "enabled": true,
      "host": "127.0.0.1",
      "port": 6379,
      "timeout": 5000
    },
    "backend": {
      "enabled": true,
      "url": "http://localhost:8000",
      "timeout": 10000
    },
    "frontend": {
      "enabled": true,
      "url": "http://localhost:8083",
      "timeout": 10000
    }
  },

  // 测试账号
  "testAccounts": {
    "email": "test@example.com",
    "password": "Test123456",
    "nickname": "测试用户"
  },

  // API 测试配置
  "apiEndpoints": [
    {
      "name": "用户登录",
      "method": "POST",
      "path": "/api/accounts/login/",
      "body": {
        "email": "{{email}}",
        "password": "{{password}}"
      },
      "expectedStatus": 200,
      "expectedCode": 200,
      "needAuth": false
    },
    {
      "name": "获取机器人列表",
      "method": "GET",
      "path": "/api/pm-robot/list",
      "expectedStatus": 200,
      "expectedCode": 200,
      "needAuth": true
    }
  ],

  // UI 测试配置
  "uiTests": [
    {
      "name": "登录功能测试",
      "url": "/login",
      "actions": [
        {
          "type": "fill",
          "selector": "#email",
          "value": "{{email}}"
        },
        {
          "type": "fill",
          "selector": "#password",
          "value": "{{password}}"
        },
        {
          "type": "click",
          "selector": "button[type='submit']"
        },
        {
          "type": "waitFor",
          "target": "navigation"
        },
        {
          "type": "assert",
          "check": "url",
          "expected": "/dashboard"
        }
      ]
    }
  ],

  // 报告配置
  "report": {
    "outputDir": "test_reports",
    "includeScreenshots": true,
    "includeRequestLogs": true
  }
}
```

---

## 测试报告模板

生成的测试报告包含以下部分：

```markdown
# 部署测试报告

## 测试概览

| 项目 | 内容 |
|------|------|
| 项目名称 | MyProject |
| 测试时间 | 2026-01-05 14:30:00 |
| 测试人员 | Your Name |
| 测试环境 | 本地开发环境 |

## 测试摘要

- 总测试项: 15
- 通过: 13
- 失败: 2
- 通过率: 86.7%

## 端口检测结果

[...]

## API 测试结果

[...]

## UI 测试结果

[...]

## 问题汇总

[...]

## 建议

[...]
```

---

## 常见问题

### Q1: 端口检测失败？

**原因**：服务未启动或端口被占用

**解决方案**：
```bash
# 检查服务状态
netstat -ano | findstr :8000

# 启动服务
# 参考 windows-fullstack-deploy 技能
```

### Q2: API 测试失败？

**原因**：
1. 后端服务未启动
2. 数据库连接失败
3. 测试账号不存在

**解决方案**：
```bash
# 检查后端服务
curl http://localhost:8000/api/accounts/login/

# 创建测试账号
python manage.py createsuperuser
```

### Q3: UI 测试失败？

**原因**：
1. 前端服务未启动
2. 页面元素选择器错误
3. 页面加载超时

**解决方案**：
```bash
# 检查前端服务
curl http://localhost:8083

# 更新选择器
# 使用浏览器开发者工具检查元素
```

---

## 技能依赖

### Python 依赖

```bash
pip install requests playwright
playwright install chromium
```

### MCP 服务器

需要安装浏览器 MCP 服务器才能运行 UI 测试。

---

## 清理测试文件

测试完成后，手动删除测试相关文件：

```bash
# 删除测试脚本文件夹
rm -rf scripts/

# 删除测试报告（可选）
rm -rf test_reports/

# 删除配置文件（可选）
rm test.config.json
```

---

## 相关技能

- [windows-fullstack-deploy](../windows-fullstack-deploy/) - Windows 本地部署技能
- [webapp-testing](../webapp-testing/) - Web 应用测试技能

---

**技能版本**: 1.0
**最后更新**: 2026-01-05
**适用平台**: Windows 10/11
**适用项目**: Django + Vue 全栈项目