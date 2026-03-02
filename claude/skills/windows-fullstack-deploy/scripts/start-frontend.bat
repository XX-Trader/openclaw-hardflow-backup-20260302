@echo off
REM ========================================
REM 前端启动脚本
REM ========================================
REM 支持框架: Vue、React
REM 构建工具: Vite、Webpack
REM ========================================

SETLOCAL EnableDelayedExpansion

REM 颜色定义
set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "BLUE=[94m"
set "NC=[0m"

REM 设置项目根目录
set "PROJECT_DIR=%~dp0.."
cd /d "%PROJECT_DIR%"

REM ========================================
REM 读取配置文件
REM ========================================

set "FRONTEND_TYPE=vue"
set "FRONTEND_PATH=frontend"
set "FRONTEND_PORT=8083"

REM 简单解析配置文件（如果存在）
if exist "deploy.config.json" (
    REM 查找前端类型
    findstr /i "vue" deploy.config.json >nul 2>&1
    if not errorlevel 1 set "FRONTEND_TYPE=vue"

    findstr /i "react" deploy.config.json >nul 2>&1
    if not errorlevel 1 set "FRONTEND_TYPE=react"
)

REM 切换到前端目录
if exist "%FRONTEND_PATH%" (
    cd /d "%FRONTEND_PATH%"
) else (
    echo %RED%[错误] 前端目录不存在: %FRONTEND_PATH%%NC%
    pause
    exit /b 1
)

echo.
echo %BLUE%========================================%NC%
echo %BLUE%  前端服务启动 (%FRONTEND_TYPE%)%NC%
echo %BLUE%========================================%NC%
echo.

REM ========================================
REM 检查 Node.js 环境
REM ========================================
echo %YELLOW%[*] 检查 Node.js 环境...%NC%
node --version >nul 2>&1
if errorlevel 1 (
    echo %RED%[错误] 未找到 Node.js！%NC%
    echo %YELLOW%请先安装 Node.js (版本要求: ^20.19.0 或 >=22.12.0)%NC%
    echo %YELLOW%下载地址: https://nodejs.org/%NC%
    pause
    exit /b 1
)

for /f "tokens=1" %%i in ('node --version') do set NODE_VERSION=%%i
echo %GREEN%[✓] Node.js 已安装: %NODE_VERSION%%NC%
echo.

REM ========================================
REM 检查 npm
REM ========================================
echo %YELLOW%[*] 检查 npm...%NC%
npm --version >nul 2>&1
if errorlevel 1 (
    echo %RED%[错误] npm 未找到！%NC%
    pause
    exit /b 1
)
echo %GREEN%[✓] npm 正常%NC%
echo.

REM ========================================
REM 安装依赖
REM ========================================
if not exist "node_modules\" (
    echo %YELLOW%[*] 安装项目依赖...%NC%
    echo %BLUE%(这可能需要几分钟，请耐心等待...)%NC%
    echo.
    npm install
    if errorlevel 1 (
        echo %RED%[错误] 依赖安装失败！%NC%
        echo %YELLOW%建议:%NC%
        echo %YELLOW%  1. 检查网络连接%NC%
        echo %YELLOW%  2. 尝试切换 npm 源: npm config set registry https://registry.npmmirror.com%NC%
        pause
        exit /b 1
    )
    echo.
    echo %GREEN%[✓] 依赖安装完成%NC%
    echo.
) else (
    echo %GREEN%[✓] 依赖已安装%NC%
    echo.
)

REM ========================================
REM 选择启动端口
REM ========================================
echo %BLUE%----------------------------------------%NC%
echo %BLUE%启动选项:%NC%
echo %BLUE%----------------------------------------%NC%
echo %GREEN%1.%NC% 开发模式 - 端口 8080
echo %GREEN%2.%NC% 开发模式 - 端口 8081
echo %GREEN%3.%NC% 开发模式 - 端口 8082
echo %GREEN%4.%NC% 开发模式 - 端口 8083（默认）
echo %GREEN%5.%NC% 生产构建
echo %GREEN%6.%NC% 预览构建结果
echo.
set /p "CHOICE=请选择启动模式 (1-6): "

if "%CHOICE%"=="1" set "VITE_PORT=8080"
if "%CHOICE%"=="2" set "VITE_PORT=8081"
if "%CHOICE%"=="3" set "VITE_PORT=8082"
if "%CHOICE%"=="4" set "VITE_PORT=8083"
if "%CHOICE%"=="5" goto :build
if "%CHOICE%"=="6" goto :preview

if not defined VITE_PORT set "VITE_PORT=8083"

REM ========================================
REM 启动开发服务器
REM ========================================
echo.
echo %YELLOW%[*] 启动开发服务器...%NC%
echo %BLUE%========================================%NC%
echo %BLUE%  前端服务地址:%NC%
echo %GREEN%     http://localhost:%VITE_PORT%%NC%
echo %BLUE%========================================%NC%
echo.
echo %YELLOW%[*] 按 Ctrl+C 停止服务器%NC%
echo.

REM 根据项目类型启动
if exist "package.json" (
    REM 检查是否使用 Vite
    findstr /i "vite" package.json >nul 2>&1
    if not errorlevel 1 (
        npm run dev -- --port %VITE_PORT%
        goto :end
    )

    REM React 项目
    findstr /i "react" package.json >nul 2>&1
    if not errorlevel 1 (
        set "PORT=%VITE_PORT%"
        npm start
        goto :end
    )

    REM Vue 项目
    findstr /i "vue" package.json >nul 2>&1
    if not errorlevel 1 (
        npm run dev -- --port %VITE_PORT%
        goto :end
    )

    REM 默认使用 npm start
    npm start
) else (
    echo %RED%[错误] 未找到 package.json%NC%
    pause
    exit /b 1
)

goto :end

:build
echo.
echo %YELLOW%[*] 执行生产构建...%NC%
npm run build
if errorlevel 1 (
    echo %RED%[错误] 构建失败！%NC%
    pause
    exit /b 1
)
echo.
echo %GREEN%[✓] 构建完成！文件位于: dist\%NC%
pause
goto :end

:preview
echo.
echo %YELLOW%[*] 预览构建结果...%NC%
if not exist "dist\" (
    echo %RED%[错误] 未找到构建文件！请先执行构建（选项 5）%NC%
    pause
    exit /b 1
)
npm run preview
goto :end

:end
echo.
echo %GREEN%[*] 服务已停止%NC%
pause

ENDLOCAL
