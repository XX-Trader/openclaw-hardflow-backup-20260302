---
name: "openclaw-auto-evolution"
description: "OpenClaw 自动进化经验系统（hooks + memory + 定时维护）部署与运维手册"
version: "1.0.0"
lastUpdated: "2026-03-01"
---

# OpenClaw 自动进化经验系统

## 1. 目标

把问题解决经验自动沉淀、自动召回、自动进化，形成可复用的经验资产。

核心流程：

1. 采集（capture）
2. 召回（recall）
3. 进化（evolve）
4. 维护（daily/weekly/monthly）

## 2. 目录建议

- 执行目录：`~/.openclaw/hardflow-hooks`
- 本地备份：`~/.claude/hooks/hardflow`
- 技能备份：`~/.claude/skills/openclaw-auto-evolution`

## 3. 必开 hooks

- `hardflow-experience-capture`
- `hardflow-experience-recall`
- `hardflow-experience-evolve`

可选配套：

- `hardflow-command-guard`
- `hardflow-audit`
- `hardflow-stop-gate-reminder`

## 4. 配置入口

详见：

- `REQUIRED_INFO.md`
- `DEPLOY_GUIDE.md`
- `QUICK_CHECK_COMMANDS.md`

## 5. 当前状态（2026-03-01）

已复核 6 台 OpenClaw 服务器：

- hooks `10/10 ready`
- 3 个自动进化 hooks 全部 `enabled=true`
- cron 日/周/月维护任务全部存在
