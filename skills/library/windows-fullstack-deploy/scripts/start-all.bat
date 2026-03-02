@echo off
REM ========================================
REM 一键启动所有服务
REM ========================================
REM 功能：
REM   1. 读取配置文件
REM   2. 按顺序启动 MySQL、Redis、后端、前端
REM   3. 显示服务访问地址
REM ========================================

SETLOCAL EnableDelayedExpansion

REM 颜色定义
set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "BLUE=[94m"
set "CYAN=[96m"
set "NC=[0m"

echo.
echo %CYAN%========================================%NC%
echo %CYAN%  Windows 全栈项目 - 一键启动%NC%
echo %CYAN%========================================%NC%
echo.

REM ========================================
REM 步骤 1: 检查配置文件
REM ========================================
echo %YELLOW%[*] 检查配置文件...%NC%

if not exist "deploy.config.json" (
    echo %RED%[错误] 未找到配置文件！%NC%
    echo.
    echo %YELLOW%请先运行初始化向导:%NC%
    echo   scripts\init-config.bat
    echo.
    pause
    exit /b 1
)

echo %GREEN%[✓] 配置文件已找到%NC%
echo.

REM ========================================
REM 步骤 2: 启动 MySQL
REM ========================================
echo %CYAN%[1/4] 启动 MySQL 服务...%NC%
echo %BLUE%----------------------------------------%NC%

call "%~dp0start-mysql.bat"

if errorlevel 1 (
    echo %RED%[错误] MySQL 启动失败%NC%
    pause
    exit /b 1
)

echo.

REM ========================================
REM 步骤 3: 启动 Redis（异步）
REM ========================================
echo %CYAN%[2/4] 启动 Redis 服务...%NC%
echo %BLUE%----------------------------------------%NC%

start "Redis Server" cmd /k "call "%~dp0start-redis.bat""

REM 等待 Redis 启动
echo %YELLOW%[*] 等待 Redis 启动...%NC%
timeout /t 3 /nobreak >nul

echo %GREEN%[✓] Redis 已在后台启动%NC%
echo.

REM ========================================
REM 步骤 4: 启动后端（异步）
REM ========================================
echo %CYAN%[3/4] 启动后端服务...%NC%
echo %BLUE%----------------------------------------%NC%

REM 读取配置判断是否启用后端
findstr /c:"\"enabled\": false" deploy.config.json | findstr /c:"backend" >nul
if not errorlevel 1 (
    echo %YELLOW%[!] 后端服务已禁用（deploy.config.json）%NC%
) else (
    start "Backend Service" cmd /k "call "%~dp0start-backend.bat""

    REM 等待后端启动
    echo %YELLOW%[*] 等待后端启动...%NC%
    timeout /t 5 /nobreak >nul

    echo %GREEN%[✓] 后端已启动%NC%
)

echo.

REM ========================================
REM 步骤 5: 启动前端（异步）
REM ========================================
echo %CYAN%[4/4] 启动前端服务...%NC%
echo %BLUE%----------------------------------------%NC%

REM 读取配置判断是否启用前端
findstr /c:"\"enabled\": false" deploy.config.json | findstr /c:"frontend" >nul
if not errorlevel 1 (
    echo %YELLOW%[!] 前端服务已禁用（deploy.config.json）%NC%
) else (
    start "Frontend Service" cmd /k "call "%~dp0start-frontend.bat""

    REM 等待前端启动
    echo %YELLOW%[*] 等待前端启动...%NC%
    timeout /t 3 /nobreak >nul

    echo %GREEN%[✓] 前端已启动%NC%
)

echo.

REM ========================================
REM 步骤 6: 显示服务信息
REM ========================================
echo %CYAN%========================================%NC%
echo %CYAN%  所有服务已启动！%NC%
echo %CYAN%========================================%NC%
echo.

REM 从配置文件读取端口
set "FRONTEND_PORT=8083"
set "BACKEND_PORT=8000"

REM 简单解析 JSON 获取端口（bat 不支持复杂 JSON 解析）
for /f "tokens=2 delims=:" %%A in ('findstr /c:"\"port\"" deploy.config.json ^| findstr /n "." ^| findstr "^[0-9]*:.*frontend"') do (
    set "FRONTEND_PORT=%%A"
    set "FRONTEND_PORT=!FRONTEND_PORT: =!"
)

for /f "tokens=2 delims=:" %%A in ('findstr /c:"\"port\"" deploy.config.json ^| findstr /n "." ^| findstr "^[0-9]*:.*backend"') do (
    set "BACKEND_PORT=%%A"
    set "BACKEND_PORT=!BACKEND_PORT: =!"
)

echo %BLUE%服务访问地址:%NC%
echo   前端应用: %GREEN%http://localhost:!FRONTEND_PORT!%NC%
echo   后端 API: %GREEN%http://localhost:!BACKEND_PORT!%NC%
echo   数据库:   %GREEN%127.0.0.1:3306%NC%
echo   Redis:    %GREEN%127.0.0.1:6379%NC%
echo.

echo %YELLOW%[*] 所有服务窗口已打开，请勿关闭%NC%
echo %YELLOW%[*] 按 Ctrl+C 可停止各服务%NC%
echo.

echo %BLUE%========================================%NC%
echo.

pause
