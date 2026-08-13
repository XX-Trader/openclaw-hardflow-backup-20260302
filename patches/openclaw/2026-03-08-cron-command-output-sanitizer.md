# 2026-03-08 Cron Command Output Sanitizer

## 背景与原因

线上 6 台非 `HOST_F` 服务器的 cron 对话历史里，多个 `agentTurn` command-runner 任务把模型的自然语言废话直接投递到了聊天通道，而不是投递真实命令输出或 `NO_REPLY`。

已确认的典型误发包括：

- `Let's execute the command exactly as scheduled.`
- `Okay, let's remove the invalid --output-mode argument and run the command again.`
- `Backup completed successfully! Here's the summary:`
- `Okay, the Django + Vue full-stack scaffold is now complete!`

这些文本都不是 runner 脚本的原始输出，而是 isolated cron agent 在命令执行前后追加的叙述或改写。当前官方 cron 逻辑默认取“最后一段非空文本”作为 summary/delivery，因此一旦模型多说一句，就会把废话发到 Telegram。

## 影响范围

改动点位于官方 submodule：

- `vendor/openclaw-official/src/cron/isolated-agent/helpers.ts`
- `vendor/openclaw-official/src/cron/isolated-agent/run.ts`

以及对应回归测试：

- `vendor/openclaw-official/src/cron/isolated-agent/helpers.test.ts`
- `vendor/openclaw-official/src/cron/isolated-agent/run.command-only-contract.test.ts`
- `vendor/openclaw-official/src/cron/isolated-agent/run.test-harness.ts`

## 对应上游版本

- submodule 基线：`v2026.3.2`
- 当前本地 vendor ref：`85377a28175695c224f6589eb5c1460841ecd65c`
- 本地验证补丁提交：`333796d0b`（branch: `fix/cron-command-output-sanitizer`）

## 补丁内容

1. 为 cron `agentTurn` 增加 command-runner prompt 识别。
2. 为 command-runner payload 增加“可信命令输出”筛选：
   - 优先保留 JSON、Markdown 报告、字段化 bullet 输出、Traceback 等原始命令输出。
   - 过滤 `Let's ...`、`Okay, ...`、`Here's the summary ...` 这类模型叙述。
3. 若 command-runner 任务只返回叙述、没有可信命令输出：
   - 不再把这段文本投递到聊天通道。
   - 直接把该次 cron run 标记为 error，错误原因为 `cron command-only job returned non-command text`。

## 回滚方法

1. 回退 `vendor/openclaw-official` 到补丁前提交。
2. 同步移除本次新增的测试文件与 patch 记录。
3. 重新运行：
   - `corepack pnpm exec vitest run src/cron/isolated-agent/helpers.test.ts src/cron/isolated-agent/run.command-only-contract.test.ts`

## 是否建议上游合并

建议。

这是官方 cron `agentTurn` delivery 选择逻辑的通用缺陷，不是本仓业务特例。只要 job prompt 使用“Run command only / 仅用命令执行”这类 contract，就应该在 delivery 前做最终输出鉴别，而不是盲信最后一段模型文本。
