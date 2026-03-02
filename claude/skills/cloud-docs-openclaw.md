# 云文档 + OpenClaw 配置指南

**更新时间**: 2026-02-25 15:20
**服务器**: tokyo-claw (43.167.192.49)

---

## Google Docs 配置

### 1. 安装 gog CLI

```bash
cd /tmp
git clone --depth 1 --branch v0.5.0 https://github.com/steipete/gogcli.git
cd gogcli
GOTOOLCHAIN=auto GOSUMDB=sum.golang.org make
cp bin/gog /usr/local/bin/
```

### 2. OAuth 凭证

1. [Google Cloud Console](https://console.cloud.google.com/) 创建项目
2. 启用 API: Gmail, Calendar, Drive, Docs, Sheets, Contacts
3. 创建 OAuth 2.0 凭证 (Desktop app)
4. 下载 JSON 凭证

```bash
gog auth credentials /path/to/client_secret.json
```

### 3. 授权 (无 TTY)

```bash
# 生成链接
gog auth add your@email.com --services gmail,calendar,drive,contacts,docs,sheets --manual

# 访问链接授权后，用 curl 交换 token
curl -X POST 'https://oauth2.googleapis.com/token' \
  -d 'code=YOUR_CODE' \
  -d 'client_id=YOUR_CLIENT_ID' \
  -d 'client_secret=YOUR_CLIENT_SECRET' \
  -d 'redirect_uri=http://localhost:1' \
  -d 'grant_type=authorization_code'

# 导入 token
export GOG_KEYRING_PASSWORD='your-password'
echo '{"email":"your@email.com","refresh_token":"YOUR_REFRESH_TOKEN","scopes":[...]}' > /tmp/token.json
gog auth tokens import /tmp/token.json
```

### 4. 环境变量

```bash
# ~/.bashrc
export GOG_KEYRING_PASSWORD="tokyo-claw-gog-2026"
export GOG_ACCOUNT="mawenzhe1993@gmail.com"
```

### 5. systemd 服务

```ini
# ~/.config/systemd/user/openclaw-gateway.service
[Service]
Environment=GOG_KEYRING_PASSWORD=tokyo-claw-gog-2026
Environment=GOG_ACCOUNT=mawenzhe1993@gmail.com
```

---

## 飞书配置 (待补充)

TODO

---

## 当前状态

| 服务 | 状态 | 账户 |
|------|------|------|
| Google Workspace | ✅ 已配置 | mawenzhe1993@gmail.com |
| 飞书 | ⏳ 待配置 | - |
