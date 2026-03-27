# 错误驱动进化协议

> 版本：v1.0 | 2026-03-28

## 1. 概述

将 `system_exception_patrol`（异常巡检）产出的异常报告与故障知识库（fault_knowledge_base）集成，
实现「异常→诊断→修复建议→自动修复/人工修复→经验沉淀」的闭环。

## 2. 数据流

```mermaid
graph LR
    A[system_exception_patrol] -->|异常报告| B[/abnormal/ 归档]
    B --> C{fault_knowledge_base}
    C -->|已知故障| D[自动修复脚本]
    C -->|未知故障| E[创建 TODO 工单]
    D --> F[修复结果验证]
    E --> F
    F -->|成功| G[经验沉淀到 fault_kb]
    F -->|失败| H[升级为人工干预]
```

## 3. fault_knowledge_base 结构

位置：`~/.openclaw/ops/fault-kb/`

```
fault-kb/
├── index.json              # 故障指纹→修复方案索引
├── fixes/
│   ├── api_timeout.json    # 修复方案：API 超时
│   ├── disk_full.json      # 修复方案：磁盘满
│   └── ...
└── history/
    └── 2026-03-28.jsonl    # 修复历史记录
```

### 3.1 index.json

```json
{
  "schema_version": "1.0",
  "entries": {
    "api_error:rate_limit": {
      "fix_file": "fixes/api_rate_limit.json",
      "auto_fix": true,
      "success_rate": 0.95,
      "last_seen": "2026-03-28T04:00:00Z"
    },
    "filesystem_error:disk_full": {
      "fix_file": "fixes/disk_full.json",
      "auto_fix": true,
      "success_rate": 0.90,
      "last_seen": "2026-03-28T04:00:00Z"
    }
  }
}
```

### 3.2 修复方案文件

```json
{
  "fault_id": "api_error:rate_limit",
  "description": "API 限速导致调用失败",
  "diagnosis_steps": [
    "检查最近 1 小时的 API 调用频率",
    "确认是否超出 rate limit 配额"
  ],
  "auto_fix_commands": [
    "sleep 60",
    "python3 ~/.openclaw/ops/retry_failed_tasks.py --task-type api_call"
  ],
  "manual_fallback": "如果自动修复失败，请检查 API Key 配额并联系服务商",
  "prevention": "考虑增加请求间隔或申请更高配额"
}
```

## 4. 集成点

### 4.1 异常巡检→故障知识库匹配

`system_exception_patrol` 在每次扫描后，将异常指纹与 `fault-kb/index.json` 匹配：
- **匹配到已知故障**：若 `auto_fix=true` 且 `success_rate > 0.8`，自动执行修复
- **未匹配**：创建 TODO 工单并标记为新故障类型

### 4.2 修复结果→经验沉淀

每次修复（成功或失败）都记录到 `history/` 目录，用于：
- 更新 `success_rate`
- 发现新的修复方案
- 识别退化的修复方案

## 5. 当前状态

| 组件 | 状态 |
|------|------|
| system_exception_patrol 异常报告 | ✅ 已就绪 |
| abnormal/ 归档目录 | ✅ 已就绪 |
| fault-kb/ 目录结构 | 📋 协议定义完成 |
| 自动匹配+修复 | 📋 待实现（按需渐进） |
| 经验沉淀逻辑 | 📋 待实现 |

## 6. 落地路径

1. **Phase 1**（当前）：定义协议、目录结构、数据格式
2. **Phase 2**：实现 index.json 匹配逻辑，手动维护修复方案
3. **Phase 3**：自动从修复历史中学习，更新 success_rate
4. **Phase 4**：与 memory_to_skill_extractor 集成，将高频修复封装为 Hook
