# ACP 全链路编码工作流

> 状态：✅ 已上线 | 触发方式：人工触发
> 上级目录：[核心主工作流](../README.md)

## 功能概述

OpenClaw 的核心编码工作流引擎（HardFlow Core），实现从需求拆解到部署上线的全链路自动化。通过 G0-G6 七道独立评分门禁 + 评分回流整改机制，确保每个环节达到质量标准后才能进入下一阶段。

## 核心能力

1. **G0-G6 七道门禁** — 需求/方案/前端/后端/安全/发布/终审各独立评分
2. **评分回流** — 门禁不通过自动回流整改，最多重试3次
3. **部署验收** — 部署后自动执行验收测试（gateway/status/plugins/hooks/cron）
4. **完成前验证** — 依赖验收产物，防止未验证就 git-push
5. **安全一票否决** — G4 Security Gate 高危未闭环直接失败
6. **证据落盘** — 全流程产物写入 `.workflow/runs/<run_id>/`

## 文档清单

| 文档 | 内容 |
|------|------|
| [架构设计](architecture.md) | 阶段流程图、门禁阈值、产物目录 |
| [评分系统升级](评分系统升级/README.md) | 评分数据源修复、评分标准 Skill、进化闭环接通 |
| HardFlow 详细文档 | [HardFlow Automation Skill](../../../skills/openclaw-hardflow-automation/SKILL.md) |

## 主流程（23个阶段）

```
classify → G0需求 → dispatch → G1方案 → implement → test-loop → review
→ G2前端 → G3后端 → G4安全 → API-doc-gate → predeploy-gate
→ preview-deploy → deploy → post-test → G5发布 → G6终审
→ postdeploy-gate → acceptance-test → verify-completion
→ preview-git-push → git-push → score-report
```

## Gate 阈值

| Gate | 名称 | 阈值 | 特殊规则 |
|------|------|------|----------|
| G0 | requirements | ≥93 | — |
| G1 | solution | ≥92 | — |
| G2 | frontend | ≥92 | — |
| G3 | backend | ≥93 | — |
| G4 | security | ≥95 | 一票否决 |
| G5 | release | ≥92 | — |
| G6 | final | ≥93 | — |

## 核心文件

| 文件 | 说明 |
|------|------|
| `scripts/hardflow/hardflow-run.sh` | 主执行器（44KB） |
| `scripts/hardflow/check-score-gate.mjs` | 单 Gate 评分校验器 |
| `scripts/hardflow/score-policy.json` | 门禁阈值配置 |
| `scripts/hardflow/check-api-doc-gate.sh` | 接口文档门禁 |
| `scripts/hardflow/check-review-test-gate.sh` | 部署前后综合门禁 |
| `scripts/hardflow/check-deployment-acceptance.sh` | 部署后验收 |
| `scripts/hardflow/check-completion-verification.sh` | 完成前验证 |
| `scripts/hardflow/atomic_task_guard.py` | 原子化任务守卫 |

## 关联 Hook

| Hook | 功能 |
|------|------|
| `hardflow-command-guard` | 命令守卫（拦截危险命令） |
| `hardflow-policy-enforcer` | 策略执行（硬约束检查） |
| `hardflow-audit` | 审计日志（操作留痕） |
| `hardflow-failure-detector` | 失败检测（异常捕获） |
| `hardflow-stop-gate-reminder` | 门禁提醒（阻断通知） |
