# 小红书 MCP 配置指南

## 快速开始

### 1. 获取小红书 Cookie

**步骤**：
1. 打开 Chrome/Edge 浏览器
2. 访问 https://www.xiaohongshu.com 并登录
3. 按 `F12` 打开开发者工具
4. 点击 `Application` 标签页
5. 左侧找到 `Cookies` → `https://www.xiaohongshu.com`
6. 复制所有 Cookie，格式如:
   ```
   a1=xxxxx; webId=xxxxx; webBuild=xxxxx; ...
   ```

### 2. 配置环境变量

#### 方案A：系统环境变量（推荐用于全局配置）

1. 右键 "此电脑" → "属性" → "高级系统设置"
2. 点击 "环境变量"
3. 点击 "新建" 或 "编辑"
4. 变量名：`XHS_COOKIE`
5. 变量值：你复制的 Cookie 字符串
6. 点击"确定"保存

#### 方案B：用户目录配置文件

**创建文件**：
- Windows: `C:\Users\你的用户名\.xhs-mcp\.env`
- Linux/Mac: `~/.xhs-mcp/.env`

**文件内容**：
```bash
XHS_COOKIE=a1=xxxxx; webId=xxxxx; webBuild=xxxxx; ...
```

**或使用统一配置文件**：
- `C:\Users\你的用户名\.claude\skills\travel-skills\.env`

### 3. 启动小红书 MCP

```bash
npm run xhs
```

或创建启动脚本：
```batch
@echo off
cd /d C:\Users\你的用户名\.claude\skills\travel-skills
npm run xhs
pause
```

---

## 使用说明

配置完成后，在 Claude Code 中可以直接调用小红书搜索：
```
用户: 帮我搜索深圳东西冲海岸线的旅游攻略
AI: [调用 xhs_search_notes] → 返回相关笔记列表
```

---

## 注意事项

1. **Cookie 有效期**: Cookie 通常 7-30 天过期，需要定期更新
2. **请求频率**: 避免频繁请求，可能被限流
3. **内容质量**: 搜索结果可能包含广告，需要过滤
4. **安全**: 不要分享你的 Cookie，它包含你的登录信息

---

## 更新日志

- **2025-01-18**: 创建小红书配置指南
