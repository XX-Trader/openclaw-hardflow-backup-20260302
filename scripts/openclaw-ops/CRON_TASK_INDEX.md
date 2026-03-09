# OpenClaw 定时任务索引（Core / All）
本文档作为项目定时任务总索引，按 `core` / `all` 两个安装档位组织。

## 1. 档位定义
- `core`：安装核心链路任务（`1,2,3,4,5,7,8,9`）。
- `all`：在 `core` 基础上额外安装任务 `6`（互联网进化）与任务 `10`（web-agent 采集与审核链路）。

## 2. 一键安装命令
```bash
# 核心档位
python3 scripts/openclaw-ops/install_workflow_profile.py \
  --profile core \
  --workflow-repo-path ~/openclaw-hardflow-backup-20260302

# 全量档位（含互联网进化 + web-agent）
python3 scripts/openclaw-ops/install_workflow_profile.py \
  --profile all \
  --workflow-repo-path ~/openclaw-hardflow-backup-20260302
```

可选：显式指定消息投递目标
```bash
--channel telegram --to "<chat_id>"
```

## 3. 任务映射（核心 + 全量）
| # | 任务目标 | 档位 | 对应 Job（name） | 安装入口 | 默认频率 |
|---|---|---|---|---|---|
| 1 | 运维 agent 定期把到期 TODO 发给规划者执行 | core/all | `todo_patrol_15m` | `install_todo_patrol_job.py` | 每 15 分钟 |
| 2 | 运维 agent 监控日志问题并去重报警；失败工作流自动派生给优化 agent 的修复任务 | core/all | `ops_incremental_monitor` + `ops_full_calibration` + `ops_daily_summary` | `cron_setup.py`（由 profile 安装器调用） | 15 分钟 + 6 小时 + 每日 |
| 3 | 项目 agent 同步项目 git 与索引（含本地 `~/.openclaw` 备份链路） | core/all | `project_index_maintainer_30m` + `ops_git_sync_push` + `ops_local_openclaw_git_backup` | `install_project_index_job.py` + `cron_setup.py` + `install_local_openclaw_backup_job.py` | 30 分钟 + 6 小时 + 1 小时 |
| 4 | 优化 agent 基于本地 openclaw/git 更新优化工作流项目 | core/all | `ops_governance_evolution_incremental` | `cron_setup.py` | 6 小时 |
| 5 | 优化 agent 全量看对话与 memory，总结并优化其他 agent（含评分） | core/all | `ops_conversation_evolution_incremental` + `ops_self_evolution_weekly_todo` | `cron_setup.py` | 6 小时 + 每周 |
| 6 | 优化 agent 从互联网搜进化技能并反哺工作流项目 | all | `ops_github_web_evolution_incremental` | `cron_setup.py`（仅 `--profile all`） | 12 小时 |
| 7 | 每日工作总结（todo/done）并发送钉钉 | core/all | `ops_daily_work_report_dingtalk` | `cron_setup.py` | 每日 00:15 |
| 8 | reviewer agent 技术债审查（每日 + 每周全量） | core/all | `reviewer_incremental_daily_4am` + `reviewer_weekly_structure_review` | `install_reviewer_scan_jobs.py`（`techdebt`） | 每日 04:00 + 每周一 04:40 |
| 9 | 自动拉取工作流仓库并自动安装（失败仅记录日志） | core/all | `ops_auto_update_install_hourly` | `cron_setup.py` | 每 1 小时 |
| 10 | web-agent 采集互联网 + optimization/project 审核与改造建议 | all（core 可手动开启） | `web_intel_collect_hourly` + `web_intel_review_optimization_4h` + `web_intel_review_project_docs_6h` | `install_web_intel_jobs.py` | 1 小时 + 4 小时 + 6 小时 |

## 4. Web-Agent 链路说明（任务 #10）
- 采集脚本：`web_intel_collect_runner.py`
  - HTTP/API 优先，遇到反爬或失败时可尝试浏览器兜底。
  - 数据落盘到 `~/.openclaw/web/raw|parsed|summary`。
- 审核脚本：`web_intel_review_runner.py`
  - `optimization` 模式：产出流程优化建议。
  - `project-doc` 模式：产出面向代码改造的官方文档建议。
- 安装器：`install_web_intel_jobs.py`
  - 一次写入 3 个 job，并自动复用已有消息投递配置。

## 5. Git 链路定义
- `~/.openclaw`：仅本地 git 备份（`init/add/commit`），不配置远程，不做 push。
- 工作流仓库 `~/openclaw-hardflow-backup-20260302`：走远程同步（`pull + push`），用于共享最新工作流改动。

## 6. 模型说明
- 定时脚本本身不硬编码具体模型；实际模型由 OpenClaw 运行时 agent 配置决定。
- 默认分工：
  - `main` / `coordinator` / `reviewer` -> `openai-codex/gpt-5.4`
  - `optimization-agent` / `backend-dev` / `frontend-dev` / `project-agent` / `agent-factory` -> `openai-codex/gpt-5.3-codex`
  - `ops-agent` / `web-agent` / `tester` / `deployer` / `doc-writer` -> `glmcode/glm-4.7`
- 思考强度规则：
  - Codex 模型默认 `xhigh`
  - 非 Codex 模型默认 `high`
- 统一切换模型档位可用：
  - `scripts/openclaw-ops/model_tier_profiles.json`
  - `scripts/openclaw-ops/switch_model_tier.py`

## 7. 安装后快速核对
```bash
python3 - <<'PY'
import json, os, pathlib
p = pathlib.Path(os.path.expanduser("~/.openclaw/cron/jobs.json"))
data = json.loads(p.read_text(encoding="utf-8-sig"))
for j in data.get("jobs", []):
    if not j.get("enabled", True):
        continue
    s = j.get("schedule", {})
    kind = s.get("kind")
    expr = s.get("expr") if kind == "cron" else s.get("everyMs")
    print(f"{j.get('name')} | {kind} | {expr} | agent={j.get('agentId')}")
PY
```
