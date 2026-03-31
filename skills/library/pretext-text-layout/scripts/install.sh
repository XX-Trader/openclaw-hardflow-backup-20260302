#!/usr/bin/env bash
# install.sh - Pretext 技能一键安装脚本
# 用法: bash install.sh [--global]
#
# 自动检测环境并安装 @chenglou/pretext 及所需依赖
# - 浏览器环境: 只需 @chenglou/pretext
# - Node.js 环境: 额外需要 canvas 包作为 polyfill

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

echo "=========================================="
echo "  Pretext 文本布局技能安装"
echo "=========================================="
echo ""

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo "❌ 未检测到 Node.js，请先安装 Node.js >= 16"
    exit 1
fi

NODE_VERSION=$(node -v | sed 's/v//' | cut -d. -f1)
echo "✅ Node.js $(node -v)"

if [ "$NODE_VERSION" -lt 16 ]; then
    echo "⚠️ Node.js 版本过低 (需要 >= 16)，请升级"
    exit 1
fi

# 检查 npm
if ! command -v npm &> /dev/null; then
    echo "❌ 未检测到 npm"
    exit 1
fi
echo "✅ npm $(npm -v)"

# 安装核心包
echo ""
echo "[1/2] 安装 @chenglou/pretext ..."
if [[ "${1:-}" == "--global" ]]; then
    npm install -g @chenglou/pretext
else
    npm install @chenglou/pretext
fi
echo "✅ @chenglou/pretext 已安装"

# Node.js 环境需要 canvas polyfill
echo ""
echo "[2/2] 安装 canvas polyfill (Node.js 环境) ..."
if [[ "${1:-}" == "--global" ]]; then
    npm install -g canvas 2>/dev/null || echo "⚠️ canvas 安装失败 (可能缺少系统依赖)。浏览器环境可忽略。"
else
    npm install canvas 2>/dev/null || echo "⚠️ canvas 安装失败 (可能缺少系统依赖)。浏览器环境可忽略。"
fi

# canvas 系统依赖提示
echo ""
echo "📋 如果 canvas 安装失败，需要安装系统依赖:"
echo "   Ubuntu/Debian: sudo apt-get install -y build-essential libcairo2-dev libpango1.0-dev libjpeg-dev libgif-dev librsvg2-dev"
echo "   macOS:         brew install pkg-config cairo pango libpng jpeg giflib librsvg"
echo "   Alpine:        apk add build-base cairo-dev pango-dev jpeg-dev giflib-dev"
echo ""

# 验证安装
echo "=========================================="
echo "  验证安装"
echo "=========================================="
node -e "
  try {
    const { prepare, layout } = require('@chenglou/pretext');
    const p = prepare('Hello World 你好', '16px sans-serif');
    const r = layout(p, 200, 20);
    console.log('✅ Pretext 工作正常');
    console.log('   测试文本: \"Hello World 你好\"');
    console.log('   容器宽度: 200px, 行高: 20px');
    console.log('   计算结果: height=' + r.height + 'px, lines=' + r.lineCount);
  } catch(e) {
    console.log('⚠️ Pretext 加载失败:', e.message);
    console.log('   浏览器环境可正常使用，Node.js 环境需要 canvas 依赖');
  }
"

echo ""
echo "=========================================="
echo "  安装完成"
echo "=========================================="
echo ""
echo "快速测试溢出检测:"
echo "  node ${SKILL_DIR}/scripts/pretext-check-overflow.js --text '按钮文案很长很长' --font '14px Inter' --width 80 --line-height 20"
echo ""
