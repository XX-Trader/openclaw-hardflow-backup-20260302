# 小红书 MCP 使用说明

> 本目录包含小红书 MCP 服务的详细配置说明。

**版本**: 1.0.0
**NPM 包**: `@iflow-mcp/xhs-mcp@0.8.7`

---

## 快速开始

### 1. 获取小红书 Cookie

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

在 `travel-skills` 根目录的 `.env` 文件中添加:

```
XHS_COOKIE=a1=xxxxx; webId=xxxxx; webBuild=xxxxx; ...
```

### 3. 启动小红书 MCP

```bash
cd C:\Users\superma\.claude\skills\travel-skills
npm run xhs
```

---

## MCP 可用工具

### 搜索笔记 (`xhs_search_notes`)
- **参数**: `query` (搜索关键词)
- **返回**: 笔记列表（标题、作者、内容摘要、点赞数等）
- **示例**: 搜索"深圳东西冲攻略"

### 获取笔记详情 (`xhs_get_note_detail`)
- **参数**: `note_id` (笔记ID)
- **返回**: 完整笔记内容、图片、标签等

### 获取用户信息 (`xhs_get_user_info`)
- **参数**: `user_id` (用户ID)
- **返回**: 用户昵称、简介、粉丝数等

---

## 在旅游技能中的应用

当使用 `universal-travel-planner` 技能时：

1. **攻略采集**: 自动搜索目的地相关笔记
2. **用户评价**: 提取真实用户反馈和评分
3. **避坑指南**: 整合用户的注意事项和经验分享
4. **拍照打卡点**: 提取热门拍照位置推荐

---

## 注意事项

1. **Cookie 有效期**: 通常 7-30 天过期，需要定期更新
2. **请求频率**: 避免频繁请求，可能被限流
3. **内容质量**: 搜索结果可能包含广告，需要过滤

---

## 故障排除

### 问题: "登录状态过期"
- **解决**: 重新获取 Cookie 并更新 `.env` 文件

### 问题: "搜索无结果"
- **解决**: 尝试更换搜索关键词

### 问题: "MCP 连接失败"
- **解决**:
  1. 检查 `.env` 文件是否存在
  2. 确认 Cookie 格式正确
  3. 运行 `npm run xhs` 查看 MCP 日志

---

## 替代方案

如果小红书 MCP 未安装，旅游技能会使用：
1. 浏览器搜索 + 网页抓取
2. 通用旅游攻略知识库
3. 用户提供的评价模板

详见 `universal-travel-planner.md` 中的"替代方案"章节。

---

## 更新日志

- **2025-01-18**: v1.0.0 - 整合到统一旅游技能管理目录
