# DECISIONS

## 2026-04-27 - 仓库精简采用专门巡检器而不是复用 reviewer

类型：decision
范围：`cron/jobs.json`、`scripts/openclaw-ops/repo_hygiene_reviewer.py`、项目交付流水线
事实：代码精简、冗余文件、失效缓存、冲突残留和测试残留治理由 `repo_hygiene_reviewer.py` 承担定期只读扫描，cron 执行 agent 使用 `optimization-agent`。`reviewer` 仍负责需求、方案和代码审查裁决，不承担长期仓库清理执行。
证据：`cron/jobs.json` 的 `repo_hygiene_reviewer_2d` 每 2 天运行一次；脚本只生成报告和 `repo_hygiene_candidate` 人工确认候选，不自动删除、不自动提交。
最后验证：2026-04-27
复用建议：下次需要“仓库保持整洁”时，先看 repo hygiene 报告和 Task Center 候选；真正删除或重构必须单独进入交付流水线，并通过测试、code reviewer 和 Git 发布门禁。

## 2026-04-27 - Git 发布只能作为通过门禁后的可选阶段

类型：decision
范围：`pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`smart_arb_live_bridge.py`
事实：reviewer 审核通过后不会直接部署或上传 Git；发布阶段必须在 verification、code review、deployment（如有）、acceptance 和 memory writeback 全部通过后执行。`git_publish` 输入必须是已验收变更集：优先使用 `memory_writeback` 隔离工作区 patch，缺失时只回退到 `code_execution` patch，不发布 `command_cwd` 的未验收脏改动。提交说明、备注和变更描述必须使用中文且先脱敏；疑似密钥、远端冲突、认证失败或 push 失败会阻塞到 `fix_git_publish`。
证据：`pipeline_runner.py` 中 `git_publish` 位于 memory writeback 成功之后，并写入 `git_publish_input_patch_report`；`smart_arb_live_bridge.py --stage git_publish` 执行 `git diff --check`、`git diff --cached --check`、staged diff 密钥扫描、脱敏中文 commit message 和普通 `git push <remote> HEAD:<branch>`，不做 force push。
最后验证：2026-04-27
复用建议：如果用户要求“审核完自动上传”，必须确认已经开启 `--git-publish-command`，并检查 `git_publish_report.md`；不要把 `reviewer pass` 误解为已经部署或已 push。
