# OpenClaw Ops Scripts

这个目录用于维护 OpenClaw 工作流、定时任务和运维巡检脚本。

所有自动消息输出与运行记录统一包含 `sender_identity` 字段，便于排查是谁发送、链路是否正常。

## TODO 巡检

- `todo_patrol.py`
  - 读取 coordinator 的 TODO 与执行看板。
  - 仅对 `UNASSIGNED` 项请求分配。
  - 自动合并 tester 失败项（去重）。
- `install_todo_patrol_job.py`
  - 安装/更新 `TODO 巡检（15分钟）` 到 `~/.openclaw/cron/jobs.json`。

## Cron 工作流

- `ops_cron_runner.py`
  - 统一执行 `incremental/full/daily` 三种模式。
  - 记录增量读取位置（checkpoint）、问题次数、open/resolved/reopened 状态。
  - 增量异常可自动回退全量扫描。
  - 支持每个技能日志开关：`silent`（静默）/`chat`（发聊天）。
  - 高风险始终提醒，不受普通日志开关影响。
- `cron_setup.py`
  - 一键安装 OpenClaw cron jobs（增量监控/全量校准/每日日报）。
  - 可选安装系统定时审计 job（系统 cron + systemd timer + openclaw jobs）。
  - 自动推断 delivery channel/to。
  - 自动写入 `~/.openclaw/ops/cron-monitor-config.json` 的技能日志开关。
- `system_schedule_snapshot.py`
  - 采集系统定时与 OpenClaw 定时快照。
  - 对比历史状态，识别变更与高风险项。
  - 输出 `NO_REPLY` 或告警摘要（附证据路径）。
- `api_test_audit.py`
  - 接口巡检采用单次执行，不做重复重测循环。
  - 支持 `http/playwright/selenium` 模式（浏览器检查可用 playwright/selenium）。
  - 检查接口是否有返回值、必填字段、JSON 合法性、数据时效（旧数据自动高风险）。
  - 空返回值和旧数据都会归类为高风险并落盘证据。
- `daily_work_report.py`
  - 每日从任务中心提取 TODO/DONE。
  - 仅发送新增记录，不重复发送历史 TODO/DONE。
  - 支持钉钉 webhook 通知（无新增记录时输出 `NO_REPLY`）。
- `self_evolution_todo.py`
  - 周度全量复盘历史任务/流程指标。
  - 只产出“建议与任务包”，禁止自动修改工作流与技能。
  - 任务统一写入 TODO（低优先级、高风险、需人工确认），并带 `scheduled_at`。
  - 按 FIFO 时间顺序入队，且每次运行限制最大产出数量，避免批量风险。

## 风险动态更新

- `policy/risk_rule_sync.py`
  - 支持聊天驱动的高低风险关键词更新。
  - 典型高风险：`api变更/参数变更/逻辑变更/流程变更/结构变更`。
  - 典型低风险：`代码bug/配置错误/网络失败/资源告警/重复进程`。

## Policy Enforcer 同步

- `sync_policy_enforcer_to_servers.sh`
- `sync_policy_enforcer_to_servers.ps1`

## 常用命令

```bash
# 安装 cron 工作流（含系统定时审计技能）
python3 scripts/openclaw-ops/cron_setup.py \
  --install-system-schedule-job \
  --install-api-test-job \
  --api-test-engine playwright \
  --api-test-expr "*/15 * * * *" \
  --install-daily-work-job \
  --daily-work-expr "15 0 * * *" \
  --install-self-evolution-job \
  --self-evolution-expr "30 3 * * 1" \
  --self-evolution-min-interval-days 7 \
  --self-evolution-max-tasks-per-run 3 \
  --dingtalk-webhook-env DINGTALK_WEBHOOK_URL \
  --dingtalk-secret-env DINGTALK_SECRET \
  --incremental-log-mode silent \
  --full-log-mode silent \
  --daily-log-mode silent \
  --system-log-mode silent \
  --api-test-log-mode silent \
  --daily-work-log-mode silent \
  --self-evolution-log-mode silent

# 手动执行一次增量巡检
python3 scripts/openclaw-ops/ops_cron_runner.py --mode incremental

# 手动执行一次接口单次全量巡检
python3 scripts/openclaw-ops/api_test_audit.py \
  --config-file ~/.openclaw/ops/api-test-config.json \
  --engine playwright \
  --normal-log-mode silent

# 动态调整风险规则（示例）
python3 scripts/openclaw-ops/policy/risk_rule_sync.py batch \
  --apply-default-preset \
  --add-high "api契约升级" \
  --add-low "临时网络抖动"

# 手动执行一次每日工作钉钉报告（仅新增 todo/done）
python3 scripts/openclaw-ops/daily_work_report.py \
  --db ~/.openclaw/ops/task-center/task_center.db \
  --normal-log-mode silent

# 手动执行一次周度自我进化复盘（只产出 TODO 任务包）
python3 scripts/openclaw-ops/self_evolution_todo.py \
  --db ~/.openclaw/ops/task-center/task_center.db \
  --min-review-interval-days 7 \
  --max-tasks-per-run 3 \
  --normal-log-mode silent

# 手动执行一次系统定时快照审计
python3 scripts/openclaw-ops/system_schedule_snapshot.py --normal-log-mode silent
```
