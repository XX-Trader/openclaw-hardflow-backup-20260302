#!/bin/bash

# 旅游技能 MCP 服务启动脚本 (Linux/Mac)

echo "========================================"
echo "旅游技能 MCP 服务启动脚本"
echo "========================================"
echo ""

# 进入脚本所在目录
cd "$(dirname "$0")"

# 检查依赖
echo "检查依赖安装..."
if [ ! -d "node_modules" ]; then
    echo "[!] 未检测到 node_modules，正在安装依赖..."
    npm install
    if [ $? -ne 0 ]; then
        echo "[X] 依赖安装失败！"
        exit 1
    fi
    echo "[√] 依赖安装完成"
    echo ""
fi

# 检查环境变量
echo "检查环境变量配置..."
if [ ! -f ".env" ]; then
    echo "[!] 未检测到 .env 文件！"
    echo "[!] 请先复制 .env.example 为 .env 并填入你的密钥"
    echo ""
    cp .env.example .env
    echo "[√] 已创建 .env 模板文件"
    echo "[!] 请编辑 .env 文件，填入以下密钥："
    echo "    - XHS_COOKIE（小红书 Cookie）"
    echo "    - BAIDU_MAP_API_KEY（百度地图 API Key）"
    echo ""
    exit 1
fi

echo "[√] 环境变量配置文件存在"
echo ""

echo "========================================"
echo "启动旅游相关 MCP 服务"
echo "========================================"
echo ""
echo "服务列表："
echo "  1. 高德地图 MCP - 天气、POI、周边搜索"
echo "  2. 百度地图 MCP - 路线规划、地图可视化"
echo "  3. 小红书 MCP - 攻略采集、用户评价"
echo ""
echo "正在启动服务..."
echo ""

# 后台启动服务
echo "[1/3] 启动高德地图 MCP..."
npm run amap &
AMAP_PID=$!
sleep 2

echo "[2/3] 启动百度地图 MCP..."
npm run baidu &
BAIDU_PID=$!
sleep 2

echo "[3/3] 启动小红书 MCP..."
npm run xhs &
XHS_PID=$!

echo ""
echo "========================================"
echo "[√] 所有 MCP 服务已在后台启动"
echo "========================================"
echo ""
echo "进程 PID："
echo "  高德地图: $AMAP_PID"
echo "  百度地图: $BAIDU_PID"
echo "  小红书:   $XHS_PID"
echo ""
echo "停止服务："
echo "  kill $AMAP_PID $BAIDU_PID $XHS_PID"
echo ""
echo "或在 Claude Code 中测试服务是否正常"
