@echo off
REM ========================================
REM Redis 服务管理脚本（WSL）
REM ========================================

SETLOCAL EnableDelayedExpansion

REM 颜色定义
set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "BLUE=[94m"
set "NC=[0m"

REM 检查 WSL
wsl --version >nul 2>&1
if errorlevel 1 (
    echo %RED%[错误] 未找到 WSL！%NC%
    echo.
    echo %YELLOW%请先安装 WSL:%NC%
    echo %YELLOW%  1. 以管理员身份运行 PowerShell%NC%
    echo %YELLOW%  2. 执行: wsl --install%NC%
    echo %YELLOW%  3. 重启计算机%NC%
    echo.
    pause
    exit /b 1
)
echo %GREEN%[✓] WSL 环境正常%NC%
echo.

REM 检查 Redis 是否已安装
wsl redis-cli --version >nul 2>&1
if errorlevel 1 (
    echo %YELLOW%[!] Redis 未安装，正在安装...%NC%
    echo.
    echo %BLUE%安装方法（推荐自动安装）:%NC%
    echo.
    wsl sudo apt-get update
    wsl sudo apt-get install -y redis-server
    wsl sudo sed -i 's/supervised no/supervised systemd/g' /etc/redis/redis.conf
    echo.
    echo %GREEN%[✓] Redis 安装完成！%NC%
) else (
    echo %GREEN%[✓] Redis 已安装%NC%
)
echo.

REM 启动 Redis
echo %YELLOW%[*] 启动 Redis 服务...%NC%
wsl sudo service redis-server start
echo.

echo Redis 连接信息:
echo   主机: 127.0.0.1
echo   端口: 6379
echo.

REM 测试连接
echo %YELLOW%[*] 测试连接...%NC%
wsl redis-cli ping
if errorlevel 1 (
    echo %RED%[警告] Redis 连接测试失败%NC%
) else (
    echo %GREEN%[✓] Redis 连接正常%NC%
)
echo.

echo %YELLOW%[*] 按 Ctrl+C 停止服务%NC%
echo.

ENDLOCAL
