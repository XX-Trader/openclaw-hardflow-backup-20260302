@echo off
chcp 65001 >nul
echo ========================================
echo 旅游技能 MCP 服务启动脚本
echo ========================================
echo.

cd /d "%~dp0"

echo 检查依赖安装...
if not exist "node_modules\" (
    echo [!] 未检测到 node_modules，正在安装依赖...
    call npm install
    if errorlevel 1 (
        echo [X] 依赖安装失败！
        pause
        exit /b 1
    )
    echo [√] 依赖安装完成
    echo.
)

echo 检查环境变量配置...
if not exist ".env" (
    echo [!] 未检测到 .env 文件！
    echo [!] 请先复制 .env.example 为 .env 并填入你的密钥
    echo.
    copy .env.example .env >nul
    echo [√] 已创建 .env 模板文件
    echo [!] 请编辑 .env 文件，填入以下密钥：
    echo     - XHS_COOKIE（小红书 Cookie）
    echo     - BAIDU_MAP_API_KEY（百度地图 API Key）
    echo.
    pause
    exit /b 1
)

echo [√] 环境变量配置文件存在
echo.

echo ========================================
echo 启动旅游相关 MCP 服务
echo ========================================
echo.
echo 服务列表：
echo   1. 高德地图 MCP - 天气、POI、周边搜索
echo   2. 百度地图 MCP - 路线规划、地图可视化
echo   3. 小红书 MCP - 攻略采集、用户评价
echo.
echo 正在启动服务...
echo.

echo [1/3] 启动高德地图 MCP...
start "高德地图MCP" cmd /k "npm run amap"

timeout /t 2 /nobreak >nul

echo [2/3] 启动百度地图 MCP...
start "百度地图MCP" cmd /k "npm run baidu"

timeout /t 2 /nobreak >nul

echo [3/3] 启动小红书 MCP...
start "小红书MCP" cmd /k "npm run xhs"

echo.
echo ========================================
echo [√] 所有 MCP 服务已启动
echo ========================================
echo.
echo 提示：
echo   - 每个服务会在独立窗口中运行
echo   - 关闭窗口即停止对应服务
echo   - 请在 Claude Code 中测试服务是否正常
echo.
echo 按任意键退出本启动窗口...
pause >nul
