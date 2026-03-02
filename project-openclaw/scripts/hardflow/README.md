# HardFlow v2（完整版高分门禁）

HardFlow v2 是基于 `tmux + Codex CLI + Lobster + Hooks` 的多角色自动化流程，采用 G0-G6 独立评分门禁。

## 1. 硬约束

1. 每个 Gate 独立评分，不能用总分掩盖低分。
2. 任何 Gate 不通过，必须回流整改并重评分。
3. Security Gate（G4）启用一票否决（高危未闭环直接失败）。
4. 接口变更必须同步 API 文档，否则阻断。
5. reviewer + tester + score gates 通过后，才允许部署/推送。

## 2. Gate 列表与阈值

1. `G0 requirements`：`>=93`
2. `G1 solution`：`>=92`
3. `G2 frontend`：`>=92`
4. `G3 backend`：`>=93`
5. `G4 security`：`>=95` + veto
6. `G5 release`：`>=92`
7. `G6 final`：`>=93`

策略文件：`scripts/hardflow/score-policy.json`

## 3. 关键文件

1. `hardflow-run.sh`：主执行器（含测试回流、评分回流、部署回滚）。
2. `check-score-gate.mjs`：单 Gate 评分校验器。
3. `SCORECARD_SCHEMA.md`：评分输入格式约束。
4. `check-api-doc-gate.sh`：接口文档门禁。
5. `check-review-test-gate.sh`：部署前/后综合门禁。
6. `hardflow-v1.lobster.yaml`：Lobster 工作流。
7. `hardflow-tmux-runner.sh`：tmux 常驻执行入口。

## 4. 评分命令约定

每个 Gate 支持两类命令：

1. 评分命令（必须产出 scorecard）
2. 改进命令（低分时回流整改）

环境变量：

1. `SCORE_REQUIREMENTS_CMD`
2. `SCORE_SOLUTION_CMD`
3. `SCORE_FRONTEND_CMD`
4. `SCORE_BACKEND_CMD`
5. `SCORE_SECURITY_CMD`
6. `SCORE_RELEASE_CMD`
7. `SCORE_FINAL_CMD`
8. `IMPROVE_REQUIREMENTS_CMD`
9. `IMPROVE_SOLUTION_CMD`
10. `IMPROVE_FRONTEND_CMD`
11. `IMPROVE_BACKEND_CMD`
12. `IMPROVE_SECURITY_CMD`
13. `IMPROVE_RELEASE_CMD`
14. `IMPROVE_FINAL_CMD`
15. `SCORE_MAX_RETRIES`（默认 3）

评分命令可读取 `SCORECARD_FILE` 环境变量，把 JSON 写入该路径。

### 推荐配置方式（服务器）

1. 复制模板：`cp scripts/hardflow/hardflow.env.example ~/.openclaw/hardflow/hardflow.env`
2. 编辑命令：`vi ~/.openclaw/hardflow/hardflow.env`
3. 权限收敛：`chmod 600 ~/.openclaw/hardflow/hardflow.env`

`hardflow-run.sh` 会在每次执行时自动按以下顺序查找配置：
1. `HARDFLOW_ENV_FILE`（显式指定）
2. `~/.openclaw/hardflow/hardflow.env`
3. `~/.claude/hardflow/hardflow.env`
4. `<repo>/.workflow/hardflow.env`

## 5. 直跑示例

```bash
bash scripts/hardflow/hardflow-run.sh classify --task "实现XX需求"
bash scripts/hardflow/hardflow-run.sh score-gate --gate requirements --max-retries 3
bash scripts/hardflow/hardflow-run.sh dispatch
bash scripts/hardflow/hardflow-run.sh score-gate --gate solution --max-retries 3
bash scripts/hardflow/hardflow-run.sh implement
bash scripts/hardflow/hardflow-run.sh test-loop --max-retries 3
bash scripts/hardflow/hardflow-run.sh review
bash scripts/hardflow/hardflow-run.sh score-gate --gate frontend --max-retries 3
bash scripts/hardflow/hardflow-run.sh score-gate --gate backend --max-retries 3
bash scripts/hardflow/hardflow-run.sh score-gate --gate security --max-retries 3
bash scripts/hardflow/check-api-doc-gate.sh
bash scripts/hardflow/check-review-test-gate.sh --stage predeploy
bash scripts/hardflow/hardflow-run.sh deploy
bash scripts/hardflow/hardflow-run.sh post-test || true
bash scripts/hardflow/hardflow-run.sh score-gate --gate release --max-retries 3
bash scripts/hardflow/hardflow-run.sh score-gate --gate final --max-retries 3
bash scripts/hardflow/check-review-test-gate.sh --stage postdeploy
bash scripts/hardflow/hardflow-run.sh git-push
bash scripts/hardflow/hardflow-run.sh score-report --format text
```

## 6. Lobster 运行

```json
{
  "action": "run",
  "pipeline": "/absolute/path/to/scripts/hardflow/hardflow-v1.lobster.yaml",
  "argsJson": "{\"task\":\"实现XX需求\",\"max_retries\":\"3\",\"score_max_retries\":\"3\"}",
  "timeoutMs": 180000
}
```

## 7. 产物目录

1. `.workflow/runs/<run_id>/timeline.log`
2. `.workflow/runs/<run_id>/issues.ndjson`
3. `.workflow/runs/<run_id>/scorecards/*.json`
4. `.workflow/runs/<run_id>/score-gate-audit.ndjson`
5. `.workflow/gates/*.json`
6. `.workflow/hook-audit/commands.log`

## 8. 经验进化维护（新增）

1. 主文档：`scripts/hardflow/EXPERIENCE_EVOLUTION.md`
2. 维护脚本：`scripts/hardflow/experience-maintain.mjs`
3. cron 运行器：`scripts/hardflow/experience-maintain-cron.sh`
4. 自测：`node --experimental-strip-types scripts/hardflow/hook-selftest.mjs --hooks-dir .claude/hardflow/hooks --workspace .workflow/tmp-hook-selftest`
