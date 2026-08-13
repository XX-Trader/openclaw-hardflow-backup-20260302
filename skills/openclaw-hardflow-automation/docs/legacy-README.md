# HardFlow Core（默认编码工作流底座）

HardFlow Core 是 OpenClaw 工作流体系的共享流程内核，不再只表示“一个很强的编码脚本链”。
从 2026-03-22 起，推荐统一口径：

- 平台总流程：`需求输入 -> 澄清 -> 拆分 -> 选择 workflow -> 进入执行闭环`
- `HardFlow Core`
  - 负责阶段编排、G0-G6 评分门禁、验收、完成前验证、证据落盘、回流整改
- `coding-default`
  - 唯一默认 workflow profile
- `hardflow-run.sh workflow`
  - 当前等价于 `coding-default@stable` 的主入口

未来新增其他 workflow profile 时，必须复用同一套 HardFlow Core，而不是复制一套平行的 runner 链。

## 1. 硬约束

1. 每个 Gate 独立评分，不能用总分掩盖低分。
2. 任何 Gate 不通过，必须回流整改并重评分。
3. Security Gate（G4）启用一票否决（高危未闭环直接失败）。
4. 接口变更必须同步 API 文档，否则阻断。
5. reviewer + tester + score gates 通过后，才允许部署/推送。
6. 没有当前 run 的完成前验证产物，不允许执行 `git-push`。
7. 部署后验收测试必须生成当前 run 的统一验收产物，否则不能进入完成前验证。
8. 自我进化只能先改 candidate，不能直接覆盖默认 stable。
9. workflow 绑定 capability，不直接把 skill 当作流程真值。

## 2. Gate 列表与阈值

1. `G0 requirements`：`>=93`
2. `G1 solution`：`>=92`
3. `G2 frontend`：`>=92`
4. `G3 backend`：`>=93`
5. `G4 security`：`>=95` + veto
6. `G5 release`：`>=92`
7. `G6 final`：`>=93`

策略文件：`scripts/hardflow/score-policy.json`

## 3. Core 与 Profile 的关系

| 层 | 负责什么 |
| --- | --- |
| `HardFlow Core` | 阶段机、Gate、验收、完成前验证、评分、证据 |
| `coding-default` | 默认编码工作流的阶段图与能力绑定 |
| `skill` | capability 的实现说明 |
| `hook` | 运行时护栏与审计 |

一句话理解：

`HardFlow 负责怎么管流程，coding-default 负责默认跑哪条流程。`

## 4. 关键文件

1. `hardflow-run.sh`：主执行器（含测试回流、评分回流、部署回滚、上下文重置、git 存档点回滚）。
2. `check-score-gate.mjs`：单 Gate 评分校验器。
3. `SCORECARD_SCHEMA.md`：评分输入格式约束。
4. `check-api-doc-gate.sh`：接口文档门禁。
5. `check-review-test-gate.sh`：部署前/后综合门禁。
6. `check-deployment-acceptance.sh`：部署后验收测试门禁。
7. `check-completion-verification.sh`：完成前验证门禁。
8. `hardflow-v1.lobster.yaml`：Lobster 工作流。
9. `hardflow-tmux-runner.sh`：tmux 常驻执行入口。
10. `atomic_task_guard.py`：保证 `.workflow/task.json` 为原子化细粒度任务（最少 4 个可执行子任务）。

## 5. 主流程入口

正式主流程入口：

```bash
bash scripts/hardflow/hardflow-run.sh workflow --task "实现XX需求" --max-retries 3 --score-max-retries 3
```

当前推荐把这条命令理解成：

`coding-default@stable` 的默认执行入口

注意：

- 这不是整个平台接到需求后的第一步
- 正确顺序是先做需求澄清和任务拆分
- 当任务被识别为编码类任务后，再进入这条默认执行入口

这条命令会按固定顺序执行：

1. classify
2. `G0 requirements`
3. dispatch
4. `G1 solution`
5. implement
6. test-loop
7. review
8. `G2 frontend`
9. `G3 backend`
10. `G4 security`
11. API doc gate
12. predeploy quality gate
13. preview deploy
14. deploy
15. post-test
16. `G5 release`
17. `G6 final`
18. postdeploy quality gate
19. acceptance-test
20. verify-completion
21. preview git-push
22. git-push
23. score-report

说明：

1. `workflow` 现在是 direct 模式下的正式统一入口。
2. `hardflow-tmux-runner.sh` 的 direct 模式已改为调用这条主流程命令。
3. `hardflow-v1.lobster.yaml` 仍保留显式分步编排，作为 Lobster 模式入口。
4. `post-test` 失败现在会直接中断 workflow，不再继续进入 `G5 release` / `G6 final`。
5. `git-push` 现在显式依赖 `verify-completion` 产物，缺失或过期都会阻断推送。
6. `verify-completion` 现在显式依赖 `acceptance-test` 产物，缺失或失败都会阻断完成。
7. 未来若新增其他 workflow profile，应通过 profile/manifest 切换，而不是改写 HardFlow Core 本身。

### 安全演练模式

如果目标是验证 `G0-G6 + acceptance-test + verify-completion` 链路本身，而不是执行真实部署或外部提交，可以在运行前覆盖以下命令：

1. `DISPATCH_CMD`
2. `IMPLEMENT_CMD`
3. `TEST_CMD`
4. `REVIEW_CMD`
5. `DEPLOY_CMD`
6. `POST_TEST_CMD`
7. `ROLLBACK_CMD`
8. `SCORE_*_CMD`

推荐做法：

1. 业务阶段命令改为本地 no-op 命令
2. `SCORE_*_CMD` 生成满足 `score-policy.json` 的标准 scorecard
3. 仍然执行真实的：
   - `check-api-doc-gate.sh`
   - `check-review-test-gate.sh`
   - `acceptance-test`
   - `verify-completion`

这样可以在不触发外部提交的前提下，验证完整门禁链路是否可运行。

## 6. 部署后验收测试约定

正式阶段入口：

```bash
bash scripts/hardflow/hardflow-run.sh acceptance-test
```

默认必检项：

1. `openclaw gateway status`
2. `openclaw status`
3. `openclaw plugins list`
4. `openclaw hooks check --json`
5. `openclaw cron status --json`
6. `python skills/library/openclaw-workflow-manager/scripts/check_openviking_stack.py --workspace-root .`

运行说明：

1. `check-deployment-acceptance.sh` 会自动优先使用 `python3`，不存在时回退到 `python`。
2. `check_openviking_stack.py` 会优先从运行时 `openclaw.json` 的 `memory-openviking` 配置推导健康检查地址，兼容 Windows 本机这类非默认端口场景。

可选补充项：

1. `DEPLOY_ACCEPT_OPENVIKING_CMD`
2. `DEPLOY_ACCEPT_OPENVIKING_HEALTH_URL`
3. `DEPLOY_ACCEPT_TELEGRAM_CMD`
4. `DEPLOY_ACCEPT_FEISHU_CMD`

产物：

1. `.workflow/runs/<run_id>/acceptance/deployment.json`
2. `.workflow/gates/deployment_acceptance.json`

## 7. 评分命令约定

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

## 8. 分步调试示例

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
bash scripts/hardflow/hardflow-run.sh acceptance-test
bash scripts/hardflow/hardflow-run.sh verify-completion
bash scripts/hardflow/hardflow-run.sh git-push
bash scripts/hardflow/hardflow-run.sh score-report --format text
```

## 9. Lobster 运行

```json
{
  "action": "run",
  "pipeline": "/absolute/path/to/scripts/hardflow/hardflow-v1.lobster.yaml",
  "argsJson": "{\"task\":\"实现XX需求\",\"max_retries\":\"3\",\"score_max_retries\":\"3\"}",
  "timeoutMs": 180000
}
```

## 10. 产物目录

1. `.workflow/runs/<run_id>/timeline.log`
2. `.workflow/runs/<run_id>/issues.ndjson`
3. `.workflow/runs/<run_id>/scorecards/*.json`
4. `.workflow/runs/<run_id>/score-gate-audit.ndjson`
5. `.workflow/runs/<run_id>/acceptance/deployment.json`
6. `.workflow/gates/*.json`
7. `.workflow/runs/<run_id>/verification/completion.json`
8. `.workflow/hook-audit/commands.log`
9. `.workflow/task.json`
10. `.workflow/progress.txt`

## 11. 进化与晋升说明

当前阶段建议把默认编码工作流的自我进化统一成：

- `coding-default@stable`
- `coding-default@candidate`

upgrade feedback、workflow scorecard、skill review 的最终目标，不只是输出报告，而是支撑：

1. candidate 重跑
2. stable/candidate 对比
3. 晋升或回滚

在这套机制成熟前，不建议让自我进化直接覆盖默认稳定流。

## 12. 记忆说明

当前工作流已把记忆链路标准化成两种明确模式，而不是混合表述：

1. 官方默认模式：`memory-core`
2. 增强记忆模式：`OpenViking + memory-openviking`

标准三层：

1. 服务层：`OpenViking`
2. 插件层：`memory-openviking`
3. 路由层：`plugins.allow` + `plugins.slots.memory`

运行说明：

1. 仓库基线 `openclaw/openclaw.json` 显式保留 `plugins.slots.memory = "memory-core"` 作为默认基线。
2. 运行时切到增强记忆模式时，必须同时满足：
   - `plugins.slots.memory = "memory-openviking"`
   - `memory-openviking` 插件层通过
   - `OpenViking` 服务层健康检查通过
3. `check_openviking_stack.py` 会优先读取运行时 `memory-openviking.config.port` / `healthUrl` / `baseUrl`，再回退到环境变量和默认端口。
