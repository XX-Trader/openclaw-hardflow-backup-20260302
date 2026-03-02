# universal-travel-planner - 通用旅游规划技能

## 功能描述

全功能旅游规划解决方案，整合需求询问、地图可视化、社交媒体数据采集。使用**百度地图JavaScript API**生成交互式地图，输出**移动端优先**的响应式HTML页面。

---

## 核心功能

1. **需求收集** - 4阶段结构化询问
2. **目标分解** - 时间轴规划 + 阻力点分析
3. **百度地图可视化** - 双地图（开车+徒步）、POI标记
4. **小红书数据采集** - 真实用户评价、避坑指南
5. **综合输出** - Markdown攻略 + 移动端HTML页面

---

## 触发条件

- "帮我做个攻略" / "制定出行计划"
- "从A到B怎么去"
- "推荐旅游景点/路线"
- 任何旅游规划相关请求

---

## 执行流程

### 第一步：需求询问（必须）

使用 `AskUserQuestion` 工具询问以下信息：

```javascript
// 第一轮：基础信息
{
  "questions": [
    {
      "question": "出发时间和地点是什么？",
      "header": "出发信息",
      "options": [
        {"label": "早上出发", "description": "6:00-10:00出发，避开早高峰"},
        {"label": "中午出发", "description": "11:00-14:00出发"},
        {"label": "下午出发", "description": "15:00-18:00出发"}
      ],
      "multiSelect": false
    },
    {
      "question": "出行人数是多少？",
      "header": "人数",
      "options": [
        {"label": "1-2人", "description": "情侣/独行"},
        {"label": "3-5人", "description": "小团体/朋友"},
        {"label": "6人以上", "description": "大团体/家庭"}
      ],
      "multiSelect": false
    },
    {
      "question": "大家的体力状况如何？",
      "header": "体力评估",
      "options": [
        {"label": "体力充沛", "description": "经常运动，可以爬山徒步"},
        {"label": "体力一般", "description": "日常活动量一般"},
        {"label": "体力较弱", "description": "偏好轻松休闲"}
      ],
      "multiSelect": false
    }
  ]
}

// 第二轮：交通方式
{
  "questions": [
    {
      "question": "交通方式偏好？",
      "header": "交通",
      "options": [
        {"label": "自驾", "description": "自由灵活，考虑停车费"},
        {"label": "高铁+打车", "description": "快速便捷"},
        {"label": "飞机+接送", "description": "远距离首选"}
      ],
      "multiSelect": false
    }
  ]
}

// 第三轮：活动偏好
{
  "questions": [
    {
      "question": "主要想体验什么？",
      "header": "活动",
      "options": [
        {"label": "爬山徒步", "description": "体力消耗大"},
        {"label": "休闲观光", "description": "轻松拍照"},
        {"label": "水上活动", "description": "划船、游泳等"},
        {"label": "美食探店", "description": "当地特色美食"}
      ],
      "multiSelect": true
    }
  ]
}
```

---

### 第二步：目标分解与阻力分析

#### 2.1 时间轴分解模板

| 小目标 | 时间窗口 | 完成标准 | 依赖 |
|--------|----------|----------|------|
| G1: 出发 | XX:XX-XX:XX | ✅ 准时出发 | 无 |
| G2: 到达目的地 | XX:XX-XX:XX | ✅ 到达停车场/入口 | G1 |
| G3: 核心活动 | XX:XX-XX:XX | ✅ 完成体验 | G2 |
| G4: 午餐/休息 | XX:XX-XX:XX | ✅ 恢复体力 | G3 |
| G5: 继续活动 | XX:XX-XX:XX | ✅ 完成备选项目 | G4 |
| G6: 返程 | XX:XX-XX:XX | ✅ 到家 | G5 |

#### 2.2 阻力点分析模板

| 阻力类型 | 具体表现 | 应对策略 |
|----------|----------|----------|
| 👥 人 | 体力不支 | 设置放弃点 |
| 🚗 堵车 | 高峰延误 | 提前/延后出发 |
| 😤 情绪 | 疲劳不耐烦 | 安排休息时间 |
| ⚠️ 意外 | 天气/故障 | 备选方案 |

---

### 第三步：百度地图生成

#### 3.1 百度地图坐标获取

**方法A：使用百度地图MCP**（推荐）

```javascript
// 调用百度地图MCP工具
// 1. 地理编码：地址 → 坐标
map_geocode({ address: "深圳东西冲" })
// 返回: { lat: 22.553920, lng: 114.529010 }

// 2. 路线规划
map_directions({
  origin: "22.553920,114.529010",  // 纬度,经度
  destination: "22.478670,114.532060",
  mode: "driving"  // driving/walking/riding/transit
})
```

**方法B：手动拾取坐标**

1. 访问 [百度地图坐标拾取器](https://api.map.baidu.com/lbsapi/getpoint/index.html)
2. 搜索地点
3. 点击地图获取坐标（BD-09格式）
4. 复制经纬度

#### 3.2 坐标系说明

| 坐标系 | 说明 | 使用场景 |
|--------|------|----------|
| BD-09 | 百度地图专用坐标 | 百度地图API |
| GCJ-02 | 国测局坐标（火星坐标） | 高德地图、腾讯地图 |
| WGS-84 | GPS原始坐标 | Google地球、GPS设备 |

**重要**: 百度地图使用 **BD-09** 坐标，如果从其他平台获取坐标需要转换。

#### 3.3 HTML地图模板（移动端优先）

**核心设计特点**：
- **最大宽度**: 750px（标准移动端）
- **暗色渐变**: #1a1a2e → #16213e → #0f3460
- **毛玻璃效果**: backdrop-filter: blur(10px)
- **双地图**: 开车路线 + 徒步路线独立加载
- **费用分离**: 共用费用（AA）+ 个人费用（自理）

```html
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>{{目的地}}完整攻略</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body {
    width: 100%;
    min-width: 320px;
    max-width: 750px;
    margin: 0 auto;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    background: linear-gradient(180deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    color: #fff;
    line-height: 1.8;
  }

  /* 顶部标题区 */
  .header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 30px 15px 20px;
    text-align: center;
    border-radius: 0 0 24px 24px;
    position: relative;
    overflow: hidden;
  }
  .header-emoji { font-size: 45px; margin-bottom: 8px; display: block; }
  .header h1 { font-size: 22px; font-weight: 700; margin-bottom: 6px; position: relative; z-index: 1; }
  .header-subtitle { font-size: 12px; opacity: 0.9; position: relative; z-index: 1; }
  .data-source {
    font-size: 11px;
    opacity: 0.8;
    margin-top: 8px;
    padding: 4px 8px;
    background: rgba(255,255,255,0.1);
    border-radius: 10px;
    display: inline-block;
  }

  /* 基本信息卡片 */
  .info-card {
    background: rgba(255,255,255,0.1);
    backdrop-filter: blur(10px);
    border-radius: 16px;
    padding: 22px;
    margin: 20px 15px;
    border: 1px solid rgba(255,255,255,0.1);
  }
  .info-title {
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .info-title .icon { font-size: 18px; }

  /* 信息网格 */
  .info-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
  }
  .info-item {
    background: rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 14px 8px;
    text-align: center;
  }
  .info-item .label { font-size: 11px; opacity: 0.7; margin-bottom: 4px; }
  .info-item .value { font-size: 14px; font-weight: 600; color: #ffd700; }

  /* 详细攻略区域 */
  .detail-section {
    background: rgba(255,255,255,0.08);
    border-radius: 10px;
    padding: 16px;
    margin: 14px 0;
  }
  .detail-section h3 {
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 12px;
    color: #ffd700;
  }
  .detail-section p, .detail-section li {
    font-size: 12px;
    opacity: 0.9;
    line-height: 1.7;
    margin: 8px 0;
  }

  /* 地图卡片 */
  .map-card {
    background: rgba(255,255,255,0.1);
    backdrop-filter: blur(10px);
    border-radius: 16px;
    margin: 20px 15px;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,0.1);
  }
  .map-card-header {
    padding: 12px 15px;
    background: rgba(0,0,0,0.2);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .map-card-title { font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 6px; }
  .map-card-badge {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: #fff;
    padding: 3px 8px;
    border-radius: 12px;
    font-size: 10px; font-weight: 600;
  }
  .map-container { height: 400px; position: relative; background: #000; }
  #drivingMap, #hikingMap { width: 100%; height: 100%; }

  /* 时间线 */
  .timeline { padding: 12px 0; }
  .timeline-item {
    display: flex;
    margin-bottom: 14px;
    position: relative;
  }
  .timeline-item::before {
    content: ''; position: absolute; left: 23px; top: 32px; bottom: -14px;
    width: 2px; background: linear-gradient(180deg, #667eea 0%, transparent 100%);
  }
  .timeline-item:last-child::before { display: none; }
  .timeline-time {
    width: 46px; height: 46px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 10px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    flex-shrink: 0;
    margin-right: 10px;
    font-size: 10px;
    font-weight: 700;
  }
  .timeline-content {
    flex: 1;
    background: rgba(255,255,255,0.06);
    border-radius: 8px;
    padding: 10px 12px;
  }
  .timeline-title { font-weight: 600; font-size: 13px; margin-bottom: 3px; }
  .timeline-desc { font-size: 12px; opacity: 0.7; }

  /* 装备网格 */
  .equipment-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
  }
  .equipment-item {
    background: rgba(255,255,255,0.08);
    border-radius: 10px;
    padding: 10px;
    display: flex;
    align-items: flex-start;
    gap: 8px;
  }
  .equipment-icon { font-size: 20px; flex-shrink: 0; }
  .equipment-text h4 { font-size: 13px; font-weight: 600; margin-bottom: 2px; }
  .equipment-text p { font-size: 11px; opacity: 0.7; }

  /* 表格通用样式 */
  .toilet-table {
    background: rgba(255,255,255,0.08);
    border-radius: 10px;
    overflow-x: auto;
    margin: 14px 0;
  }
  .toilet-table table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }
  .toilet-table th, .toilet-table td {
    padding: 12px 14px;
    text-align: left;
    border-bottom: 1px solid rgba(255,255,255,0.1);
  }
  .toilet-table th {
    color: #ffd700;
    font-weight: 600;
    font-size: 13px;
    background: rgba(255,215,0,0.15);
  }
  .toilet-table tr:hover {
    background: rgba(255,255,255,0.05);
  }

  /* 底部 */
  .footer {
    text-align: center;
    padding: 20px 15px 25px;
    opacity: 0.5;
    font-size: 10px;
  }

  /* 响应式 */
  @media (max-width: 375px) {
    .header h1 { font-size: 22px; }
    .info-grid { grid-template-columns: repeat(2, 1fr); }
  }
</style>
</head>
<body>
  <!-- 内容结构 -->
  <!-- 参考 旅游/output/20250118_dongxichong_travel_plan_v2.6.html -->
</body>
</html>
```

---

### 第四步：小红书数据采集（可选）

#### 4.1 搜索关键词

```javascript
// 搜索目的地评价
xhs_search_notes({ query: "{{目的地}} 评价" })

// 搜索路线攻略
xhs_search_notes({ query: "{{目的地}} 路线攻略" })

// 搜索避坑指南
xhs_search_notes({ query: "{{目的地}} 避坑" })
```

#### 4.2 数据处理规则

- 过滤明显广告（大量emoji、营销话术）
- 优先选择带图/视频的笔记
- 选择近期发布（30天内）
- 提取关键信息：评分、避坑点、推荐时间

---

### 第五步：输出文件

#### 5.1 文件命名

```
Markdown: {YYYYMMDD}_攻略_{起点}到{目的地}_{人数}人出行.md
HTML: 旅游/output/{YYYYMMDD}_{目的地英文}_travel_plan_v{版本}.html
```

#### 5.2 浏览器预览

```bash
# Windows
start 旅游/output/{html文件名}.html

# macOS
open 旅游/output/{html文件名}.html

# Linux
xdg-open 旅游/output/{html文件名}.html
```

---

## 设计特点

### 移动端优先

| 特性 | 说明 |
|------|------|
| 最大宽度 | 750px（标准移动端宽度） |
| viewport | user-scalable=no 防止缩放 |
| 响应式 | 375px以下双列布局 |
| 字体 | 10-22px 适配小屏幕 |

### 暗色主题

| 元素 | 样式 |
|------|------|
| 背景 | 渐变 #1a1a2e → #16213e → #0f3460 |
| 卡片 | rgba(255,255,255,0.1) + 毛玻璃 |
| 文字 | 白色 #fff |
| 强调色 | 金色 #ffd700 |

### 双地图设计

| 地图 | 用途 | 高度 |
|------|------|------|
| 开车路线 | 显示长途路径 | 400px |
| 徒步路线 | 详细节点标注 | 400px |

### 费用预算结构

```javascript
// 共用费用（AA制）
{
  油费: ¥200,
  过路费: ¥105,
  停车费: ¥25,
  小计: ¥330,
  每人分摊: ¥165 (2人AA)
}

// 个人费用（自理）
{
  食物: ¥80,
  备用金: ¥50,
  小计: ¥130/人
}

// 总计
{
  单人: ¥295 (共用¥165 + 个人¥130),
  团队: ¥590 (2人)
}
```

---

## 百度地图API参考

### JavaScript API v3.0

```javascript
// 创建地图
var map = new BMap.Map('map');
map.centerAndZoom(new BMap.Point(lng, lat), zoom);

// 添加标注
var marker = new BMap.Marker(new BMap.Point(lng, lat));
map.addOverlay(marker);

// 绘制折线
var polyline = new BMap.Polyline([
  new BMap.Point(lng1, lat1),
  new BMap.Point(lng2, lat2)
], {
  strokeColor: '#ff4757',
  strokeWeight: 4,
  strokeOpacity: 0.9
});
map.addOverlay(polyline);

// 信息窗口
var infoWindow = new BMap.InfoWindow('内容', {
  width: 200,
  height: 60,
  title: '标题'
});
marker.openInfoWindow(infoWindow);

// 调整视野
map.setViewport([point1, point2, point3]);

// 启用滚轮缩放
map.enableScrollWheelZoom(true);

// 设置动画
marker.setAnimation(BMAP_ANIMATION_BOUNCE);
setTimeout(function() {
  marker.setAnimation(null);
}, 3000);
```

### MCP工具

| 工具 | 用途 | 参数 |
|------|------|------|
| `map_geocode` | 地址→坐标 | `{address}` |
| `map_reverse_geocode` | 坐标→地址 | `{latitude, longitude}` |
| `map_search_places` | 地点搜索 | `{query, region/bounds/location}` |
| `map_directions` | 路线规划 | `{origin, destination, mode}` |
| `map_distance_matrix` | 距离矩阵 | `{origins[], destinations[], mode}` |
| `map_weather` | 天气查询 | `{districtId / location}` |
| `map_road_traffic` | 路况查询 | `{roadName, city}` |

---

## 技术配置

```yaml
百度地图:
  JavaScript API Key: cKX39VLGSPOyiRXObDiNC3YMDJtnsgtl
  MCP包名: @baidumap/mcp-server-baidu-map@1.0.5
  启动命令: npm run baidu
  坐标系: BD-09

小红书:
  MCP包名: @iflow-mcp/xhs-mcp@0.8.7
  启动命令: npm run xhs
  Cookie配置: mcp/.env 中设置 XHS_COOKIE

输出目录:
  HTML: 旅游/output/
  Markdown: 项目根目录
```

---

## 快速检查清单

### 需求收集
- [ ] 出发时间确认
- [ ] 出发地点确认
- [ ] 人数确认
- [ ] 体力评估确认
- [ ] 交通方式确认
- [ ] 活动偏好确认

### 规划阶段
- [ ] 时间轴分解完成
- [ ] 阻力点分析完成
- [ ] 费用预算计算完成（共用+个人）
- [ ] 备选方案准备

### 地图生成
- [ ] 坐标获取（BD-09格式）
- [ ] 开车路线点定义
- [ ] 徒步路线点定义
- [ ] 节点标注定义
- [ ] HTML文件生成
- [ ] 浏览器打开测试

### 输出确认
- [ ] Markdown攻略生成
- [ ] HTML页面可访问
- [ ] 开车地图正确
- [ ] 徒步地图正确
- [ ] 移动端显示正常
- [ ] 小红书数据整合（如需要）

---

## 常见问题

**Q: 百度地图无法显示？**
A: 检查API Key是否正确，确认网络可以访问百度API。

**Q: 坐标位置不对？**
A: 确认使用BD-09坐标系，其他坐标系需要转换。

**Q: 移动端显示异常？**
A: 检查viewport设置，确保max-width为750px。

**Q: 小红书搜索无结果？**
A: 检查Cookie是否过期，使用 `npx xhs-mcp login` 重新登录。

**Q: 地图加载失败？**
A: 检查浏览器控制台错误，确认AK没有超出配额。

---

**版本**: 2.0.0
**更新时间**: 2025-01-18
**更新内容**:
- 全新的移动端优先设计（750px宽度）
- 暗色渐变主题（毛玻璃效果）
- 双地图支持（开车+徒步独立加载）
- 费用预算分共用/个人详细列出
- 响应式布局（375px以下适配）
- 丰富的信息卡片（餐饮、厕所、装备等）
- 基于实战案例更新：深圳东西冲海岸线徒步
