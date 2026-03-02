#!/bin/bash
# ==============================================================================
# 全栈项目一键部署脚本
# ==============================================================================
# 使用方法: bash deploy.sh [选项] [参数]
#
# 选项:
#   --config FILE    使用指定的配置文件
#   --interactive    交互式配置
#   --full           完整部署
#   --backend        仅部署后端
#   --frontend       仅部署前端
#   --update         更新部署
#   --status         查看状态
#   --logs           查看日志
#   --backup         备份数据
#   --help           显示帮助
#
# 示例:
#   bash deploy.sh --config deploy.config.env --full
#   bash deploy.sh --config deploy.config.env --update
#   bash deploy.sh --config deploy.config.env --backend
# ==============================================================================

set -e

# ==============================================================================
# 颜色输出
# ==============================================================================
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

# ==============================================================================
# 配置变量 (默认值，会被配置文件覆盖)
# ==============================================================================
PROJECT_NAME="my-project"
PROJECT_ROOT="/www/wwwroot/my-project"
PROJECT_TYPE="fullstack"

# 服务器配置
SERVER_HOST=""
SERVER_PORT="22"
SERVER_USER="root"
SERVER_PASSWORD=""
SERVER_SSH_KEY_PATH=""

# GitHub 配置
GITHUB_OWNER=""
GITHUB_REPO=""
GITHUB_BRANCH="main"
GITHUB_FRONTEND_REPO=""
GITHUB_FRONTEND_BRANCH="main"

# 域名配置
HAS_DOMAIN="false"
DOMAIN=""
WWW_DOMAIN=""
API_DOMAIN=""
ENABLE_SSL="false"
SSL_EMAIL=""

# 数据库配置
DB_TYPE="mysql"
DB_NAME="my_database"
DB_USER="db_user"
DB_PASSWORD=""
DB_HOST="localhost"
DB_PORT="3306"

# Django 配置
DJANGO_SECRET_KEY=""
DJANGO_SETTINGS_MODULE="myproject.settings"
DJANGO_DEBUG="False"
DJANGO_ALLOWED_HOSTS=""

# 前端配置
FRONTEND_FRAMEWORK="vue"
FRONTEND_BUILD_COMMAND="npm run build"
FRONTEND_DIST_DIR="dist"
FRONTEND_PORT="3000"

# 后端配置
BACKEND_FRAMEWORK="django"
BACKEND_PYTHON_VERSION="3.10"
BACKEND_VENV_NAME="venv"
BACKEND_PORT="8000"
BACKEND_WORKERS="3"

# Redis 配置
REDIS_ENABLED="true"
REDIS_HOST="localhost"
REDIS_PORT="6379"

# 部署选项
AUTO_MIGRATE="true"
AUTO_COLLECTSTATIC="true"
AUTO_RESTART_SERVICES="true"

# ==============================================================================
# 加载配置文件
# ==============================================================================
load_config() {
    local config_file="$1"

    if [ ! -f "$config_file" ]; then
        log_error "配置文件不存在: $config_file"
        exit 1
    fi

    log_info "加载配置文件: $config_file"

    # 读取配置文件 (忽略注释和空行)
    while IFS='=' read -r key value; do
        # 跳过注释和空行
        [[ $key =~ ^#.*$ ]] && continue
        [[ -z $key ]] && continue

        # 移除引号和空格
        value=$(echo "$value" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sed 's/^"//;s/"$//' | sed "s/^'//;s/'$//")

        # 导出变量
        export "$key=$value"
    done < "$config_file"

    log_info "配置加载完成"
}

# ==============================================================================
# 检查配置
# ==============================================================================
check_config() {
    log_step "检查配置..."

    if [ -z "$PROJECT_ROOT" ]; then
        log_error "PROJECT_ROOT 未设置"
        exit 1
    fi

    if [ -z "$DB_NAME" ]; then
        log_error "DB_NAME 未设置"
        exit 1
    fi

    if [ -z "$DB_PASSWORD" ]; then
        log_error "DB_PASSWORD 未设置"
        exit 1
    fi

    log_info "配置检查通过"
}

# ==============================================================================
# 初始化部署
# ==============================================================================
init_deploy() {
    log_step "开始初始化部署..."

    check_root

    # 更新系统
    log_info "更新系统包..."
    apt update && apt upgrade -y

    # 安装系统依赖
    log_info "安装系统依赖..."
    apt install -y \
        python${BACKEND_PYTHON_VERSION} \
        python${BACKEND_PYTHON_VERSION}-venv \
        python3-pip \
        mysql-server \
        redis-server \
        nginx \
        git \
        supervisor \
        certbot \
        python3-certbot-nginx \
        nodejs \
        npm

    # 启动服务
    log_info "启动系统服务..."
    systemctl enable mysql
    systemctl start mysql
    systemctl enable redis-server
    systemctl start redis-server
    systemctl enable nginx
    systemctl start nginx
    systemctl enable supervisor
    systemctl start supervisor

    # 创建项目目录
    log_info "创建项目目录..."
    mkdir -p "$PROJECT_ROOT"/{backend,frontend,logs,backups}

    # 配置 MySQL
    log_info "配置 MySQL..."
    mysql -e "CREATE DATABASE IF NOT EXISTS ${DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    mysql -e "CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';"
    mysql -e "GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'localhost';"
    mysql -e "FLUSH PRIVILEGES;"

    log_info "初始化完成！"
}

# ==============================================================================
# 部署后端
# ==============================================================================
deploy_backend() {
    log_step "开始部署后端..."

    local backend_dir="$PROJECT_ROOT/backend"

    if [ ! -d "$backend_dir" ]; then
        log_error "后端目录不存在: $backend_dir"
        exit 1
    fi

    # 查找 Django 项目目录
    local django_project_dir=$(find "$backend_dir" -name "manage.py" -printf "%h\n" | head -1)

    if [ -z "$django_project_dir" ]; then
        log_error "未找到 Django 项目 (manage.py)"
        exit 1
    fi

    log_info "Django 项目目录: $django_project_dir"

    cd "$django_project_dir"

    # 创建虚拟环境
    if [ ! -d "$BACKEND_VENV_NAME" ]; then
        log_info "创建 Python 虚拟环境..."
        python${BACKEND_PYTHON_VERSION} -m venv "$BACKEND_VENV_NAME"
    fi

    # 激活虚拟环境并安装依赖
    log_info "安装 Python 依赖..."
    source "$BACKEND_VENV_NAME/bin/activate"
    pip install --upgrade pip
    pip install -r requirements.txt

    # 创建 .env 文件
    log_info "配置环境变量..."
    cat > .env << EOF
SECRET_KEY=${DJANGO_SECRET_KEY}
DEBUG=${DJANGO_DEBUG}
ALLOWED_HOSTS=${DJANGO_ALLOWED_HOSTS:-$DOMAIN,$WWW_DOMAIN}
DB_ENGINE=django.db.backends.mysql
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASSWORD}
DB_HOST=${DB_HOST}
DB_PORT=${DB_PORT}
REDIS_HOST=${REDIS_HOST}
REDIS_PORT=${REDIS_PORT}
EOF

    # 数据库迁移
    if [ "$AUTO_MIGRATE" = "true" ]; then
        log_info "执行数据库迁移..."
        python manage.py makemigrations
        python manage.py migrate
    fi

    # 收集静态文件
    if [ "$AUTO_COLLECTSTATIC" = "true" ]; then
        log_info "收集静态文件..."
        python manage.py collectstatic --noinput
    fi

    # 配置 Supervisor
    log_info "配置 Supervisor..."
    cat > /etc/supervisor/conf.d/${PROJECT_NAME}-django.conf << EOF
[program:${PROJECT_NAME}-django]
directory=$django_project_dir
command=$django_project_dir/${BACKEND_VENV_NAME}/bin/gunicorn --workers ${BACKEND_WORKERS} --bind unix:/tmp/${PROJECT_NAME}-django.sock wsgi:application
autostart=true
autorestart=true
stderr_logfile=${PROJECT_ROOT}/logs/django-error.log
stdout_logfile=${PROJECT_ROOT}/logs/django-access.log
user=www-data
environment=DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE}"
EOF

    supervisorctl reread
    supervisorctl update

    if [ "$AUTO_RESTART_SERVICES" = "true" ]; then
        log_info "重启 Django 服务..."
        supervisorctl restart ${PROJECT_NAME}-django
    fi

    log_info "后端部署完成！"
}

# ==============================================================================
# 部署前端
# ==============================================================================
deploy_frontend() {
    log_step "开始部署前端..."

    local frontend_dir="$PROJECT_ROOT/frontend"

    if [ ! -d "$frontend_dir" ]; then
        log_error "前端目录不存在: $frontend_dir"
        exit 1
    fi

    # 查找前端项目目录 (package.json)
    local frontend_project_dir=$(find "$frontend_dir" -name "package.json" -printf "%h\n" | head -1)

    if [ -z "$frontend_project_dir" ]; then
        log_error "未找到前端项目 (package.json)"
        exit 1
    fi

    log_info "前端项目目录: $frontend_project_dir"

    cd "$frontend_project_dir"

    # 安装依赖
    log_info "安装 Node.js 依赖..."
    npm install

    # 构建生产版本
    log_info "构建前端..."
    eval "$FRONTEND_BUILD_COMMAND"

    log_info "前端部署完成！"
}

# ==============================================================================
# 更新部署
# ==============================================================================
update_deploy() {
    log_step "开始更新部署..."

    # 更新后端
    log_info "更新后端..."
    cd "$PROJECT_ROOT/backend"
    git pull
    deploy_backend

    # 更新前端
    log_info "更新前端..."
    cd "$PROJECT_ROOT/frontend"
    git pull
    deploy_frontend

    # 重启 Nginx
    log_info "重启 Nginx..."
    nginx -s reload

    log_info "更新完成！"
}

# ==============================================================================
# 查看状态
# ==============================================================================
check_status() {
    log_step "检查服务状态..."

    echo "=== Supervisor 服务 ==="
    supervisorctl status ${PROJECT_NAME}:*

    echo ""
    echo "=== 系统服务 ==="
    systemctl status mysql --no-pager -l
    systemctl status redis-server --no-pager -l
    systemctl status nginx --no-pager -l
}

# ==============================================================================
# 查看日志
# ==============================================================================
view_logs() {
    echo "选择要查看的日志:"
    echo "1) Django 错误日志"
    echo "2) Django 访问日志"
    echo "3) Nginx 错误日志"
    echo "4) Nginx 访问日志"
    read -p "请选择 (1-4): " choice

    case $choice in
        1) tail -f ${PROJECT_ROOT}/logs/django-error.log ;;
        2) tail -f ${PROJECT_ROOT}/logs/django-access.log ;;
        3) tail -f /var/log/nginx/error.log ;;
        4) tail -f /var/log/nginx/access.log ;;
        *) log_error "无效选择" ;;
    esac
}

# ==============================================================================
# 备份数据
# ==============================================================================
backup_data() {
    log_step "开始备份数据..."

    local backup_date=$(date +%Y%m%d_%H%M%S)
    local backup_dir="${PROJECT_ROOT}/backups"

    mkdir -p "$backup_dir/db"
    mkdir -p "$backup_dir/files"

    # 备份数据库
    log_info "备份数据库..."
    mysqldump -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" > "$backup_dir/db/db_$backup_date.sql"

    # 备份文件
    log_info "备份项目文件..."
    tar -czf "$backup_dir/files/files_$backup_date.tar.gz" "$PROJECT_ROOT" --exclude="$PROJECT_ROOT/backend/${BACKEND_VENV_NAME}" --exclude="$PROJECT_ROOT/frontend/node_modules"

    log_info "备份完成！文件位于: $backup_dir/"
}

# ==============================================================================
# 检查 root 权限
# ==============================================================================
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "请使用 sudo 运行此脚本"
        exit 1
    fi
}

# ==============================================================================
# 显示帮助
# ==============================================================================
show_help() {
    cat << EOF
全栈项目一键部署脚本

用法: bash deploy.sh [选项] [命令]

选项:
  --config FILE      使用指定的配置文件

命令:
  --interactive      交互式配置
  --init             初始化部署环境
  --full             完整部署
  --backend          仅部署后端
  --frontend         仅部署前端
  --update           更新所有组件
  --status           检查服务状态
  --logs             查看日志
  --backup           备份数据
  --help             显示帮助

示例:
  bash deploy.sh --config deploy.config.env --init
  bash deploy.sh --config deploy.config.env --full
  bash deploy.sh --config deploy.config.env --update
  bash deploy.sh --config deploy.config.env --backend

配置文件:
  复制 templates/deploy.config.env 并填写配置

文档:
  SKILL.md                 - 完整部署指南
  DEPLOYMENT_CHECKLIST.md  - 部署前准备清单

EOF
}

# ==============================================================================
# 主函数
# ==============================================================================
main() {
    local config_file=""
    local command=""

    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --config)
                config_file="$2"
                shift 2
                ;;
            --interactive|--init|--full|--backend|--frontend|--update|--status|--logs|--backup|--help)
            ;;
        --check-ports)
            check_ports
            ;;
        --generate-docs)
            generate_docs
            ;;
                command="$1"
                shift
                ;;
            *)
                log_error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # 如果指定了配置文件，加载它
    if [ -n "$config_file" ]; then
        load_config "$config_file"
    fi

    # 检查配置
    check_config

    # 执行命令
    case "$command" in
        --interactive)
            log_info "启动交互式配置向导..."
            bash "$(dirname "$0")/init-config.sh"
            ;;
        --init)
            init_deploy
            ;;
        --full)
            init_deploy
            deploy_backend
            deploy_frontend

    # 检查端口
    log_info "检查端口和防火墙..."
    check_ports

    # 生成部署文档
    log_info "生成部署文档..."
    generate_docs
            ;;
        --backend)
            deploy_backend
            ;;
        --frontend)
            deploy_frontend
            ;;
        --update)
            update_deploy
            ;;
        --status)
            check_status
            ;;
        --logs)
            view_logs
            ;;
        --backup)
            backup_data
            ;;
        --help|"")
            show_help
            ;;
        *)
            log_error "未知命令: $command"
            show_help
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"

# ==============================================================================
# 检查端口
# ==============================================================================
check_ports() {
    local script_dir="$(dirname "$0")"
    if [ -f "$script_dir/check-ports.sh" ]; then
        bash "$script_dir/check-ports.sh" --config "${config_file:-}"
    else
        log_warn "端口检查脚本不存在"
    fi
}

# ==============================================================================
# 生成文档
# ==============================================================================
generate_docs() {
    local script_dir="$(dirname "$0")"
    if [ -f "$script_dir/generate-docs.sh" ]; then
        bash "$script_dir/generate-docs.sh" --config "${config_file:-}"
    else
        log_warn "文档生成脚本不存在"
    fi
}
