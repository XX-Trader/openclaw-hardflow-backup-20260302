# UI原型文档模板

> **适用场景**: 中等/复杂功能
> **填写说明**: 描述页面布局、交互流程、表单字段

---

## 1. 页面概览

**页面名称**: 交易员分组管理

**页面路径**: `/pm-robot/trader-group`

**功能概述**: 管理交易员分组，支持创建、编辑、删除分组，以及添加交易员到分组

---

## 2. 页面布局

### 2.1 整体布局

```
┌──────────────────────────────────────────────────────┐
│  面包屑：首页 > 量化交易 > 交易员分组管理               │
├──────────────────────────────────────────────────────┤
│                                                      │
│  ┌─────────────────┐  ┌──────────────────────────┐  │
│  │  分组列表（左侧）  │  │  交易员列表（右侧）        │  │
│  │                 │  │                          │  │
│  │  ┌───────────┐  │  │  [搜索框]           [+]  │  │
│  │  │高频交易组  │  │  │                          │  │
│  │  │(5人)      │  │  │  ┌──────────────────────┐ │  │
│  │  └───────────┘  │  │  │ 交易员1               │ │  │
│  │  ┌───────────┐  │  │  │ 交易员2               │ │  │
│  │  │趋势跟踪组  │  │  │  │ 交易员3               │ │  │
│  │  │(3人)      │  │  │  └──────────────────────┘ │  │
│  │  └───────────┘  │  │                          │  │
│  │                 │  │  [批量启动] [批量停止]     │  │
│  │  [+ 新建分组]    │  │                          │  │
│  └─────────────────┘  └──────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### 2.2 布局说明

**左侧分组列表**：
- 显示所有分组（卡片样式）
- 每个卡片显示：分组名称、交易员数量
- 点击卡片，右侧显示该分组的交易员
- 底部有"新建分组"按钮

**右侧交易员列表**：
- 顶部：搜索框 + "添加交易员"按钮
- 中间：表格展示交易员
- 底部：批量操作按钮

---

## 3. 交互流程

### 3.1 新建分组流程

```
用户点击"新建分组"
  ↓
弹出对话框
  ↓
┌─────────────────────────┐
│  新建分组                │
├─────────────────────────┤
│  分组名称: [________]    │
│  分组描述: [________]    │
│                         │
│  [取消]      [确定]      │
└─────────────────────────┘
  ↓
用户输入信息
  ↓
点击"确定"
  ↓
前端验证（名称不为空、长度不超过100）
  ↓
调用API: POST /api/pm-robot/trader-group/create
  ↓
成功：关闭对话框，刷新列表
失败：显示错误提示
```

### 3.2 添加交易员流程

```
用户点击"添加交易员"
  ↓
弹出穿梭框对话框
  ↓
┌────────────────────────────────────────┐
│  添加交易员到分组                       │
├────────────────────────────────────────┤
│  [待选交易员列表]      [已选交易员列表] │
│  ☑ 交易员1            →  交易员5       │
│  ☑ 交易员2               交易员6       │
│  ☐ 交易员3               交易员7       │
│  ☐ 交易员4                            │
│                                        │
│  [取消]                  [确定]        │
└────────────────────────────────────────┘
  ↓
用户选择交易员
  ↓
点击"确定"
  ↓
前端验证（至少选择1个，检查是否已在其他分组）
  ↓
调用API: POST /api/pm-robot/trader-group/add-traders
  ↓
成功：关闭对话框，刷新列表，显示"成功添加X个交易员"
失败：显示失败原因（如"交易员XX已在YY分组"）
```

### 3.3 批量操作流程

```
用户勾选多个交易员
  ↓
点击"批量启动"
  ↓
弹出确认对话框："确定启动选中的3个交易员？"
  ↓
用户点击"确定"
  ↓
调用API: POST /api/pm-robot/trader-group/batch-start
  ↓
显示加载状态："正在启动..."
  ↓
成功：显示"成功启动3个交易员"，刷新列表
失败：显示失败原因
```

---

## 4. 表单字段定义

### 4.1 新建分组表单

| 字段 | 类型 | 必填 | 验证规则 | 占位符 |
|------|------|------|----------|--------|
| 分组名称 | 文本输入 | ✅ | 长度1-100，不能重复 | 请输入分组名称 |
| 分组描述 | 文本域 | ❌ | 最长500字符 | 请输入分组描述（选填） |

### 4.2 添加交易员表单

| 字段 | 类型 | 必填 | 验证规则 | 说明 |
|------|------|------|----------|------|
| 交易员列表 | 穿梭框(Transfer) | ✅ | 至少选择1个 | 左侧显示所有未分组交易员 |

### 4.3 搜索表单

| 字段 | 类型 | 必填 | 验证规则 | 占位符 |
|------|------|------|----------|--------|
| 关键词 | 文本输入 | ❌ | - | 搜索交易员名称 |

---

## 5. 前端测试数据

**严格按照API响应格式设计，方便后续替换为真实接口**

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

// 交易员列表
const MOCK_TRADER_LIST = {
  code: 200,
  msg: "获取成功",
  data: {
    list: [
      {
        traderId: 1,
        traderName: "交易员Alpha",
        exchange: "Binance",
        status: 1, // 1=运行中, 0=已停止
        profitRate: 15.5,
        createdAt: "2025-01-01 10:00:00"
      },
      {
        traderId: 2,
        traderName: "交易员Beta",
        exchange: "OKX",
        status: 1,
        profitRate: 8.3,
        createdAt: "2025-01-02 14:00:00"
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

// 批量启动响应
const MOCK_BATCH_START = {
  code: 200,
  msg: "操作成功",
  data: {
    successCount: 3,
    failedList: []
  }
}
```

**使用方式**：
```vue
<script setup>
import { ref } from 'vue'

// 开发阶段使用测试数据
const isDevelopment = import.meta.env.DEV
const groupList = ref(isDevelopment ? MOCK_GROUP_LIST.data.list : [])

// 实际调用
async function fetchGroupList() {
  if (isDevelopment) {
    groupList.value = MOCK_GROUP_LIST.data.list
    return
  }

  const res = await api.getGroupList()
  groupList.value = res.data.list
}
</script>
```

---

## 6. 状态说明

### 6.1 加载态

**场景**: 首次加载、刷新列表、提交表单

**展示**:
- 列表区域显示骨架屏（Skeleton）
- 按钮显示loading状态

**实现**:
```vue
<el-skeleton :loading="loading" animated>
  <template #template>
    <el-skeleton-item variant="h3" style="width: 50%" />
    <el-skeleton-item variant="rect" style="width: 100%; height: 200px" />
  </template>
  <template #default>
    <!-- 真实内容 -->
  </template>
</el-skeleton>
```

### 6.2 错误态

**场景**: 接口请求失败、数据为空

**展示**:
- 列表区域显示空状态插图（Empty）
- 错误信息显示在页面顶部

**实现**:
```vue
<el-empty v-if="!list.length && !loading" description="暂无数据">
  <el-button type="primary" @click="handleCreate">创建分组</el-button>
</el-empty>
```

### 6.3 空态

**场景**: 列表无数据

**展示**:
- 显示空状态插图
- 显示引导文案"还没有分组，点击创建"
- 显示"创建分组"按钮

---

## 7. 组件拆分

**建议拆分的组件**：

| 组件名 | 功能 | 文件位置 |
|--------|------|----------|
| GroupManage.vue | 主页面组件 | src/views/pm-robot/ |
| GroupCard.vue | 分组卡片组件 | src/components/pm-robot/ |
| GroupCreateDialog.vue | 创建分组对话框 | src/components/pm-robot/ |
| AddTraderDialog.vue | 添加交易员对话框 | src/components/pm-robot/ |
| TraderTable.vue | 交易员表格组件 | src/components/pm-robot/ |

---

## 8. 样式规范

**颜色**:
- 主色：`#409EFF`（Element Plus 蓝）
- 成功：`#67C23A`
- 警告：`#E6A23C`
- 危险：`#F56C6C`
- 文字：`#303133`（主文字）、`#606266`（次要文字）

**间距**:
- 卡片间距：16px
- 表单项间距：24px
- 按钮间距：12px

**圆角**:
- 卡片：4px
- 对话框：4px
- 按钮：4px

---

**文档版本**: v1.0
**最后更新**: YYYY-MM-DD
**状态**: 待确认 / 已确认
