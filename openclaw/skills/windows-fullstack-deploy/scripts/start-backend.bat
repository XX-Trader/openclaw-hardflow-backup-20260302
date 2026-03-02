@echo off
REM ========================================
REM 后端启动脚本
REM ========================================
REM 支持框架: Django、FastAPI、Flask
REM ========================================

SETLOCAL EnableDelayedExpansion

REM 颜色定义
set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "BLUE=[94m"
set "NC=[0m"

REM 设置项目根目录（脚本所在目录的上级目录）
set "PROJECT_DIR=%~dp0.."
cd /d "%PROJECT_DIR%"

REM ========================================
REM 读取配置文件
REM ========================================

set "BACKEND_TYPE=django"
set "BACKEND_PATH=backend"
set "BACKEND_PORT=8000"

REM 简单解析配置文件（如果存在）
if exist "deploy.config.json" (
    REM 查找后端类型
    findstr /i "django" deploy.config.json >nul 2>&1
    if not errorlevel 1 set "BACKEND_TYPE=django"

    findstr /i "fastapi" deploy.config.json >nul 2>&1
    if not errorlevel 1 set "BACKEND_TYPE=fastapi"

    findstr /i "flask" deploy.config.json >nul 2>&1
    if not errorlevel 1 set "BACKEND_TYPE=flask"
)

REM 切换到后端目录
if exist "%BACKEND_PATH%" (
    cd /d "%BACKEND_PATH%"
) else (
    echo %RED%[错误] 后端目录不存在: %BACKEND_PATH%%NC%
    pause
    exit /b 1
)

echo.
echo %BLUE%========================================%NC%
echo %BLUE%  后端服务启动 (%BACKEND_TYPE%)%NC%
echo %BLUE%========================================%NC%
echo.

REM ========================================
REM 检查 Python 环境
REM ========================================
echo %YELLOW%[*] 检查 Python 环境...%NC%
python --version >nul 2>&1
if errorlevel 1 (
    echo %RED%[错误] 未找到 Python！%NC%
    pause
    exit /b 1
)
echo %GREEN%[✓] Python 环境正常%NC%
echo.

REM ========================================
REM 检查虚拟环境
REM ========================================
echo %YELLOW%[*] 检查虚拟环境...%NC%
if not exist "venv\" (
    echo %YELLOW%[*] 创建虚拟环境...%NC%
    python -m venv venv
    if errorlevel 1 (
        echo %RED%[错误] 创建虚拟环境失败%NC%
        pause
        exit /b 1
    )
    echo %GREEN%[✓] 虚拟环境创建成功%NC%
)

REM 激活虚拟环境
echo %YELLOW%[*] 激活虚拟环境...%NC%
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo %RED%[错误] 激活虚拟环境失败%NC%
    pause
    exit /b 1
)
echo %GREEN%[✓] 虚拟环境已激活%NC%
echo.

REM ========================================
REM 安装依赖
REM ========================================
echo %YELLOW%[*] 检查依赖包...%NC%
if exist "requirements.txt" (
    pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo %RED%[错误] 依赖安装失败%NC%
        pause
        exit /b 1
    )
    echo %GREEN%[✓] 依赖包正常%NC%
) else (
    echo %YELLOW%[!] 未找到 requirements.txt%NC%
)
echo.

REM ========================================
REM 数据库迁移（仅 Django）
REM ========================================
if "%BACKEND_TYPE%"=="django" (
    if exist "manage.py" (
        echo %YELLOW%[*] 检查数据库迁移...%NC%
        python manage.py showmigrations 2>nul | findstr "[X]" >nul 2>&1
        if errorlevel 1 (
            echo %YELLOW%[!] 数据库未迁移，正在执行迁移...%NC%
            python manage.py makemigrations
            python manage.py migrate
            if errorlevel 1 (
                echo %RED%[错误] 数据库迁移失败%NC%
                pause
                exit /b 1
            )
            echo %GREEN%[✓] 数据库迁移完成%NC%
        ) else (
            echo %GREEN%[✓] 数据库迁移正常%NC%
        )
        echo.
    )
)

REM ========================================
REM 启动服务
REM ========================================
echo %YELLOW%[*] 启动后端服务...%NC%
echo %BLUE%========================================%NC%
echo %BLUE%  后端服务地址:%NC%
echo %GREEN%     http://localhost:%BACKEND_PORT%%NC%
echo %BLUE%========================================%NC%
echo.
echo %YELLOW%[*] 按 Ctrl+C 停止服务器%NC%
echo.

if "%BACKEND_TYPE%"=="django" (
    if exist "manage.py" (
        python manage.py runserver 0.0.0.0:%BACKEND_PORT%
    )
) else if "%BACKEND_TYPE%"=="fastapi" (
    if exist "main.py" (
        pip install uvicorn >nul 2>&1
        uvicorn main:app --reload --host 0.0.0.0 --port %BACKEND_PORT%
    )
) else if "%BACKEND_TYPE%"=="flask" (
    if exist "app.py" (
        python app.py
    ) else if exist "wsgi.py" (
        python wsgi.py
    )
)

pause
