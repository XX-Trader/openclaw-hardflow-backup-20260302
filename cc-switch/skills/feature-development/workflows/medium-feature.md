# 中等功能流程（前端先行版）

> **适用场景**: 2个表及以上、前后端联动、多个接口

---

## 流程图

```
用户输入需求
    ↓
识别为中等功能
    ↓
生成需求文档
    ↓
等待用户确认
    ↓
生成UI原型（含测试数据）⭐ 前端先行
    ↓
等待用户确认UI效果
    ↓
生成API设计（基于UI需求）⭐ API适配UI
    ↓
等待用户确认
    ↓
生成数据库设计（基于API）⭐ 数据库适配API
    ↓
等待用户确认
    ↓
生成技术方案总结
    ↓
开始实施开发
    ↓
联调测试
    ↓
完成
```

---

## 为什么前端先行？

### 传统流程的问题
```
需求 → 技术方案 → 数据库 → API → UI
```
- ❌ UI最后做，如果效果不好，前面都白做
- ❌ API设计时不知道UI实际需要什么数据
- ❌ 数据库设计时可能包含用不到的字段
- ❌ 调整成本高（改UI → 改API → 改数据库）

### 前端先行的优势
```
需求 → UI（测试数据） → API → 数据库
```
- ✅ **UI优先**：用户先看到效果，确认体验后再做后端
- ✅ **API适配UI**：UI需要什么数据，API就返回什么（不多不少）
- ✅ **数据库适配API**：API字段确定后，数据库结构自然清晰
- ✅ **调整成本低**：改UI不用动后端，改测试数据即可
- ✅ **测试数据即API**：UI用的测试数据结构，直接作为API响应规范

---

## 判定标准

满足以下**任意一个**条件即为中等功能：

- ✅ 涉及2个及以上数据库表
- ✅ 需要新增/修改3个及以上接口
- ✅ 前端和后端需要联动开发
- ✅ 需要新建一个完整的功能模块
- ✅ 涉及多对多关系、外键关联

---

## 文档生成顺序（前端先行版）

### 顺序调整的原因

1. **需求文档** - 明确做什么
2. **UI原型（含测试数据）** - ⭐ **前端先行**，确定数据展示需求
3. **API设计** - ⭐ **API适配UI**，响应格式与测试数据一致
4. **数据库设计** - ⭐ **数据库适配API**，字段映射到表结构
5. **技术方案总结** - 回顾整体方案，确认无误

---

## 各阶段输出

### 阶段1：需求文档（3分钟阅读）

**包含**：
- 功能概述
- 详细功能点
- 业务规则和约束
- 边界情况处理
- 实现思路（如何做，但不写代码）

**不包含**：
- 具体字段定义
- API接口路径
- 前端组件名称

---

### 阶段2：UI原型（含测试数据）⭐ 关键环节

**包含**：
- 页面布局（ASCII图）
- 交互流程
- 表单字段
- **完整的测试数据结构**（按照真实API格式设计）

**测试数据示例**：
```javascript
// 严格按照API响应格式设计
const MOCK_GROUP_LIST = {
  code: 200,
  msg: "获取成功",
  data: {
    list: [
      {
        groupId: 1,
        groupName: "高频交易组",
        traderCount: 5,
        createdAt: "2025-01-05 10:00:00"
      }
    ],
    total: 1
  }
}
```

**关键原则**：
- ✅ 测试数据字段名与API保持一致（如 `groupId` 不是 `group_id`）
- ✅ 测试数据结构完全模拟API响应
- ✅ 后续开发时，API响应必须与测试数据一致

**前端使用方式**：
```javascript
const isDevelopment = import.meta.env.DEV
const groupList = ref(isDevelopment ? MOCK_GROUP_LIST.data.list : [])

async function fetchGroupList() {
  if (isDevelopment) {
    groupList.value = MOCK_GROUP_LIST.data.list
    return
  }
  const res = await api.getGroupList()
  groupList.value = res.data.list
}
```

---

### 阶段3：API设计（基于UI需求）⭐ 适配UI

**包含**：
- 接口路径和方法
- 请求参数（字段名、类型、说明）
- **响应数据（与UI测试数据完全一致）**
- 错误码说明

**关键点**：
- ✅ 响应字段名与测试数据一致（前端不需要改代码）
- ✅ 响应结构与测试数据一致（前端不需要改逻辑）

**示例**：
```javascript
// UI测试数据定义了：
{ groupId, groupName, traderCount, createdAt }

// API响应必须完全一致：
{
  "code": 200,
  "data": {
    "list": [
      {
        "groupId": 1,        // 与测试数据一致
        "groupName": "...",   // 与测试数据一致
        "traderCount": 5,     // 与测试数据一致
        "createdAt": "..."    // 与测试数据一致
      }
    ]
  }
}
```

---

### 阶段4：数据库设计（基于API）⭐ 适配API

**包含**：
- 表结构（字段、类型、约束）
- **API字段到数据库字段的映射**
- 索引设计
- 关联关系

**字段映射示例**：

| API字段 | 数据库字段 | 类型 | 说明 |
|---------|-----------|------|------|
| groupId | id | BIGINT | API用驼峰，DB用下划线 |
| groupName | group_name | VARCHAR(100) | 命名转换 |
| traderCount | (关联查询) | - | 虚拟字段，需计算 |
| createdAt | created_at | DATETIME | 命名转换 |

**关键点**：
- ✅ API字段与数据库字段的映射关系清晰
- ✅ 复杂字段（如 traderCount）说明如何计算
- ✅ 命名转换规则明确（camelCase ↔ snake_case）

---

### 阶段5：技术方案总结

**包含**：
- 推荐方案（一句话）
- 涉及的文件和模块
- 关键技术点
- 潜在风险

**不包含**：
- 详细代码逻辑
- 具体函数签名

**为什么放在最后**：
- UI、API、数据库都确定后，技术方案更准确
- 避免因后续调整导致方案返工

---

## 前端测试数据标准（重点）

### 核心原则

**测试数据结构 = API响应结构**

### 命名规范

| 层级 | 命名规范 | 示例 |
|------|----------|------|
| 前端/测试数据 | camelCase | `groupId`, `groupName` |
| API响应 | camelCase | `groupId`, `groupName` |
| 数据库字段 | snake_case | `group_id`, `group_name` |

### 转换示例

```javascript
// ✅ 正确：测试数据与API一致
const MOCK_DATA = {
  groupId: 1,           // API也返回 groupId
  groupName: "高频交易组" // API也返回 groupName
}

// ❌ 错误：测试数据与API不一致
const MOCK_DATA = {
  group_id: 1,          // API返回的是 groupId（前端要改代码）
  group_name: "高频交易组"
}
```

---

## 示例：交易员分组管理（前端先行版）

### 第1步：需求文档
```
功能概述：支持将交易员分组管理...

详细功能点：
- 创建分组（名称、描述）
- 将交易员添加到分组（多选）
- 查看分组下的交易员列表
- 对分组进行批量启停
```

**用户**: "OK"

### 第2步：UI原型⭐
```
测试数据（重点）：
const MOCK_GROUP_LIST = {
  code: 200,
  data: {
    list: [
      {
        groupId: 1,           // ⭐ 注意：用驼峰命名
        groupName: "高频交易组",
        traderCount: 5,
        createdAt: "2025-01-05 10:00:00"
      }
    ],
    total: 1
  }
}
```

**用户**: "OK，效果可以"

### 第3步：API设计⭐
```
GET /api/pm-robot/trader-group/list

响应（与测试数据完全一致）：
{
  "code": 200,
  "data": {
    "list": [
      {
        "groupId": 1,        // ⭐ 与测试数据一致
        "groupName": "高频交易组",
        "traderCount": 5,
        "createdAt": "2025-01-05 10:00:00"
      }
    ],
    "total": 1
  }
}

字段映射：
groupId → id (数据库字段)
groupName → group_name
traderCount → (关联查询计算)
createdAt → created_at
```

**用户**: "OK"

### 第4步：数据库设计⭐
```
pm_trader_group 表：
- id (对应API的groupId)
- group_name (对应API的groupName)
- created_at (对应API的createdAt)

说明：
- traderCount是虚拟字段，需要通过关联查询计算
- 命名转换：API用驼峰，DB用下划线
```

**用户**: "OK"

### 第5步：技术方案总结
```
推荐方案：新增分组表和关联表

涉及文件：
- pm_robot/models/: PMTraderGroup, PMTraderGroupMember
- pm_robot/views/: 分组CRUD视图
- 前端: TraderGroupManage.vue

关键点：
- traderCount通过annotate计算
- API响应序列化时转换字段名
```

**用户**: "OK"

### 第6步：开始实施
前端先开发（用测试数据），后端按API规范实现...

---

## 时间估算

| 阶段 | 预计时间 |
|------|----------|
| 需求文档 | 1分钟 |
| UI原型（含测试数据） | 2分钟 |
| API设计 | 1分钟 |
| 数据库设计 | 1分钟 |
| 技术方案总结 | 30秒 |
| **文档总耗时** | **约5.5分钟** |
| 等待确认 | - |
| 实施开发 | 根据复杂度 |

---

## 与简单功能的区别

| 维度 | 简单功能 | 中等功能（前端先行） |
|------|----------|---------------------|
| 文档 | 无 | 5个文档（顺序调整） |
| 确认 | 交付后确认 | 每个文档确认 |
| UI | 直接改代码 | ⭐ 先做UI原型（含测试数据） |
| API | 直接改代码 | ⭐ API适配UI测试数据 |
| 数据库 | 直接改代码 | ⭐ 数据库适配API字段 |
| 测试数据 | 无 | ⭐ 必须提供，且与API一致 |

---

## 已有功能新增（前端先行版）

### 场景1：纯UI调整

```
修改前端UI（测试数据）
  ↓
确认效果
  ↓
完成（不动后端）
```

### 场景2：涉及数据变更

```
修改前端UI（测试数据）
  ↓
确认UI效果
  ↓
判断是否需要改API
  ↓
调整API响应（如果需要）
  ↓
调整数据库（如果需要）
```

**关键**：每一步确认后，再决定是否需要下一步

---

**最后更新**: 2025-01-05
