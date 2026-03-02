#!/bin/bash
# OpenClaw 快速部署脚本
# 用法: bash deploy.sh

set -e

echo "=========================================="
echo "  OpenClaw 服务器部署脚本"
echo "=========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 检测系统
if [ -f /etc/centos-release ]; then
    PKG_MANAGER="dnf"
    echo -e "${GREEN}检测到 CentOS/RHEL 系统${NC}"
elif [ -f /etc/lsb-release ]; then
    PKG_MANAGER="apt"
    echo -e "${GREEN}检测到 Ubuntu/Debian 系统${NC}"
else
    echo -e "${YELLOW}未检测到支持的系统，尝试使用 dnf${NC}"
    PKG_MANAGER="dnf"
fi

# 1. 添加 Swap
echo ""
echo -e "${YELLOW}[1/7] 检查 Swap...${NC}"
if [ ! -f /swapfile ]; then
    echo "添加 2GB Swap..."
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo -e "${GREEN}Swap 添加完成${NC}"
else
    echo -e "${GREEN}Swap 已存在${NC}"
fi

# 2. 安装依赖
echo ""
echo -e "${YELLOW}[2/7] 安装系统依赖...${NC}"
if [ "$PKG_MANAGER" = "dnf" ]; then
    dnf install -y cmake gcc gcc-c++ make git curl
else
    apt update && apt install -y build-essential cmake git curl
fi
echo -e "${GREEN}依赖安装完成${NC}"

# 3. 检查 Node.js
echo ""
echo -e "${YELLOW}[3/7] 检查 Node.js...${NC}"
if ! command -v node &> /dev/null; then
    echo "请先安装 Node.js v18+"
    echo "推荐使用 nvm 安装:"
    echo "  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash"
    echo "  source ~/.bashrc"
    echo "  nvm install 22"
    exit 1
fi
NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "Node.js 版本过低，需要 v18+"
    exit 1
fi
echo -e "${GREEN}Node.js $(node -v)${NC}"

# 4. 安装 OpenClaw
echo ""
echo -e "${YELLOW}[4/7] 安装 OpenClaw...${NC}"
npm install -g openclaw
openclaw setup
mkdir -p ~/.openclaw/workspace
mkdir -p ~/.openclaw/agents/main/agent
mkdir -p ~/.openclaw/agents/main/sessions
echo -e "${GREEN}OpenClaw 安装完成: $(openclaw --version)${NC}"

# 5. 安装 ClawHub
echo ""
echo -e "${YELLOW}[5/7] 安装 ClawHub...${NC}"
npm install -g clawhub
echo -e "${GREEN}ClawHub 安装完成${NC}"

# 6. 生成 Gateway Token
echo ""
echo -e "${YELLOW}[6/7] 生成 Gateway Token...${NC}"
GATEWAY_TOKEN=$(openssl rand -hex 16)
openclaw config set gateway.auth.token "$GATEWAY_TOKEN"
echo -e "${GREEN}Gateway Token: $GATEWAY_TOKEN${NC}"

# 7. 创建 Systemd 服务
echo ""
echo -e "${YELLOW}[7/7] 创建 Systemd 服务...${NC}"
cat > /etc/systemd/system/openclaw.service << 'EOF'
[Unit]
Description=OpenClaw Gateway
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
ExecStart=/usr/bin/openclaw gateway --port 18789
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable openclaw
systemctl start openclaw
echo -e "${GREEN}服务创建完成${NC}"

# 完成
echo ""
echo "=========================================="
echo -e "${GREEN}  OpenClaw 安装完成!${NC}"
echo "=========================================="
echo ""
echo "Dashboard: http://127.0.0.1:18789/"
echo "Gateway Token: $GATEWAY_TOKEN"
echo ""
echo "下一步:"
echo "  1. 配置 AI 模型: 编辑 ~/.openclaw/openclaw.json"
echo "  2. 配置 Telegram: openclaw config set channels.telegram.botToken 'YOUR_TOKEN'"
echo "  3. 重启服务: systemctl restart openclaw"
echo "  4. 查看状态: openclaw status"
echo ""
