# ACP 全链路编码工作流 — 架构设计

> 版本：v1.0 | 2026-03-29
> 详细实现见 [`scripts/hardflow/README.md`](../../../scripts/hardflow/README.md)

## 1. 分层架构

| 层 | 职责 | 代表文件 |
|----|------|----------|
| **HardFlow Core** | 阶段机、Gate、验收、完成前验证、评分、证据 | `hardflow-run.sh` |
| **Workflow Profile** | 默认编码工作流的阶段图与能力绑定 | `coding-default@stable` |
| **Skill** | capability 的实现说明 | `skills/by_domain/` |
| **Hook** | 运行时护栏与审计 | `hooks/hardflow-*` |

## 2. 主流程图

```mermaid
graph TD
    A[classify] --> B[G0 requirements ≥93]
    B --> C[dispatch]
    C --> D[G1 solution ≥92]
    D --> E[implement]
    E --> F[test-loop]
    F --> G[review]
    G --> H[G2 frontend ≥92]
    H --> I[G3 backend ≥93]
    I --> J[G4 security ≥95 + veto]
    J --> K[API doc gate]
    K --> L[predeploy gate]
    L --> M[deploy]
    M --> N[post-test]
    N --> O[G5 release ≥92]
    O --> P[G6 final ≥93]
    P --> Q[acceptance-test]
    Q --> R[verify-completion]
    R --> S[git-push]
    S --> T[score-report]
```

## 3. 回流整改机制

```mermaid
graph LR
    A[Gate 评分] -->|≥阈值| B[通过，进入下一阶段]
    A -->|<阈值| C[触发 improve 命令]
    C --> D[整改后重新评分]
    D -->|重试≤max| A
    D -->|超过 max_retries| E[标记失败，中断]
```

## 4. 产物目录

```
.workflow/
├── runs/<run_id>/
│   ├── timeline.log              # 阶段时间线
│   ├── issues.ndjson             # 问题记录
│   ├── scorecards/*.json         # 各 Gate 评分卡
│   ├── score-gate-audit.ndjson   # 评分审计日志
│   ├── acceptance/deployment.json # 部署验收结果
│   └── verification/completion.json # 完成前验证
├── gates/*.json                   # 门禁状态
├── hook-audit/commands.log        # Hook 审计
├── task.json                      # 当前任务
└── progress.txt                   # 进度标记
```

## 5. 进化与晋升

- `coding-default@stable`：当前稳定版本
- `coding-default@candidate`：候选版本（自我进化先改 candidate）
- upgrade feedback / workflow scorecard / skill review 的目标：candidate 重跑 → stable/candidate 对比 → 晋升或回滚
