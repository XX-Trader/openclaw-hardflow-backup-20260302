# amap-visualize - 高德地图可视化技能

## 功能描述

将高德地图 MCP 查询结果转换为 HTML 可视化页面，自动在浏览器中打开展示。

## 触发条件

当用户查询涉及以下内容时自动触发：
- 地点搜索 (POI)
- 路径规划
- 周边搜索
- 地理编码结果

## 执行流程

### 1. 调用高德地图 MCP
```
使用 amap-maps MCP 工具获取数据
```

### 2. 生成 HTML 文件

根据查询类型生成对应的 HTML：

#### A. 地点搜索 (POI)
```python
# 数据结构
{
  "type": "poi_search",
  "title": "搜索: {关键词}",
  "center": [经度, 纬度],
  "zoom": 14,
  "pois": [
    {"name": "名称", "address": "地址", "location": [lng, lat], "distance": "距离"}
  ]
}
```

#### B. 路径规划
```python
{
  "type": "route",
  "title": "{起点} → {终点}",
  "center": [中心经度, 中心纬度],
  "zoom": 12,
  "routes": {
    "distance": "总距离",
    "duration": "预计时间",
    "steps": ["路径描述..."],
    "path": [[lng1, lat1], [lng2, lat2], ...]
  }
}
```

#### C. 周边搜索
```python
{
  "type": "around",
  "title": "{中心点}周边搜索",
  "center": [经度, 纬度],
  "zoom": 15,
  "center_name": "中心点名称",
  "radius": 1000,
  "pois": [...]
}
```

### 3. 输出路径
```
mcp/output/{timestamp}_{type}.html
```

### 4. 自动打开
```bash
start mcp/output/{filename}.html
```

## JavaScript 模板代码

### 添加 POI 标记
```javascript
{{POIS}}.forEach((poi, index) => {
  const marker = new AMap.Marker({
    position: poi.location,
    title: poi.name,
    label: {
      content: `${index + 1}. ${poi.name}`,
      direction: 'top'
    }
  });
  map.add(marker);
});
```

### 绘制路线
```javascript
const polyline = new AMap.Polyline({
  path: {{PATH_COORDINATES}},
  borderWeight: 2,
  strokeColor: '#667eea',
  lineJoin: 'round'
});
map.add(polyline);

// 添加起点终点标记
new AMap.Marker({ position: {{START_POINT}}, icon: '起点' });
new AMap.Marker({ position: {{END_POINT}}, icon: '终点' });
```

### 周边搜索圆形
```javascript
const circle = new AMap.Circle({
  center: {{CENTER}},
  radius: {{RADIUS}},
  fillColor: 'rgba(102, 126, 234, 0.1)',
  strokeColor: '#667eea'
});
map.add(circle);
```

## 使用示例

### 用户输入
```
搜索北京天安门附近的加油站
```

### AI 执行
1. 调用 `amap_maps_around` 搜索
2. 解析返回的 POI 数据
3. 生成 HTML 文件到 `mcp/output/`
4. 自动在浏览器打开

### 输出文件
```
mcp/output/20250109_143022_around.html
```

## 侧边栏内容模板

### POI 搜索
```html
<h3>📍 搜索结果 ({{COUNT}}个)</h3>
{{POI_ITEMS}}
```

### 路线规划
```html
<div class="route-info">
  <div class="distance">{{DISTANCE}}</div>
  <div class="duration">{{DURATION}}</div>
</div>
<h3>🗺️ 路线详情</h3>
{{ROUTE_STEPS}}
```

## 注意事项

1. API Key 已在模板中配置: `8d27975243e4497e51c4c78b632cc692`
2. 输出文件使用时间戳命名，避免覆盖
3. 地图默认使用 3D 视图，可调整 `pitch` 参数
4. 支持的浏览器: Chrome, Edge, Firefox 最新版

---

**版本**: 1.0.0
**创建时间**: 2025-01-09
