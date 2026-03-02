# API设计文档模板

> **适用场景**: 中等/复杂功能
> **填写说明**: 定义所有接口的请求和响应格式

---

## 1. 接口概览

**✅ 列出所有接口**

| 接口 | 方法 | 功能 | 认证 |
|------|------|------|------|
| /api/pm-robot/trader-group/create | POST | 创建分组 | ✅ |
| /api/pm-robot/trader-group/list | GET | 获取分组列表 | ✅ |
| /api/pm-robot/trader-group/update | POST | 更新分组 | ✅ |
| /api/pm-robot/trader-group/delete | POST | 删除分组 | ✅ |
| /api/pm-robot/trader-group/add-traders | POST | 添加交易员到分组 | ✅ |
| /api/pm-robot/trader-group/remove-traders | POST | 从分组移除交易员 | ✅ |
| /api/pm-robot/trader-group/batch-start | POST | 批量启动 | ✅ |
| /api/pm-robot/trader-group/batch-stop | POST | 批量停止 | ✅ |

---

## 2. 接口详细设计

### 2.1 创建分组

**接口**: `POST /api/pm-robot/trader-group/create`

**功能描述**: 创建一个新的交易员分组

**请求参数**:

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| groupName | String | ✅ | 分组名称，最长100字符 | "高频交易组" |
| description | String | ❌ | 分组描述，最长500字符 | "高频策略交易员" |

**请求示例**:
```json
{
  "groupName": "高频交易组",
  "description": "高频策略交易员"
}
```

**响应数据**:

| 字段名 | 类型 | 说明 |
|--------|------|------|
| code | Integer | 状态码，200表示成功 |
| msg | String | 提示信息 |
| data.groupId | Integer | 新创建的分组ID |

**响应示例**:
```json
{
  "code": 200,
  "msg": "创建成功",
  "data": {
    "groupId": 123
  }
}
```

**错误码**:

| 错误码 | 说明 | 处理建议 |
|--------|------|----------|
| 4001 | 分组名称不能为空 | 提示用户输入名称 |
| 4002 | 分组名称已存在 | 提示用户更换名称 |
| 5001 | 数据库错误 | 稍后重试或联系客服 |

---

### 2.2 获取分组列表

**接口**: `GET /api/pm-robot/trader-group/list`

**功能描述**: 获取当前用户的所有分组

**请求参数**:

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| page | Integer | ❌ | 页码，默认1 | 1 |
| pageSize | Integer | ❌ | 每页数量，默认20 | 20 |
| keyword | String | ❌ | 搜索关键词 | "高频" |

**请求示例**:
```
GET /api/pm-robot/trader-group/list?page=1&pageSize=20
```

**响应数据**:

| 字段名 | 类型 | 说明 |
|--------|------|------|
| code | Integer | 状态码 |
| msg | String | 提示信息 |
| data.list | Array | 分组列表 |
| data.list[i].groupId | Integer | 分组ID |
| data.list[i].groupName | String | 分组名称 |
| data.list[i].description | String | 分组描述 |
| data.list[i].traderCount | Integer | 交易员数量 |
| data.list[i].createdAt | String | 创建时间 |
| data.total | Integer | 总数量 |

**响应示例**:
```json
{
  "code": 200,
  "msg": "获取成功",
  "data": {
    "list": [
      {
        "groupId": 123,
        "groupName": "高频交易组",
        "description": "高频策略交易员",
        "traderCount": 5,
        "createdAt": "2025-01-05 10:00:00"
      }
    ],
    "total": 1
  }
}
```

---

### 2.3 添加交易员到分组

**接口**: `POST /api/pm-robot/trader-group/add-traders`

**功能描述**: 将一个或多个交易员添加到分组

**请求参数**:

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| groupId | Integer | ✅ | 分组ID | 123 |
| traderIds | Array<Integer> | ✅ | 交易员ID列表 | [1, 2, 3] |

**请求示例**:
```json
{
  "groupId": 123,
  "traderIds": [1, 2, 3]
}
```

**响应数据**:

| 字段名 | 类型 | 说明 |
|--------|------|------|
| code | Integer | 状态码 |
| msg | String | 提示信息 |
| data.successCount | Integer | 成功添加数量 |
| data.failedList | Array | 添加失败的交易员ID |

**响应示例**:
```json
{
  "code": 200,
  "msg": "添加成功",
  "data": {
    "successCount": 2,
    "failedList": [
      {
        "traderId": 3,
        "reason": "该交易员已在其他分组"
      }
    ]
  }
}
```

---

## 3. 数据字典

**通用字段说明**:

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id / groupId / traderId | Integer | 主键ID |
| createdAt / updatedAt | String | 时间戳，格式：YYYY-MM-DD HH:mm:ss |
| isDeleted | Boolean | 是否删除，true表示已删除 |

**状态码说明**:

| 状态码 | 含义 |
|--------|------|
| 200 | 成功 |
| 4001 | 参数错误 |
| 4002 | 数据已存在 |
| 4003 | 数据不存在 |
| 5001 | 服务器内部错误 |

---

## 4. 前端测试数据结构

**用于前端开发时模拟接口响应**:

```javascript
// 分组列表
const MOCK_GROUP_LIST = {
  code: 200,
  msg: "获取成功",
  data: {
    list: [
      {
        groupId: 1,
        groupName: "高频交易组",
        description: "高频策略交易员",
        traderCount: 5,
        createdAt: "2025-01-05 10:00:00"
      },
      {
        groupId: 2,
        groupName: "趋势跟踪组",
        description: "趋势策略交易员",
        traderCount: 3,
        createdAt: "2025-01-04 15:30:00"
      }
    ],
    total: 2
  }
}

// 创建分组响应
const MOCK_CREATE_GROUP = {
  code: 200,
  msg: "创建成功",
  data: {
    groupId: 123
  }
}

// 添加交易员响应
const MOCK_ADD_TRADERS = {
  code: 200,
  msg: "添加成功",
  data: {
    successCount: 2,
    failedList: []
  }
}
```

---

**文档版本**: v1.0
**最后更新**: YYYY-MM-DD
**状态**: 待确认 / 已确认
