@echo off
REM ========================================
REM MySQL 服务管理脚本
REM ========================================

SETLOCAL EnableDelayedExpansion

REM 颜色定义
set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "NC=[0m"

REM 尝试检测 MySQL 服务名称
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

sc query mysql57 >nul 2>&1
if not errorlevel 1 (
    set "MYSQL_SERVICE=mysql57"
    goto :service_found
)

REM 未找到 MySQL 服务
echo %RED%[错误] 未找到 MySQL 服务！%NC%
echo.
echo %YELLOW%请先安装 MySQL:%NC%
echo %YELLOW%  下载地址: https://dev.mysql.com/downloads/mysql/%NC%
echo %YELLOW%  推荐版本: MySQL 8.0+%NC%
echo.
exit /b 1

:service_found
echo %GREEN%[✓] 找到 MySQL 服务: %MYSQL_SERVICE%%NC%
echo.

REM 检查服务状态
sc query %MYSQL_SERVICE% | findstr STATE | findstr RUNNING >nul 2>&1
if not errorlevel 1 (
    echo %GREEN%[✓] MySQL 服务已运行%NC%
) else (
    echo %YELLOW%[*] 启动 MySQL 服务...%NC%
    net start %MYSQL_SERVICE%
    if errorlevel 1 (
        echo %RED%[错误] MySQL 服务启动失败！%NC%
        echo %YELLOW%请检查:%NC%
        echo %YELLOW%  1. MySQL 是否已正确安装%NC%
        echo %YELLOW%  2. 端口 3306 是否被占用%NC%
        exit /b 1
    )
    echo %GREEN%[✓] MySQL 服务已启动%NC%
)
echo.

echo MySQL 连接信息:
echo   主机: 127.0.0.1
echo   端口: 3306
echo.

ENDLOCAL
