@echo off
REM ========================================
REM 一键停止所有服务
REM ========================================
REM 功能：
REM   1. 停止后端服务窗口
REM   2. 停止前端服务窗口
REM   3. 停止 Redis 服务窗口
REM   4. 提示停止 MySQL（不自动停止）
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
echo %CYAN%  Windows 全栈项目 - 停止服务%NC%
echo %CYAN%========================================%NC%
echo.

REM ========================================
REM 步骤 1: 停止后端服务
REM ========================================
echo %YELLOW%[*] 停止后端服务...%NC%

tasklist | findstr /i "Backend Service" >nul 2>&1
if not errorlevel 1 (
    taskkill /FI "WINDOWTITLE eq Backend Service*" /F >nul 2>&1
    echo %GREEN%[✓] 后端服务已停止%NC%
) else (
    echo %YELLOW%[!] 后端服务未运行%NC%
)
echo.

REM ========================================
REM 步骤 2: 停止前端服务
REM ========================================
echo %YELLOW%[*] 停止前端服务...%NC%

tasklist | findstr /i "Frontend Service" >nul 2>&1
if not errorlevel 1 (
    taskkill /FI "WINDOWTITLE eq Frontend Service*" /F >nul 2>&1
    echo %GREEN%[✓] 前端服务已停止%NC%
) else (
    echo %YELLOW%[!] 前端服务未运行%NC%
)
echo.

REM ========================================
REM 步骤 3: 停止 Redis 服务
REM ========================================
echo %YELLOW%[*] 停止 Redis 服务...%NC%

tasklist | findstr /i "Redis Server" >nul 2>&1
if not errorlevel 1 (
    taskkill /FI "WINDOWTITLE eq Redis Server*" /F >nul 2>&1
    echo %GREEN%[✓] Redis 服务已停止%NC%
) else (
    echo %YELLOW%[!] Redis 服务未运行%NC%
)
echo.

REM ========================================
REM 步骤 4: MySQL 服务提示
REM ========================================
echo %YELLOW%[*] MySQL 服务...%NC%
echo %BLUE%  MySQL 服务保持运行，下次启动更快%NC%
echo %BLUE%  如需停止，请手动执行:%NC%
echo %GREEN%    net stop MySQL80%NC%
echo.

REM ========================================
REM 完成
REM ========================================
echo %CYAN%========================================%NC%
echo %CYAN%  所有服务已停止！%NC%
echo %CYAN%========================================%NC%
echo.

echo %YELLOW%[*] 如需重新启动，运行:%NC%
echo %GREEN%    scripts\start-all.bat%NC%
echo.

pause

ENDLOCAL
