@echo off
REM ========================================
REM 初始化配置向导
REM ========================================
REM 功能：
REM   1. 自动检测项目结构
REM   2. 检测后端/前端类型
REM   3. 生成配置文件
REM ========================================

SETLOCAL EnableDelayedExpansion

REM 颜色定义
set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "BLUE=[94m"
set "CYAN=[96m"
set "NC=[0m"

cls
echo.
echo %CYAN%========================================%NC%
echo %CYAN%  Windows 全栈项目部署配置向导%NC%
echo %CYAN%========================================%NC%
echo.

REM 检查是否在项目根目录
if not exist "deploy.config.json" (
    echo %YELLOW%[*] 首次运行，开始检测项目...%NC%
) else (
    echo %YELLOW%[*] 配置文件已存在，将重新生成%NC%
)
echo.

REM ========================================
REM 步骤 1: 检测后端项目
REM ========================================
echo %CYAN%[1/5] 检测后端项目...%NC%

set "BACKEND_TYPE="
set "BACKEND_PATH="
set "BACKEND_PORT=8000"

REM 检测标准路径 backend/
if exist "backend\manage.py" (
    set "BACKEND_TYPE=django"
    set "BACKEND_PATH=backend"
    echo %GREEN%  ✓ 发现 Django 后端: backend\%NC%
    goto :backend_found
)

if exist "backend\main.py" (
    findstr /i "fastapi" backend\main.py >nul 2>&1
    if not errorlevel 1 (
        set "BACKEND_TYPE=fastapi"
        set "BACKEND_PATH=backend"
        echo %GREEN%  ✓ 发现 FastAPI 后端: backend\%NC%
        goto :backend_found
    )
)

if exist "backend\app.py" (
    set "BACKEND_TYPE=flask"
    set "BACKEND_PATH=backend"
    echo %GREEN%  ✓ 发现 Flask 后端: backend\%NC%
    goto :backend_found
)

REM 检测其他可能的路径
if exist "server\manage.py" (
    set "BACKEND_TYPE=django"
    set "BACKEND_PATH=server"
    echo %GREEN%  ✓ 发现 Django 后端: server\%NC%
    goto :backend_found
)

if exist "api\manage.py" (
    set "BACKEND_TYPE=django"
    set "BACKEND_PATH=api"
    echo %GREEN%  ✓ 发现 Django 后端: api\%NC%
    goto :backend_found
)

REM 未检测到后端
echo %RED%  [!] 未检测到后端项目%NC%
echo %YELLOW%  支持的路径: backend/, server/, api/%NC%
echo.
set /p "BACKEND_PATH=请输入后端路径（留空跳过后端配置）: "
if "!BACKEND_PATH!"=="" goto :frontend_detect
if exist "!BACKEND_PATH!\manage.py" (
    set "BACKEND_TYPE=django"
    echo %GREEN%  ✓ 检测到 Django 项目%NC%
) else (
    echo %RED%  [错误] 路径不存在或不支持%NC%
    pause
    exit /b 1
)

:backend_found
echo.

REM ========================================
REM 步骤 2: 检测前端项目
REM ========================================
:frontend_detect
echo %CYAN%[2/5] 检测前端项目...%NC%

set "FRONTEND_TYPE="
set "FRONTEND_PATH="
set "FRONTEND_PORT=8083"

REM 检测标准路径 frontend/
if exist "frontend\package.json" (
    findstr /i "vue" frontend\package.json >nul 2>&1
    if not errorlevel 1 (
        set "FRONTEND_TYPE=vue"
        set "FRONTEND_PATH=frontend"
        echo %GREEN%  ✓ 发现 Vue 前端: frontend\%NC%
        goto :frontend_found
    )

    findstr /i "react" frontend\package.json >nul 2>&1
    if not errorlevel 1 (
        set "FRONTEND_TYPE=react"
        set "FRONTEND_PATH=frontend"
        echo %GREEN%  ✓ 发现 React 前端: frontend\%NC%
        goto :frontend_found
    )
)

REM 检测其他可能的路径
if exist "client\package.json" (
    findstr /i "vue" client\package.json >nul 2>&1
    if not errorlevel 1 (
        set "FRONTEND_TYPE=vue"
        set "FRONTEND_PATH=client"
        echo %GREEN%  ✓ 发现 Vue 前端: client\%NC%
        goto :frontend_found
    )
)

if exist "web\package.json" (
    findstr /i "vue" web\package.json >nul 2>&1
    if not errorlevel 1 (
        set "FRONTEND_TYPE=vue"
        set "FRONTEND_PATH=web"
        echo %GREEN%  ✓ 发现 Vue 前端: web\%NC%
        goto :frontend_found
    )
)

REM 未检测到前端
echo %RED%  [!] 未检测到前端项目%NC%
echo %YELLOW%  支持的路径: frontend/, client/, web/%NC%
echo.
set /p "FRONTEND_PATH=请输入前端路径（留空跳过前端配置）: "
if "!FRONTEND_PATH!"=="" goto :env_detect
if exist "!FRONTEND_PATH!\package.json" (
    set "FRONTEND_TYPE=vue"
    echo %GREEN%  ✓ 检测到前端项目%NC%
) else (
    echo %RED%  [错误] 路径不存在%NC%
    pause
    exit /b 1
)

:frontend_found
echo.

REM ========================================
REM 步骤 3: 检测环境依赖
REM ========================================
:env_detect
echo %CYAN%[3/5] 检测环境依赖...%NC%

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo %RED%  [✗] Python 未安装%NC%
) else (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PY_VER=%%i
    echo %GREEN%  ✓ Python 已安装: %PY_VER%%NC%
)

REM 检查 Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo %RED%  [✗] Node.js 未安装%NC%
) else (
    for /f "tokens=1" %%i in ('node --version') do set NODE_VER=%%i
    echo %GREEN%  ✓ Node.js 已安装: !NODE_VER!%NC%
)

REM 检查 MySQL
sc query MySQL80 >nul 2>&1
if not errorlevel 1 (
    echo %GREEN%  ✓ MySQL 服务已安装: MySQL80%NC%
) else (
    sc query MySQL >nul 2>&1
    if not errorlevel 1 (
        echo %GREEN%  ✓ MySQL 服务已安装: MySQL%NC%
    ) else (
        echo %YELLOW%  [!] MySQL 服务未找到%NC%
    )
)

REM 检查 WSL/Redis
wsl --version >nul 2>&1
if errorlevel 1 (
    echo %YELLOW%  [!] WSL 未安装（Redis 需要使用 WSL）%NC%
) else (
    echo %GREEN%  ✓ WSL 已安装%NC%
)

echo.

REM ========================================
REM 步骤 4: 显示配置信息
REM ========================================
echo %CYAN%[4/5] 项目配置信息:%NC%
echo.
echo %BLUE%----------------------------------------%NC%
if defined BACKEND_TYPE (
    echo 后端类型: %BACKEND_TYPE%
    echo 后端路径: %BACKEND_PATH%\
    echo 后端端口: %BACKEND_PORT%
)
if defined FRONTEND_TYPE (
    echo 前端类型: %FRONTEND_TYPE%
    echo 前端路径: %FRONTEND_PATH%\
    echo 前端端口: %FRONTEND_PORT%
)
echo 数据库: MySQL (端口 3306)
echo 缓存: Redis (端口 6379, WSL)
echo %BLUE%----------------------------------------%NC%
echo.

REM ========================================
REM 步骤 5: 确认并生成配置
REM ========================================
echo %CYAN%[5/5] 生成配置文件...%NC%
echo.

set /p "CONFIRM=是否使用默认配置? (Y/N): "
if /i not "%CONFIRM%"=="Y" (
    echo.
    echo 自定义配置:
    set /p "PROJECT_NAME=项目名称: "
    if defined BACKEND_TYPE set /p "BACKEND_PORT=后端端口 (8000): "
    if defined FRONTEND_TYPE set /p "FRONTEND_PORT=前端端口 (8083): "
)

REM 生成 JSON 配置文件
echo {> deploy.config.json
echo   "version": "1.0",>> deploy.config.json
echo   "projectName": "%PROJECT_NAME%",>> deploy.config.json
echo   "projectType": "fullstack",>> deploy.config.json
echo   "autoDetected": true,>> deploy.config.json
echo.>> deploy.config.json
echo   "services": {>> deploy.config.json

REM 后端配置
if defined BACKEND_TYPE (
    echo     "backend": {>> deploy.config.json
    echo       "enabled": true,>> deploy.config.json
    echo       "type": "%BACKEND_TYPE%",>> deploy.config.json
    echo       "path": "%BACKEND_PATH%",>> deploy.config.json
    echo       "port": %BACKEND_PORT%>> deploy.config.json
    echo     }>> deploy.config.json
) else (
    echo     "backend": {>> deploy.config.json
    echo       "enabled": false>> deploy.config.json
    echo     }>> deploy.config.json
)

REM 前端配置
if defined FRONTEND_TYPE (
    echo     ,>> deploy.config.json
    echo     "frontend": {>> deploy.config.json
    echo       "enabled": true,>> deploy.config.json
    echo       "type": "%FRONTEND_TYPE%",>> deploy.config.json
    echo       "path": "%FRONTEND_PATH%",>> deploy.config.json
    echo       "port": %FRONTEND_PORT%>> deploy.config.json
    echo     }>> deploy.config.json
) else (
    echo     ,>> deploy.config.json
    echo     "frontend": {>> deploy.config.json
    echo       "enabled": false>> deploy.config.json
    echo     }>> deploy.config.json
)

echo   }>> deploy.config.json
echo }>> deploy.config.json

echo.
echo %GREEN%[✓] 配置文件已生成: deploy.config.json%NC%

REM 检查是否存在 .env.local
if not exist ".env.local" (
    echo.
    echo %YELLOW%[*] 提示: 请创建环境变量文件%NC%
    echo   copy templates\.env.local.example .env.local
    echo.
)

echo.
echo %CYAN%========================================%NC%
echo %CYAN%  配置完成！%NC%
echo %CYAN%========================================%NC%
echo.
echo %BLUE%下一步操作:%NC%
echo   1. 检查 deploy.config.json（如需修改）
echo   2. 创建环境变量文件:
echo      copy templates\.env.local.example .env.local
echo   3. 启动所有服务:
echo      scripts\start-all.bat
echo.
echo %YELLOW%[*] 按任意键退出，或按 S 立即启动服务...%NC%
pause >nul
