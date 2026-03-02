# 百度地图 MCP 使用说明

> 本目录包含百度地图 MCP 服务的详细配置说明。

**版本**: 1.0.0
**NPM 包**: `@baidumap/mcp-server-baidu-map@1.0.5`

---

## 快速开始

### 1. 获取百度地图 API Key

1. 访问 [百度地图开放平台](https://lbsyun.baidu.com/)
2. 注册/登录账号
3. 进入控制台 → 创建应用 → 选择服务端API
4. 复制获得的 AK (API Key)

### 2. 配置环境变量

在 `travel-skills` 根目录的 `.env` 文件中添加:

```
BAIDU_MAP_API_KEY=你的百度地图AK密钥
```

### 3. 启动百度地图 MCP

```bash
cd C:\Users\superma\.claude\skills\travel-skills
npm run baidu
```

---

## MCP 可用工具

### 地理编码 (`map_geocode`)
- **功能**: 地址 → 坐标转换（BD-09坐标系）
- **参数**: `address` (待解析的地址)
- **返回**: `{ lat, lng, precise, confidence, level }`

### 逆地理编码 (`map_reverse_geocode`)
- **功能**: 坐标 → 地址转换
- **参数**: `latitude`, `longitude`
- **返回**: 详细地址信息、POI、道路等

### 地点检索 (`map_search_places`)
- **功能**: 检索POI/地点
- **参数**: `query` (关键词), `region`/`bounds`/`location` (三选一)
- **返回**: 地点列表 `{ name, location, address, ... }`

### 路线规划 (`map_directions`)
- **功能**: 计算两点间路线
- **参数**: `origin` (纬度,经度), `destination` (纬度,经度), `mode` (driving/walking/riding/transit)
- **返回**: 距离、时长、路线步骤

### 天气查询 (`map_weather`)
- **功能**: 查询实时天气和预报
- **参数**: `districtId` (行政区划代码) 或 `location` (经度,纬度)
- **返回**: 实时天气和未来5天预报

---

## 在旅游技能中的应用

百度地图主要用于：

1. **HTML 地图可视化**: 使用百度地图 JavaScript API v3.0
2. **路线规划**: 开车路线、徒步路线、公交路线
3. **轨迹绘制**: 在地图上绘制旅游路线轨迹
4. **坐标转换**: 将 GCJ-02 坐标（高德）转换为 BD-09（百度）

### HTML 地图示例

```javascript
// 初始化百度地图
var map = new BMap.Map('map');
var point = new BMap.Point(114.529010, 22.553920);
map.centerAndZoom(point, 12);

// 绘制路线
var path = [
  new BMap.Point(起点经度, 起点纬度),
  new BMap.Point(终点经度, 终点纬度)
];
var polyline = new BMap.Polyline(path, {
  strokeColor: '#ff4757',
  strokeWeight: 4,
  strokeOpacity: 0.9
});
map.addOverlay(polyline);
```

---

## API 限制

- **配额**: 免费版每日 10万次 调用
- **QPS**: 免费版每秒 10次
- **服务**: Web服务API（非JavaScript API）

---

## 坐标系统

百度地图使用 **BD-09** 坐标系，与高德地图的 GCJ-02 不同：

| 服务 | 坐标系 | 说明 |
|------|--------|------|
| 高德地图 | GCJ-02 | 国测局坐标（火星坐标） |
| 百度地图 | BD-09 | 百度坐标，在 GCJ-02 基础上加密 |

**转换**: 需要时使用坐标转换工具进行转换。

---

## 故障排除

### 问题: "AK 不存在"
- **解决**:
  1. 确认 API Key 正确
  2. 检查应用服务类型选择"服务端API"

### 问题: "无权限"
- **解决**:
  1. 确认 IP 白名单配置正确
  2. 检查应用是否已启用

### 问题: "MCP 连接失败"
- **解决**:
  1. 检查 `.env` 文件是否存在
  2. 确认 API Key 格式正确
  3. 运行 `npm run baidu` 查看 MCP 日志

---

## 更新日志

- **2025-01-18**: v1.0.0 - 整合到统一旅游技能管理目录
