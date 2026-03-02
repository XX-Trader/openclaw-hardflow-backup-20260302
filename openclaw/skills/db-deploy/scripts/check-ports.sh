#!/bin/bash
# ==============================================================================
# 端口和防火墙检查脚本
# ==============================================================================
# 使用: bash scripts/check-ports.sh [--config FILE]
# 功能: 检查服务器端口、防火墙状态，并提供修复建议
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
DOMAIN=""

# 加载配置
load_config() {
    local config_file="$1"

    if [ -f "$config_file" ]; then
        source "$config_file"
    fi
}

# 检查端口监听状态
check_listening_ports() {
    log_step "检查端口监听状态..."

    local ports=("22" "80" "443" "3306" "6379")
    local port_names=("SSH" "HTTP" "HTTPS" "MySQL" "Redis")
    local required=("22" "80" "443")

    echo ""
    printf "%-10s %-15s %-10s %-10s\n" "端口" "服务" "状态" "必需"
    printf "%-10s %-15s %-10s %-10s\n" "----" "----" "----" "----"

    for i in "${!ports[@]}"; do
        local port=${ports[$i]}
        local name=${port_names[$i]}
        local is_required=""
        local status=""

        if [[ " ${required[@]} " =~ " ${port} " ]]; then
            is_required="${GREEN}✅${NC}"
        else
            is_required="  "
        fi

        if netstat -tuln 2>/dev/null | grep -q ":$port "; then
            status="${GREEN}监听中${NC}"
        elif ss -tuln 2>/dev/null | grep -q ":$port "; then
            status="${GREEN}监听中${NC}"
        else
            status="${RED}未监听${NC}"
        fi

        printf "%-10s %-15s %-20s %-10s\n" "$port" "$name" "$status" "$is_required"
    done

    echo ""
}

# 检查防火墙状态
check_firewall() {
    log_step "检查防火墙状态..."

    # 检查 UFW
    if command -v ufw &> /dev/null; then
        echo ""
        log_info "UFW 防火墙状态:"
        ufw status verbose || true
    fi

    # 检查 iptables
    if command -v iptables &> /dev/null; then
        echo ""
        log_info "iptables 规则:"
        iptables -L -n | grep -E "Chain|ACCEPT.*dpt:(22|80|443)" | head -20 || true
    fi

    # 检查 firewalld
    if command -v firewall-cmd &> /dev/null; then
        echo ""
        log_info "firewalld 状态:"
        firewall-cmd --list-all 2>/dev/null || true
    fi
}

# 测试外部端口连通性
test_external_connectivity() {
    log_step "测试外部端口连通性..."

    local server_ip=$(curl -s ifconfig.me 2>/dev/null || curl -s icanhazip.com 2>/dev/null)
    local ports=("80" "443")

    echo ""
    log_info "服务器公网 IP: $server_ip"
    echo ""

    for port in "${ports[@]}"; do
        log_info "测试端口 $port..."

        # 从外部测试（使用 curl）
        if curl -s --connect-timeout 5 "http://${server_ip}:${port}" > /dev/null 2>&1; then
            echo -e "  端口 $port: ${GREEN}✅ 可从外部访问${NC}"
        else
            echo -e "  端口 $port: ${RED}❌ 无法从外部访问${NC}"
            log_warn "  可能原因: 云服务器安全组未开放此端口"
        fi
    done

    echo ""
}

# 生成修复建议
generate_fix_suggestions() {
    log_step "生成修复建议..."

    cat << 'EOF'

================================================================================
                        防火墙配置建议
================================================================================

1. 服务器内部防火墙 (UFW)
-----------------------------------------------------------------------------------------------------------
如果 UFW 未启用或端口未开放，运行以下命令:

    sudo ufw allow 22/tcp    # SSH
    sudo ufw allow 80/tcp    # HTTP
    sudo ufw allow 443/tcp   # HTTPS
    sudo ufw enable

查看状态: sudo ufw status verbose

2. 云服务器安全组 (重要!)
-----------------------------------------------------------------------------------------------------------
如果外部无法访问 80/443 端口，需要在云服务商控制台添加安全组规则:

┌─────────────┬─────────────────────────────────────────────────────────────┐
│ 云服务商     │ 控制台位置                                                  │
├─────────────┼─────────────────────────────────────────────────────────────┤
│ 阿里云       │ ECS 实例 → 安全组 → 配置规则 → 添加安全组规则               │
│ 腾讯云       │ CVM 实例 → 安全组 → 修改规则                               │
│ AWS         │ EC2 → Security Groups → Inbound Rules → Edit              │
│ 华为云       │ ECS → 安全组 → 配置规则                                     │
│ Google Cloud │ VPC Network → Firewall Rules                              │
│ Azure        │ Network Security Group → Settings                         │
└─────────────┴─────────────────────────────────────────────────────────────┘

需要添加的入站规则:

┌──────────┬──────────┬──────────────┬────────────────────────────────┐
│ 协议      │ 端口范围  │ 源地址        │ 说明                           │
├──────────┼──────────┼──────────────┼────────────────────────────────┤
│ TCP       │ 22       │ 0.0.0.0/0    │ SSH (生产环境建议限制 IP)        │
│ TCP       │ 80       │ 0.0.0.0/0    │ HTTP                           │
│ TCP       │ 443      │ 0.0.0.0/0    │ HTTPS                          │
└──────────┴──────────┴──────────────┴────────────────────────────────┘

3. 验证端口开放
-----------------------------------------------------------------------------------------------------------
从本地电脑测试:

    # 测试 HTTP
    curl -I http://YOUR_SERVER_IP

    # 测试 HTTPS
    curl -I https://YOUR_DOMAIN

    # 测试 SSH
    ssh -v user@YOUR_SERVER_IP

4. Nginx 配置检查
-----------------------------------------------------------------------------------------------------------
如果 80/443 端口已监听但无法访问，检查 Nginx:

    sudo nginx -t                    # 测试配置
    sudo systemctl status nginx       # 查看状态
    sudo tail -f /var/log/nginx/error.log  # 查看日志

5. DNS 解析检查 (如果使用域名)
-----------------------------------------------------------------------------------------------------------
    # 检查域名解析
    ping YOUR_DOMAIN

    # 查看详细 DNS 信息
    nslookup YOUR_DOMAIN

    # 检查是否指向正确 IP
    dig YOUR_DOMAIN +short

================================================================================
EOF
}

# 生成开放端口命令
generate_open_commands() {
    log_step "生成开放端口命令..."

    echo ""
    log_info "根据你的系统选择命令:"
    echo ""

    # 检测防火墙类型
    if command -v ufw &> /dev/null; then
        echo "=== 使用 UFW (Ubuntu/Debian) ==="
        echo ""
        echo "sudo ufw allow 22/tcp"
        echo "sudo ufw allow 80/tcp"
        echo "sudo ufw allow 443/tcp"
        echo "sudo ufw enable"
        echo ""
    fi

    if command -v firewall-cmd &> /dev/null; then
        echo "=== 使用 firewalld (CentOS/RHEL) ==="
        echo ""
        echo "sudo firewall-cmd --permanent --add-service=http"
        echo "sudo firewall-cmd --permanent --add-service=https"
        echo "sudo firewall-cmd --permanent --add-port=22/tcp"
        echo "sudo firewall-cmd --reload"
        echo ""
    fi

    if command -v iptables &> /dev/null; then
        echo "=== 使用 iptables ==="
        echo ""
        echo "sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT"
        echo "sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT"
        echo "sudo iptables -A INPUT -p tcp --dport 443 -j ACCEPT"
        echo "sudo iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT"
        echo ""
    fi
}

# 主函数
main() {
    local config_file=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --config)
                config_file="$2"
                shift 2
                ;;
            *)
                if [ -f "$1" ]; then
                    config_file="$1"
                fi
                shift
                ;;
        esac
    done

    if [ -n "$config_file" ]; then
        load_config "$config_file"
    fi

    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║          端口和防火墙检查脚本                                  ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""

    check_listening_ports
    check_firewall
    test_external_connectivity
    generate_fix_suggestions
    generate_open_commands

    log_step "检查完成！"
    echo ""
    log_warn "如果外部无法访问 80/443 端口，请检查云服务器安全组设置！"
}

main "$@"
