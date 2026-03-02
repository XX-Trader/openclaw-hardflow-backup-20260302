@echo off
REM ========================================
REM 项目自动检测脚本
REM ========================================
REM 功能：
REM   1. 检测后端类型和路径
REM   2. 检测前端类型和路径
REM   3. 设置环境变量供其他脚本使用
REM ========================================

SETLOCAL EnableDelayedExpansion

REM ========================================
REM 检测后端项目
REM ========================================

set "BACKEND_TYPE="
set "BACKEND_PATH="

REM 检测 Django
if exist "backend\manage.py" (
    set "BACKEND_TYPE=django"
    set "BACKEND_PATH=backend"
    goto :backend_found
)

if exist "server\manage.py" (
    set "BACKEND_TYPE=django"
    set "BACKEND_PATH=server"
    goto :backend_found
)

if exist "api\manage.py" (
    set "BACKEND_TYPE=django"
    set "BACKEND_PATH=api"
    goto :backend_found
)

REM 检测 FastAPI
if exist "backend\main.py" (
    findstr /i "fastapi" backend\main.py >nul 2>&1
    if not errorlevel 1 (
        set "BACKEND_TYPE=fastapi"
        set "BACKEND_PATH=backend"
        goto :backend_found
    )
)

REM 检测 Flask
if exist "backend\app.py" (
    set "BACKEND_TYPE=flask"
    set "BACKEND_PATH=backend"
    goto :backend_found
)

:backend_not_found
REM 后端未检测到，继续检测前端

REM ========================================
REM 检测前端项目
REM ========================================

:backend_found
set "FRONTEND_TYPE="
set "FRONTEND_PATH="

REM 检测 Vue
if exist "frontend\package.json" (
    findstr /i "vue" frontend\package.json >nul 2>&1
    if not errorlevel 1 (
        set "FRONTEND_TYPE=vue"
        set "FRONTEND_PATH=frontend"
        goto :frontend_found
    )
)

if exist "client\package.json" (
    findstr /i "vue" client\package.json >nul 2>&1
    if not errorlevel 1 (
        set "FRONTEND_TYPE=vue"
        set "FRONTEND_PATH=client"
        goto :frontend_found
    )
)

REM 检测 React
if exist "frontend\package.json" (
    findstr /i "react" frontend\package.json >nul 2>&1
    if not errorlevel 1 (
        set "FRONTEND_TYPE=react"
        set "FRONTEND_PATH=frontend"
        goto :frontend_found
    )
)

:frontend_not_found

REM ========================================
REM 输出检测结果
REM ========================================

:frontend_found
REM 检测完成，返回结果

ENDLOCAL & (
    if defined BACKEND_TYPE set "BACKEND_TYPE=%BACKEND_TYPE%"
    if defined BACKEND_PATH set "BACKEND_PATH=%BACKEND_PATH%"
    if defined FRONTEND_TYPE set "FRONTEND_TYPE=%FRONTEND_TYPE%"
    if defined FRONTEND_PATH set "FRONTEND_PATH=%FRONTEND_PATH%"
)
