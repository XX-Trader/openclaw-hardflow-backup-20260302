# 旅游技能统一管理目录

> 本目录用于统一管理所有旅游相关的 MCP 服务配置和技能文件，方便跨项目调用和修改。

**版本**: 1.0.0
**更新日期**: 2025-01-18
**关联技能**: `universal-travel-planner` v2.2

---

## 目录结构

```
travel-skills/
├── README.md                    # 本文件 - 统一管理说明
├── package.json                 # 统一的 MCP 依赖管理
├── .env.example                 # 环境变量模板
├── .env                         # 实际环境变量（需手动创建）
├── start-travel-mcps.bat        # Windows 启动脚本
├── start-travel-mcps.sh         # Linux/Mac 启动脚本
├── xhs-config/                  # 小红书配置
│   └── README.md                # 小红书 MCP 使用说明
├── baidu-config/                # 百度地图配置
│   └── README.md                # 百度地图 MCP 使用说明
└── amap-config/                 # 高德地图配置
    └── README.md                # 高德地图 MCP 使用说明
```

---

## 快速开始

### 1. 安装依赖

```bash
cd C:\Users\superma\.claude\skills\travel-skills
npm install
```

### 2. 配置环境变量

复制环境变量模板：
```bash
cp .env.example .env
```

然后编辑 `.env` 文件，填入你的 API 密钥：

```bash
# 小红书 Cookie（必填）
XHS_COOKIE=a1=xxxxx; webId=xxxxx; webBuild=xxxxx; ...

# 百度地图 API Key（必填）
BAIDU_MAP_API_KEY=你的百度地图AK密钥

# 高德地图 API Key（可选，已通过 amap-maps MCP 全局安装）
AMAP_API_KEY=你的高德地图密钥
```

### 3. 启动 MCP 服务

**Windows**:
```bash
start-travel-mcps.bat
```

**Linux/Mac**:
```bash
bash start-travel-mcps.sh
```

或手动启动单个服务：
```bash
npm run xhs      # 小红书
npm run baidu    # 百度地图
npm run amap     # 高德地图
```

---

## 服务说明

### 小红书 MCP (`xhs-config/`)
- **功能**: 攻略采集、用户评价、避坑指南
- **NPM 包**: `@iflow-mcp/xhs-mcp@0.8.7`
- **获取方式**: 浏览器 F12 获取 Cookie
- **有效期**: Cookie 通常 7-30 天过期

### 百度地图 MCP (`baidu-config/`)
- **功能**: 路线规划、轨迹绘制、HTML地图可视化
- **NPM 包**: `@baidumap/mcp-server-baidu-map@1.0.5`
- **获取方式**: [百度地图开放平台](https://lbsyun.baidu.com/)
- **限制**: 免费版每日 10万次 / QPS 10次

### 高德地图 MCP (`amap-config/`)
- **功能**: 天气、POI、周边、位置、路线规划（GCJ-02）
- **NPM 包**: `amap-maps-mcp-server`
- **状态**: ✅ 已全局安装
- **获取方式**: [高德开放平台](https://lbs.amap.com/)

---

## 坐标系统说明

| 服务 | 坐标系 | 说明 |
|------|--------|------|
| 高德地图 | GCJ-02 | 国测局坐标（火星坐标） |
| 百度地图 | BD-09 | 百度坐标，在 GCJ-02 基础上加密 |
| 小红书 | - | 文本内容，不涉及坐标 |

**坐标转换**:
- GCJ-02 → BD-09: 用于百度地图显示
- BD-09 → GCJ-02: 用于高德地图显示

---

## 与 universal-travel-planner 技能集成

本配置目录与 `C:\Users\superma\.claude\skills\universal-travel-planner.md` 技能文件无缝集成：

1. **技能触发关键词**: 攻略、旅游、出行、路线、计划、景点、美食、海滩、爬山、徒步
2. **自动调用**: 当用户提问包含上述关键词时，自动触发旅游技能
3. **数据流程**:
   ```
   用户提问 → 触发技能 → 并行调用三个服务 → 生成攻略 → 输出 HTML 地图
   ```

---

## 输出目录

生成的攻略文件保存至：
- **Markdown**: `旅游/攻略/{日期}_攻略_{目的地}_{人数}.md`
- **HTML 地图**: `旅游/output/{日期}_{地点英文}_travel_plan.html`
- **查看地图**: 启动本地服务器 `python -m http.server 6789` 访问 http://127.0.0.1:6789/

---

## 故障排除

### 小红书 Cookie 过期
- **现象**: 搜索返回"登录状态过期"
- **解决**: 重新获取 Cookie 并更新 `.env` 文件

### 百度地图 API 调用失败
- **现象**: 返回 "AK 不存在" 或 "无权限"
- **解决**:
  1. 确认 API Key 正确
  2. 检查应用服务类型选择"服务端API"
  3. 确认 IP 白名单配置正确

### MCP 服务未启动
- **现象**: Claude Code 无法调用工具
- **解决**:
  1. 检查 `npm install` 是否成功
  2. 运行 `npm run xhs` 查看错误日志
  3. 确认 `.env` 文件存在且格式正确

---

## 更新日志

- **2025-01-18**: v1.0.0 - 创建统一管理目录，整合小红书、百度地图、高德地图 MCP

---

## 相关链接

- [Claude Code 技能索引](../SKILLS_INDEX.md)
- [通用旅游规划技能 v2.2](../universal-travel-planner.md)
- [MCP 协议规范](https://modelcontextprotocol.io/)
