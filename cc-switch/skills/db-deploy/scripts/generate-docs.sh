#!/bin/bash
# ==============================================================================
# 部署文档生成脚本
# ==============================================================================
# 使用: bash scripts/generate-docs.sh [--config FILE]
# 功能: 自动生成部署后的项目文档
# ==============================================================================

set -e

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_step() {
    echo -e "${BLUE}==>${NC} $1"
}

# 默认配置
PROJECT_NAME="my-project"
PROJECT_ROOT="/www/wwwroot/my-project"
DOMAIN=""
WWW_DOMAIN=""
API_DOMAIN=""
DB_NAME=""
DB_USER=""
BACKEND_FRAMEWORK="django"
FRONTEND_FRAMEWORK="vue"
GITHUB_REPO=""

# 加载配置
load_config() {
    local config_file="$1"

    if [ -f "$config_file" ]; then
        log_info "加载配置: $config_file"
        source "$config_file"
    fi
}

# 生成文档
generate_docs() {
    local doc_file="${PROJECT_ROOT}/DEPLOYMENT_INFO.md"
    local date=$(date +"%Y-%m-%d %H:%M:%S")

    log_step "生成部署文档..."

    cat > "$doc_file" << EOF
# ${PROJECT_NAME} 部署文档

**生成时间**: ${date}
**项目名称**: ${PROJECT_NAME}
**项目类型**: ${PROJECT_TYPE:-fullstack}

---

## 📍 项目位置

| 项目 | 路径 |
|------|------|
| **项目根目录** | \`${PROJECT_ROOT}\` |
| **后端代码** | \`${PROJECT_ROOT}/backend\` |
| **前端代码** | \`${PROJECT_ROOT}/frontend\` |
| **日志目录** | \`${PROJECT_ROOT}/logs\` |
| **备份目录** | \`${PROJECT_ROOT}/backups\` |

---

## 🌐 访问地址

EOF

    if [ -n "$DOMAIN" ]; then
        cat >> "$doc_file" << EOF
| 服务 | 地址 | 说明 |
|------|------|------|
| **主站** | https://${DOMAIN} | 主域名 |
| **www** | https://${WWW_DOMAIN} | www 子域名 |
EOF

        if [ -n "$API_DOMAIN" ]; then
            echo "| **API** | https://${API_DOMAIN} | API 接口 |" >> "$doc_file"
        fi
    else
        cat >> "$doc_file" << EOF
| 服务 | 地址 | 说明 |
|------|------|------|
| **主站** | http://YOUR_SERVER_IP | 请使用服务器 IP 访问 |

**注意**: 未配置域名，请配置 DNS 或使用 IP 访问。
EOF
    fi

    cat >> "$doc_file" << EOF

---

## 🔧 服务配置

### 系统服务

| 服务 | 状态命令 | 日志位置 |
|------|----------|----------|
| **Nginx** | \`systemctl status nginx\` | /var/log/nginx/ |
| **MySQL** | \`systemctl status mysql\` | /var/log/mysql/ |
| **Redis** | \`systemctl status redis-server\` | /var/log/redis/ |
| **Supervisor** | \`systemctl status supervisor\` | /var/log/supervisor/ |

### 项目服务

| 服务 | 启动命令 | 停止命令 | 重启命令 |
|------|----------|----------|----------|
| **Django** | \`supervisorctl start ${PROJECT_NAME}:django\` | \`supervisorctl stop ${PROJECT_NAME}:django\` | \`supervisorctl restart ${PROJECT_NAME}:django\` |

**查看所有服务状态**:
\`\`\`bash
sudo supervisorctl status ${PROJECT_NAME}:*
\`\`\`

---

## 📊 技术栈

### 后端

| 项目 | 版本/说明 |
|------|-----------|
| **框架** | ${BACKEND_FRAMEWORK} |
| **Python** | ${BACKEND_PYTHON_VERSION:-3.10} |
| **虚拟环境** | ${BACKEND_VENV_NAME:-venv} |
| **数据库** | MySQL ${DB_TYPE} |
| **缓存** | Redis ${REDIS_VERSION:-latest} |

### 前端

| 项目 | 版本/说明 |
|------|-----------|
| **框架** | ${FRONTEND_FRAMEWORK} |
| **构建命令** | \`${FRONTEND_BUILD_COMMAND:-npm run build}\` |
| **输出目录** | \`${FRONTEND_DIST_DIR:-dist}\` |

---

## 🗄️ 数据库信息

| 配置项 | 值 |
|--------|-----|
| **数据库名** | \`${DB_NAME}\` |
| **数据库用户** | \`${DB_USER}\` |
| **数据库主机** | \`${DB_HOST:-localhost}\` |
| **数据库端口** | \`${DB_PORT:-3306}\` |

**连接命令**:
\`\`\`bash
mysql -u ${DB_USER} -p ${DB_NAME}
\`\`\`

---

## 🔑 SSH 访问

\`\`\`bash
# 使用 IP 登录
ssh ${SERVER_USER:-root}@YOUR_SERVER_IP

# 使用 SSH 密钥（推荐）
ssh -i ~/.ssh/id_ed255 ${SERVER_USER:-root}@YOUR_SERVER_IP
\`\`\`

---

## 📝 脚本使用说明

### 一键启动所有服务

\`\`\`bash
bash ${PROJECT_ROOT}/../db-deploy/scripts/start.sh
\`\`\`

### 一键停止所有服务

\`\`\`bash
sudo supervisorctl stop ${PROJECT_NAME}:*
sudo systemctl stop nginx
\`\`\`

### 查看服务状态

\`\`\`bash
# 查看项目服务
sudo supervisorctl status ${PROJECT_NAME}:*

# 查看系统服务
sudo systemctl status nginx mysql redis-server supervisor
\`\`\`

### 查看日志

\`\`\`bash
# Django 日志
tail -f ${PROJECT_ROOT}/logs/django-error.log
tail -f ${PROJECT_ROOT}/logs/django-access.log

# Nginx 日志
tail -f /var/log/nginx/error.log
tail -f /var/log/nginx/access.log

# Supervisor 日志
sudo supervisorctl tail ${PROJECT_NAME}:django
\`\`\`

### 更新代码

\`\`\`bash
# 方式 1: 使用 GitHub Actions (推荐)
git push origin main  # 自动部署

# 方式 2: 手动更新
cd ${PROJECT_ROOT}/backend && git pull
cd ${PROJECT_ROOT}/frontend && git pull
sudo supervisorctl restart ${PROJECT_NAME}:django
sudo nginx -s reload
\`\`\`

### 备份数据

\`\`\`bash
# 备份数据库
mysqldump -u ${DB_USER} -p ${DB_NAME} > backup_\$(date +%Y%m%d).sql

# 备份文件
tar -czf files_backup_\$(date +%Y%m%d).tar.gz ${PROJECT_ROOT}
\`\`\`

---

## 🔥 防火墙和端口

### 必需端口

| 端口 | 协议 | 用途 | 状态 |
|------|------|------|------|
| **22** | TCP | SSH | ✅ 必需 |
| **80** | TCP | HTTP | ✅ 必需 |
| **443** | TCP | HTTPS | ✅ 必需 |
| **3306** | TCP | MySQL | 🔒 本地 |
| **6379** | TCP | Redis | 🔒 本地 |

### 检查端口

\`\`\`bash
# 检查端口监听
sudo netstat -tuln | grep -E ':(22|80|443|3306|6379)\s'

# 检查防火墙状态
sudo ufw status verbose
\`\`\`

### 开放端口（如需要）

\`\`\`bash
# 开放 HTTP
sudo ufw allow 80/tcp

# 开放 HTTPS
sudo ufw allow 443/tcp

# 开放 SSH
sudo ufw allow 22/tcp

# 启用防火墙
sudo ufw enable
\`\`\`

### 云服务器防火墙

**如果外部无法访问，请在云服务商控制台添加安全组规则**：

| 云服务商 | 控制台位置 |
|---------|-----------|
| **阿里云** | ECS 实例 → 安全组 → 配置规则 |
| **腾讯云** | CVM 实例 → 安全组 → 修改规则 |
| **AWS** | EC2 → Security Groups |
| **华为云** | ECS → 安全组 |

需要添加的规则：
- 入站规则: TCP 22 (SSH)
- 入站规则: TCP 80 (HTTP)
- 入站规则: TCP 443 (HTTPS)

---

## 🐛 常见问题

### 网站无法访问

1. **检查域名解析**: \`ping ${DOMAIN:-your-domain.com}\`
2. **检查 Nginx**: \`sudo nginx -t && sudo systemctl status nginx\`
3. **检查防火墙**: \`sudo ufw status\`
4. **检查云安全组**: 登录云服务商控制台检查

### Django 502 错误

1. **检查服务**: \`sudo supervisorctl status ${PROJECT_NAME}:django\`
2. **查看日志**: \`sudo supervisorctl tail ${PROJECT_NAME}:django stderr\`
3. **重启服务**: \`sudo supervisorctl restart ${PROJECT_NAME}:django\`

### 数据库连接失败

1. **检查 MySQL**: \`sudo systemctl status mysql\`
2. **测试连接**: \`mysql -u ${DB_USER} -p ${DB_NAME}\`
3. **检查配置**: \`cat ${PROJECT_ROOT}/backend/.env\`

---

## 📞 获取帮助

- 查看完整文档: [SKILL.md](../db-deploy/SKILL.md)
- 查看准备清单: [DEPLOYMENT_CHECKLIST.md](../db-deploy/DEPLOYMENT_CHECKLIST.md)
- 查看配置模板: [templates/](../db-deploy/templates/)

---

**文档生成时间**: ${date}
EOF

    log_info "文档已生成: $doc_file"
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
    echo "║          部署文档生成脚本                                    ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""

    generate_docs

    echo ""
    log_info "🎉 文档生成完成！"
    echo ""
    echo "文档位置: ${PROJECT_ROOT}/DEPLOYMENT_INFO.md"
}

main "$@"
