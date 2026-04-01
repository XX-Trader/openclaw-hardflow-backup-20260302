# HardFlow 流程优化定时任务

## 1. 目标

在已有“经验卡自我进化”基础上，新增一个独立的“流程优化巡检”任务，用于持续评估并固化交付流程质量：

1. 修改后是否完成测试
2. 是否完成复核
3. 是否达到上线前验收门槛
4. 部署后是否回归通过，失败是否正确回滚
5. 运维可观测与应急资料是否完备
6. 代码中是否存在过多无效/备份残留文件

## 2. 执行脚本

1. 主分析脚本：`scripts/hardflow/process-optimize.mjs`
2. cron 运行器：`scripts/hardflow/process-optimize-cron.sh`
3. 远程安装任务：`scripts/hardflow/remote-install-maintenance-cron.sh`（已包含该任务）

## 3. 定时策略

默认安装以下 3 条任务（服务器时区）：

```cron
5 2 * * *   process-optimize-cron.sh daily
20 2 * * 1  process-optimize-cron.sh weekly
35 2 1 * *  process-optimize-cron.sh monthly
```

说明：

1. `daily`：快速健康巡检，关注最近 7 天
2. `weekly`：趋势复盘，关注最近 21 天
3. `monthly`：长期稳定性复盘，关注最近 60 天

## 4. 输出产物

脚本会写入以下文件：

1. `.workflow/process-optimization/latest-report.json`
2. `.workflow/process-optimization/history.ndjson`
3. `.workflow/process-optimization/SOP_PROCESS_OPTIMIZATION.md`
4. `memory/YYYY-MM-DD.md`（追加当日流程优化摘要）

## 5. 可选命令配置（hardflow.env）

可在 `~/.openclaw/hardflow/hardflow.env` 配置额外主动检查命令：

```bash
export HARDFLOW_PROCESS_CMD_TEST='bash $HOME/Project/scripts/test-all.sh'
export HARDFLOW_PROCESS_CMD_REVIEW='bash $HOME/Project/scripts/hardflow/review.sh'
export HARDFLOW_PROCESS_CMD_ACCEPTANCE='bash $HOME/Project/scripts/hardflow/check-review-test-gate.sh --stage predeploy'
export HARDFLOW_PROCESS_CMD_POSTDEPLOY='bash $HOME/Project/scripts/hardflow/check-review-test-gate.sh --stage postdeploy'
export HARDFLOW_PROCESS_CMD_OPS='bash $HOME/Project/scripts/ops/health-check.sh'
export HARDFLOW_PROCESS_CMD_HYGIENE='git -C $HOME/Project diff --check'

export HARDFLOW_PROCESS_MAX_BACKUP_FILES='8'
export HARDFLOW_PROCESS_CMD_TIMEOUT_SEC='900'
```

未配置命令时，脚本只做基于 `.workflow` 与仓库结构的被动巡检。

## 6. 部署

执行：

```bash
bash scripts/hardflow/deploy-evolution-hooks.sh
```

仅下发到单台（例如行情中心）：

```bash
bash scripts/hardflow/deploy-evolution-hooks.sh hangqing-zhongxin
```

该部署会自动：

1. 下发 `process-optimize` 相关脚本
2. 安装新增 cron
3. 立即执行一次 `daily` 流程优化巡检

## 7. 回滚

如需停用流程优化任务：

1. 在目标机 `crontab -e` 删除 `process-optimize-cron.sh` 三条任务
2. 删除 `~/.openclaw/hardflow-hooks/tools/process-optimize.mjs` 与 `process-optimize-cron.sh`
3. 保留历史报告以便后续审计（可选）
