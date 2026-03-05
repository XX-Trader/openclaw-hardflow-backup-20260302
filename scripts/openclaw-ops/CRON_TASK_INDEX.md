# OpenClaw 定时任务索引（Core / All）

本文档作为项目定时任务总索引，按 `core` / `all` 两个安装档位组织。

## 1. 档位定义

- `core`：安装核心链路任务（`1,2,3,4,5,7,8`）
- `all`：在 `core` 基础上额外安装任务 `6`（互联网进化）

## 2. 一键安装命令

```bash
# 核心档位（推荐）
python3 scripts/openclaw-ops/install_workflow_profile.py \
  --profile core \
  --workflow-repo-path ~/openclaw-hardflow-backup-20260302

# 全量档位（含互联网进化）
python3 scripts/openclaw-ops/install_workflow_profile.py \
  --profile all \
  --workflow-repo-path ~/openclaw-hardflow-backup-20260302
```

可选：如果需要显式指定消息投递目标，可追加：

```bash
--channel telegram --to "<chat_id>"
```

## 3. 任务映射（按你的 8 项）

| # | 任务目标 | 档位 | 对应 Job（name） | 安装入口 | 默认频率 |
|---|---|---|---|---|---|
| 1 | 运维 agent 定期把到期 TODO 发给规划者执行 | core/all | `todo_patrol_15m` | `install_todo_patrol_job.py` | 每 15 分钟 |
| 2 | 运维 agent 监控日志问题并去重报警 | core/all | `ops_incremental_monitor` + `ops_full_calibration` + `ops_daily_summary` | `cron_setup.py`（由 profile 安装器调用） | 15 分钟 + 6 小时 + 每日 |
| 3 | 项目 agent 同步项目 git 与索引（含本地 openclaw 本地 git） | core/all | `project_index_maintainer_30m` + `ops_git_sync_push` + `ops_local_openclaw_git_backup` | `install_project_index_job.py` + `cron_setup.py` + `install_local_openclaw_backup_job.py` | 30 分钟 + 6 小时 + 1 小时 |
| 4 | 优化 agent 基于本地 openclaw/git 更新优化工作流项目 | core/all | `ops_governance_evolution_incremental` | `cron_setup.py` | 6 小时 |
| 5 | 优化 agent 全量看对话与 memory，总结并优化其他 agent（含 agent 评分） | core/all | `ops_conversation_evolution_incremental` + `ops_self_evolution_weekly_todo` | `cron_setup.py` | 6 小时 + 每周 |
| 6 | 优化 agent 从互联网搜进化技能并反哺工作流项目 | all | `ops_github_web_evolution_incremental` | `cron_setup.py`（仅 `--profile all`） | 12 小时 |
| 7 | 每日工作总结（todo/done）并发送钉钉 | core/all | `ops_daily_work_report_dingtalk` | `cron_setup.py` | 每日 00:15 |
| 8 | reviewer agent 技术债审查（每日 + 每周全量） | core/all | `reviewer_incremental_daily_4am` + `reviewer_weekly_structure_review` | `install_reviewer_scan_jobs.py`（`techdebt`） | 每日 04:00 + 每周一 04:40 |

## 4. Git 链路定义

- `~/.openclaw`：仅本地 git 备份（`init/add/commit`），不配置远程，不 push。
- 工作流仓库 `~/openclaw-hardflow-backup-20260302`：走远程同步（`pull + push`），用于共享最新工作流改动。

## 5. 模型说明

- 定时任务脚本本身不硬编码具体模型。
- 实际使用模型由 OpenClaw 运行时配置决定（agent 配置 / model tier 配置）。
- 若要统一切模型档位，可使用：
  - `scripts/openclaw-ops/model_tier_profiles.json`
  - `scripts/openclaw-ops/switch_model_tier.py`

## 6. 安装后快速核对

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
    print(f"{j.get('name')} | {kind} | {expr}")
PY
```

