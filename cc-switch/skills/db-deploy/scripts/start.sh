#!/bin/bash
# ==============================================================================
# 一键启动脚本 - 启动所有项目服务
# ==============================================================================
# 使用: bash scripts/start.sh [--config FILE]
# 功能: 启动 Nginx、MySQL、Redis、Django 等所有服务
# ==============================================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

# 默认配置
PROJECT_NAME="my-project"
PROJECT_ROOT="/www/wwwroot/my-project"

# 加载配置文件
load_config() {
    local config_file="$1"

    if [ -f "$config_file" ]; then
        log_info "加载配置: $config_file"
        source "$config_file"
    fi
}

# 检查 root 权限
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "需要 root 权限，请使用 sudo"
        exit 1
    fi
}

# 启动系统服务
start_system_services() {
    log_step "启动系统服务..."

    # MySQL
    log_info "启动 MySQL..."
    systemctl start mysql 2>/dev/null || systemctl start mysqld 2>/dev/null || service mysql start

    # Redis
    log_info "启动 Redis..."
    systemctl start redis-server 2>/dev/null || service redis-server start

    # Nginx
    log_info "启动 Nginx..."
    systemctl start nginx

    # Supervisor
    log_info "启动 Supervisor..."
    systemctl start supervisor

    log_info "✅ 系统服务启动完成"
}

# 启动项目服务
start_project_services() {
    log_step "启动项目服务..."

    # Django
    if [ -f "/etc/supervisor/conf.d/${PROJECT_NAME}-django.conf" ]; then
        log_info "启动 Django..."
        supervisorctl start ${PROJECT_NAME}:django 2>/dev/null || true
        supervisorctl start ${PROJECT_NAME}-django 2>/dev/null || true
    else
        log_warn "Django 服务配置不存在"
    fi

    log_info "✅ 项目服务启动完成"
}

# 检查服务状态
check_services() {
    log_step "检查服务状态..."

    echo ""
    echo "=== 系统服务 ==="
    systemctl status mysql --no-pager -l | grep -E "Active|Loaded" || true
    systemctl status redis-server --no-pager -l | grep -E "Active|Loaded" || true
    systemctl status nginx --no-pager -l | grep -E "Active|Loaded" || true
    systemctl status supervisor --no-pager -l | grep -E "Active|Loaded" || true

    echo ""
    echo "=== 项目服务 ==="
    supervisorctl status ${PROJECT_NAME}:* 2>/dev/null || log_warn "没有找到项目服务"
}

# 测试端口连接
test_ports() {
    log_step "测试端口连接..."

    local ports=("80" "443" "3306" "6379")
    local port_names=("HTTP" "HTTPS" "MySQL" "Redis")

    for i in "${!ports[@]}"; do
        local port=${ports[$i]}
        local name=${port_names[$i]}

        if netstat -tuln 2>/dev/null | grep -q ":$port "; then
            log_info "$name (端口 $port): ✅ 开放"
        else
            log_warn "$name (端口 $port): ❌ 未监听"
        fi
    done
}

# 显示访问信息
show_access_info() {
    log_step "访问信息..."

    echo ""
    if [ -n "$DOMAIN" ]; then
        log_info "网站地址: https://$DOMAIN"
        log_info "www 地址: https://$WWW_DOMAIN"
    else
        log_info "网站地址: http://YOUR_SERVER_IP"
        log_warn "请配置 DNS 或使用 IP 访问"
    fi

    echo ""
    log_info "管理命令:"
    echo "  查看日志: tail -f ${PROJECT_ROOT}/logs/*.log"
    echo "  重启服务: supervisorctl restart ${PROJECT_NAME}:django"
    echo "  检查状态: supervisorctl status ${PROJECT_NAME}:*"
}

# 主函数
main() {
    local config_file=""

    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --config)
                config_file="$2"
                shift 2
                ;;
            *)
                # 如果是文件路径
                if [ -f "$1" ]; then
                    config_file="$1"
                fi
                shift
                ;;
        esac
    done

    # 加载配置
    if [ -n "$config_file" ]; then
        load_config "$config_file"
    fi

    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║          一键启动脚本 - 启动所有服务                        ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""

    check_root
    start_system_services
    start_project_services
    check_services
    test_ports
    show_access_info

    echo ""
    log_info "🎉 所有服务启动完成！"
}

main "$@"
