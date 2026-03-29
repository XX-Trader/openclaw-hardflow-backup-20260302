# 巡检故障闭环工作流 — 架构设计

> 版本：v1.0 | 2026-03-29

## 数据流

```mermaid
graph TB
    subgraph 异常采集
        A1[ops-agent sessions/] --> B[unified_exception_logger]
        A2[optimization-agent sessions/] --> B
        A3[reviewer sessions/] --> B
    end
    subgraph 分类与去重
        B -->|7类分类| C[exception-reports/]
        B -->|MD5指纹| D{是否已知}
    end
    subgraph 修复
        D -->|新异常| E[fault_knowledge_base 匹配]
        E -->|success_rate>0.8| F[自动修复脚本]
        E -->|无匹配| G[创建 TODO 工单]
        D -->|重复| H[跳过/计数器+1]
    end
    subgraph 审计
        I[Agent 会话日志] --> J[claim_verification_auditor]
        J -->|诚信度报告| K[claim-audit/]
    end
```

## 异常分类规则

| 类型 | 关键词匹配 | 修复策略 |
|------|-----------|---------|
| api_error | timeout, 429, 401, connection refused | 重试+限流退避 |
| filesystem_error | permission denied, no such file, disk full | 权限修复/目录创建 |
| config_error | invalid json, missing key, parse error | config_watchdog 回滚 |
| agent_communication_error | handoff failed, no response | coordinator 重分配 |
| system_error | OOM, segfault, zombie process | 进程重启/内存清理 |
| path_validation_error | path traversal, unsafe path | 路径白名单校验 |
| general_error | 未匹配上述分类 | 工单化人工处理 |
