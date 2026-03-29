# 记忆知识沉淀工作流 — 架构设计

> 版本：v1.0 | 2026-03-29

## 分层数据流

```mermaid
graph TB
    subgraph 数据采集层
        A1[Agent 对话记忆 .md] --> B1[memory_to_skill_extractor]
        A2[task_center.db 执行历史] --> B2[agent_self_evolution]
        A3[仓库代码变更] --> B3[governance_evolution_runner]
        A4[Agent 会话日志] --> B4[conversation_evolution_runner]
    end
    subgraph 知识提炼层
        B1 -->|高频修复模式| C1[Draft Skill/Hook]
        B2 -->|Agent 评分报告| C2[evolution-reports/]
        B3 -->|治理优化项| C3[self-evolution/reports/]
        B4 -->|对话洞察| C4[conversation-evolution/]
    end
    subgraph 落地层
        C1 -->|需人工激活| D1[skills/ 或 hooks/]
        C2 -->|优化建议| D2[TODO.md]
        C3 -->|碎片化 TODO| D3[todo.md]
        C4 -->|最佳实践| D4[经验库]
    end
```

## Agent 自进化评估维度

| 维度 | 权重 | 数据来源 |
|------|------|----------|
| 成功率 | 30% | tasks.status 统计 |
| 效率 | 20% | tasks.duration_ms |
| 质量 | 30% | tasks.result_score + stability_score |
| 可靠性 | 20% | token_records.cost + consecutiveErrors |

## 治理进化策略

- **增量模式**：仅扫描自上次以来的 git diff（`--mode incremental`）
- **最小间隔**：180分钟内不重复执行
- **碎片化处理**：大型优化建议自动拆解为多个原子 TODO
- **上下文门禁**：`--project-context-gate` 确保新任务附带项目上下文
