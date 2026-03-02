#!/bin/bash
# ==============================================================================
# 交互式部署配置向导
# ==============================================================================
# 使用: bash scripts/init-config.sh
# 说明: 通过交互式问答生成部署配置文件
# ==============================================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}==>${NC} $1"
}

# 显示欢迎信息
show_banner() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║          全栈项目部署配置向导                              ║"
    echo "║          Full-Stack Project Deployment Configurator        ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
}

# 输入函数 (带默认值)
prompt_input() {
    local prompt="$1"
    local default="$2"
    local var_name="$3"

    if [ -n "$default" ]; then
        echo -n "$prompt [$default]: "
    else
        echo -n "$prompt: "
    fi

    read -r response

    if [ -z "$response" ] && [ -n "$default" ]; then
        response="$default"
    fi

    eval "$var_name='$response'"
}

# 输入密码 (不显示)
prompt_password() {
    local prompt="$1"
    local var_name="$2"

    echo -n "$prompt: "
    read -s -r response
    echo ""

    if [ -z "$response" ]; then
        log_error "密码不能为空"
        exit 1
    fi

    eval "$var_name='$response'"
}

# 确认函数
prompt_confirm() {
    local prompt="$1"
    local default="$2"

    local default_str
    if [ "$default" = "Y" ]; then
        default_str="Y/n"
    else
        default_str="y/N"
    fi

    echo -n "$prompt [$default_str]: "
    read -r response

    if [ -z "$response" ]; then
        response="$default"
    fi

    case "$response" in
        [Yy]|[Yy][Ee][Ss]) return 0 ;;
        *) return 1 ;;
    esac
}

# 生成随机字符串
generate_random_string() {
    local length=${1:-32}
    openssl rand -base64 "$length" | tr -d "=+/" | cut -c1-"$length"
}

# 生成 Django SECRET_KEY
generate_django_key() {
    python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())" 2>/dev/null || \
    generate_random_string 50
}

# 配置向导
config_wizard() {
    show_banner

    log_info "本向导将帮助你创建项目部署配置文件"
    log_info "所有输入都可以使用默认值，按 Enter 使用默认选项"
    echo ""

    # ========================================================================
    # 步骤 1: 项目基本信息
    # ========================================================================
    log_step "步骤 1/7: 项目基本信息"
    echo ""

    prompt_input "项目名称" "my-project" PROJECT_NAME
    prompt_input "项目根目录" "/www/wwwroot/$PROJECT_NAME" PROJECT_ROOT
    prompt_input "项目类型" "fullstack" PROJECT_TYPE

    echo ""
    log_info "项目类型说明:"
    echo "  - fullstack: 前后端都部署"
    echo "  - backend:  仅部署后端"
    echo "  - frontend: 仅部署前端"

    until [[ "$PROJECT_TYPE" =~ ^(fullstack|backend|frontend)$ ]]; do
        prompt_input "选择项目类型" "fullstack" PROJECT_TYPE
    done

    echo ""
    echo "---"

    # ========================================================================
    # 步骤 2: 服务器配置
    # ========================================================================
    log_step "步骤 2/7: 服务器配置"
    echo ""

    prompt_input "服务器 IP 地址" "" SERVER_HOST
    prompt_input "SSH 端口" "22" SERVER_PORT
    prompt_input "SSH 用户名" "root" SERVER_USER
    prompt_input "SSH 密钥路径 (留空使用密码登录)" "" SERVER_SSH_KEY_PATH

    if [ -z "$SERVER_SSH_KEY_PATH" ]; then
        prompt_password "服务器密码" SERVER_PASSWORD
        log_warn "建议使用 SSH 密钥而非密码登录"
    fi

    echo ""
    echo "---"

    # ========================================================================
    # 步骤 3: GitHub 仓库配置
    # ========================================================================
    log_step "步骤 3/7: GitHub 仓库配置"
    echo ""

    prompt_input "GitHub 用户名/组织名" "" GITHUB_OWNER
    prompt_input "仓库名称" "" GITHUB_REPO
    prompt_input "部署分支" "main" GITHUB_BRANCH

    echo ""
    prompt_confirm "前后端是否分离?" "N" SEPARATE_FRONTEND

    if [ $? -eq 0 ]; then
        prompt_input "前端仓库名称" "" GITHUB_FRONTEND_REPO
        prompt_input "前端部署分支" "main" GITHUB_FRONTEND_BRANCH
    else
        GITHUB_FRONTEND_REPO=""
        GITHUB_FRONTEND_BRANCH=""
    fi

    echo ""
    echo "---"

    # ========================================================================
    # 步骤 4: 数据库配置
    # ========================================================================
    log_step "步骤 4/7: 数据库配置"
    echo ""

    prompt_input "数据库类型" "mysql" DB_TYPE

    until [[ "$DB_TYPE" =~ ^(mysql|postgresql|sqlite)$ ]]; do
        prompt_input "数据库类型 (mysql/postgresql/sqlite)" "mysql" DB_TYPE
    done

    if [ "$DB_TYPE" != "sqlite" ]; then
        prompt_input "数据库名称" "${PROJECT_NAME}_db" DB_NAME
        prompt_input "数据库用户" "${PROJECT_NAME}_user" DB_USER

        echo ""
        log_info "提示: 数据库密码建议 16 位以上，包含大小写字母、数字和特殊字符"
        prompt_password "数据库密码" DB_PASSWORD

        prompt_input "数据库主机" "localhost" DB_HOST
        prompt_input "数据库端口" "3306" DB_PORT
    else
        DB_NAME="${PROJECT_ROOT}/db.sqlite3"
        DB_USER=""
        DB_PASSWORD=""
        DB_HOST=""
        DB_PORT=""
    fi

    echo ""
    echo "---"

    # ========================================================================
    # 步骤 5: 域名配置 (可选)
    # ========================================================================
    log_step "步骤 5/7: 域名配置 (可选)"
    echo ""

    prompt_confirm "是否使用域名?" "N" HAS_DOMAIN

    if [ $? -eq 0 ]; then
        HAS_DOMAIN="true"
        prompt_input "主域名" "" DOMAIN
        prompt_input "www 子域名" "www.$DOMAIN" WWW_DOMAIN
        prompt_input "API 子域名 (可选)" "api.$DOMAIN" API_DOMAIN

        prompt_confirm "是否启用 SSL (HTTPS)?" "Y" ENABLE_SSL
        if [ $? -eq 0 ]; then
            ENABLE_SSL="true"
            prompt_input "SSL 证书联系邮箱" "admin@$DOMAIN" SSL_EMAIL
        else
            ENABLE_SSL="false"
            SSL_EMAIL=""
        fi
    else
        HAS_DOMAIN="false"
        DOMAIN=""
        WWW_DOMAIN=""
        API_DOMAIN=""
        ENABLE_SSL="false"
        SSL_EMAIL=""
    fi

    echo ""
    echo "---"

    # ========================================================================
    # 步骤 6: 框架配置
    # ========================================================================
    log_step "步骤 6/7: 框架配置"
    echo ""

    if [ "$PROJECT_TYPE" != "frontend" ]; then
        prompt_input "后端框架" "django" BACKEND_FRAMEWORK
        prompt_input "Python 版本" "3.10" BACKEND_PYTHON_VERSION
        prompt_input "虚拟环境名称" "venv" BACKEND_VENV_NAME
        prompt_input "后端端口" "8000" BACKEND_PORT

        # Django 特定配置
        if [ "$BACKEND_FRAMEWORK" = "django" ]; then
            log_info "正在生成 Django SECRET_KEY..."
            DJANGO_SECRET_KEY=$(generate_django_key)
            log_info "Django SECRET_KEY: $DJANGO_SECRET_KEY"

            prompt_input "Django settings 模块" "myproject.settings" DJANGO_SETTINGS_MODULE
        else
            DJANGO_SECRET_KEY=""
            DJANGO_SETTINGS_MODULE=""
        fi
    else
        BACKEND_FRAMEWORK="none"
        BACKEND_PYTHON_VERSION=""
        BACKEND_VENV_NAME=""
        BACKEND_PORT=""
        DJANGO_SECRET_KEY=""
        DJANGO_SETTINGS_MODULE=""
    fi

    if [ "$PROJECT_TYPE" != "backend" ]; then
        prompt_input "前端框架" "vue" FRONTEND_FRAMEWORK
        prompt_input "构建命令" "npm run build" FRONTEND_BUILD_COMMAND
        prompt_input "构建输出目录" "dist" FRONTEND_DIST_DIR
        prompt_input "前端端口" "3000" FRONTEND_PORT
    else
        FRONTEND_FRAMEWORK="none"
        FRONTEND_BUILD_COMMAND=""
        FRONTEND_DIST_DIR=""
        FRONTEND_PORT=""
    fi

    echo ""
    echo "---"

    # ========================================================================
    # 步骤 7: 其他配置
    # ========================================================================
    log_step "步骤 7/7: 其他配置"
    echo ""

    prompt_confirm "是否启用 Redis?" "Y" REDIS_ENABLED
    if [ $? -eq 0 ]; then
        REDIS_ENABLED="true"
        prompt_input "Redis 主机" "localhost" REDIS_HOST
        prompt_input "Redis 端口" "6379" REDIS_PORT
    else
        REDIS_ENABLED="false"
        REDIS_HOST="localhost"
        REDIS_PORT="6379"
    fi

    prompt_input "时区" "Asia/Shanghai" TIMEZONE
    prompt_input "日志级别" "INFO" LOG_LEVEL

    echo ""
    echo "---"

    # ========================================================================
    # 生成配置文件
    # ========================================================================
    log_step "生成配置文件"
    echo ""

    CONFIG_FILE="deploy.config.env"

    if [ -f "$CONFIG_FILE" ]; then
        prompt_confirm "配置文件已存在，是否覆盖?" "N"
        if [ $? -ne 0 ]; then
            log_warn "配置生成已取消"
            exit 0
        fi
    fi

    log_info "正在生成配置文件: $CONFIG_FILE"

    cat > "$CONFIG_FILE" << EOF
# ==============================================================================
# 部署配置文件 (由 init-config.sh 生成)
# ==============================================================================
# 生成时间: $(date)
# ==============================================================================

# 服务器配置
SERVER_HOST="$SERVER_HOST"
SERVER_PORT="$SERVER_PORT"
SERVER_USER="$SERVER_USER"
SERVER_PASSWORD="$SERVER_PASSWORD"
SERVER_SSH_KEY_PATH="$SERVER_SSH_KEY_PATH"

# GitHub 仓库配置
GITHUB_OWNER="$GITHUB_OWNER"
GITHUB_REPO="$GITHUB_REPO"
GITHUB_BRANCH="$GITHUB_BRANCH"
GITHUB_FRONTEND_REPO="$GITHUB_FRONTEND_REPO"
GITHUB_FRONTEND_BRANCH="$GITHUB_FRONTEND_BRANCH"
GITHUB_PAT=""

# 项目配置
PROJECT_NAME="$PROJECT_NAME"
PROJECT_ROOT="$PROJECT_ROOT"
PROJECT_TYPE="$PROJECT_TYPE"

# 域名配置
HAS_DOMAIN="$HAS_DOMAIN"
DOMAIN="$DOMAIN"
WWW_DOMAIN="$WWW_DOMAIN"
API_DOMAIN="$API_DOMAIN"
ENABLE_SSL="$ENABLE_SSL"
SSL_EMAIL="$SSL_EMAIL"

# 数据库配置
DB_TYPE="$DB_TYPE"
DB_NAME="$DB_NAME"
DB_USER="$DB_USER"
DB_PASSWORD="$DB_PASSWORD"
DB_HOST="$DB_HOST"
DB_PORT="$DB_PORT"

# Django 配置
DJANGO_SECRET_KEY="$DJANGO_SECRET_KEY"
DJANGO_SETTINGS_MODULE="$DJANGO_SETTINGS_MODULE"
DJANGO_DEBUG="False"
DJANGO_ALLOWED_HOSTS=""

# 前端配置
FRONTEND_FRAMEWORK="$FRONTEND_FRAMEWORK"
FRONTEND_BUILD_COMMAND="$FRONTEND_BUILD_COMMAND"
FRONTEND_DIST_DIR="$FRONTEND_DIST_DIR"
FRONTEND_PORT="$FRONTEND_PORT"

# 后端配置
BACKEND_FRAMEWORK="$BACKEND_FRAMEWORK"
BACKEND_PYTHON_VERSION="$BACKEND_PYTHON_VERSION"
BACKEND_VENV_NAME="$BACKEND_VENV_NAME"
BACKEND_PORT="$BACKEND_PORT"
BACKEND_WORKERS="3"

# Redis 配置
REDIS_ENABLED="$REDIS_ENABLED"
REDIS_HOST="$REDIS_HOST"
REDIS_PORT="$REDIS_PORT"
REDIS_DB="0"
REDIS_PASSWORD=""

# 邮件配置
EMAIL_ENABLED="false"
EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST="smtp.example.com"
EMAIL_PORT="587"
EMAIL_USE_TLS="true"
EMAIL_HOST_USER=""
EMAIL_HOST_PASSWORD=""
EMAIL_DEFAULT_SENDER=""

# 日志配置
LOG_LEVEL="$LOG_LEVEL"
LOG_RETENTION_DAYS="30"

# 备份配置
BACKUP_ENABLED="true"
BACKUP_SCHEDULE_DB="0 2 * * *"
BACKUP_SCHEDULE_FILES="0 3 * * 0"
BACKUP_RETENTION_DAYS="7"

# 部署选项
AUTO_MIGRATE="true"
AUTO_COLLECTSTATIC="true"
AUTO_RESTART_SERVICES="true"
RUN_BUILD_BEFORE_DEPLOY="true"

# 开发模式配置
DEV_MODE="false"
DEV_HOT_RELOAD="true"
DEV_SHOW_SQL="false"

# 安全配置
ENABLE_FIREWALL="true"
ALLOWED_IPS=""
RATE_LIMIT_ENABLED="false"
RATE_LIMIT_REQUESTS="100"

# 监控配置
MONITORING_ENABLED="false"
SLACK_WEBHOOK_URL=""
ENABLE_ERROR_NOTIFICATIONS="false"

# 自定义命令
PRE_DEPLOY_COMMAND=""
POST_DEPLOY_COMMAND=""
PRE_BUILD_COMMAND=""
POST_BUILD_COMMAND=""

# 其他配置
TIMEZONE="$TIMEZONE"
LOCALE="zh_CN.UTF-8"

# ==============================================================================
# 配置文件结束
# ==============================================================================
EOF

    log_info "配置文件已生成: $CONFIG_FILE"

    # ========================================================================
    # 显示配置摘要
    # ========================================================================
    echo ""
    log_step "配置摘要"
    echo ""

    echo "项目信息:"
    echo "  - 项目名称: $PROJECT_NAME"
    echo "  - 项目类型: $PROJECT_TYPE"
    echo "  - 项目根目录: $PROJECT_ROOT"
    echo ""

    echo "服务器信息:"
    echo "  - 服务器: $SERVER_USER@$SERVER_HOST:$SERVER_PORT"
    echo "  - SSH 密钥: ${SERVER_SSH_KEY_PATH:-未配置 (使用密码)}"
    echo ""

    echo "GitHub 仓库:"
    echo "  - 仓库: $GITHUB_OWNER/$GITHUB_REPO ($GITHUB_BRANCH)"
    if [ -n "$GITHUB_FRONTEND_REPO" ]; then
        echo "  - 前端: $GITHUB_OWNER/$GITHUB_FRONTEND_REPO ($GITHUB_FRONTEND_BRANCH)"
    fi
    echo ""

    echo "数据库:"
    echo "  - 类型: $DB_TYPE"
    if [ "$DB_TYPE" != "sqlite" ]; then
        echo "  - 数据库: $DB_USER@$DB_HOST:$DB_PORT/$DB_NAME"
    fi
    echo ""

    if [ "$HAS_DOMAIN" = "true" ]; then
        echo "域名:"
        echo "  - 主域名: $DOMAIN"
        echo "  - SSL: $ENABLE_SSL"
        echo ""
    fi

    # ========================================================================
    # 下一步操作提示
    # ========================================================================
    echo "---"
    echo ""
    log_info "配置文件已成功生成！"
    echo ""
    echo "📝 下一步操作:"
    echo ""
    echo "1. 检查配置文件:"
    echo "   cat $CONFIG_FILE"
    echo ""
    echo "2. 编辑配置文件 (如需修改):"
    echo "   vim $CONFIG_FILE"
    echo ""
    echo "3. 使用配置文件部署:"
    echo "   bash scripts/deploy.sh --config $CONFIG_FILE"
    echo ""
    echo "4. 或配置 GitHub Actions:"
    echo "   - 将配置添加到 GitHub Secrets"
    echo "   - 复制 templates/github-action.yml 到 .github/workflows/deploy.yml"
    echo "   - 推送代码到 GitHub 触发自动部署"
    echo ""
    log_warn "⚠️  请确保:"
    echo "  - 服务器 SSH 连接正常"
    echo "  - GitHub Secrets 已正确配置"
    echo "  - 域名已解析到服务器 IP (如使用域名)"
    echo ""
}

# 主函数
main() {
    config_wizard
}

# 运行
main "$@"
