# OpenClaw Setup/Init 增强说明

本次增强把 `workflow_setup.py` 和 `cron_setup.py` 升级为“先检测、再同步、再审计纠偏”流程。

## 1. 新增能力

1. OpenClaw 安装探测  
脚本：`scripts/openclaw-ops/detect_openclaw_installations.py`  
输出：安装路径、版本、marker 完整性、jobs 数量、推荐目标。

2. OpenClaw ops 文件同步  
脚本：`scripts/openclaw-ops/sync_openclaw_ops_files.py`  
输出：`added/updated/deleted/moved` 清单 + manifest。

3. Cron 任务审计与纠偏  
脚本：`scripts/openclaw-ops/cron_setup.py`  
输出：`audit.before` 与 `audit.after`（`compliant/drifted/missing` 统计）。

4. Workflow 一体化安装  
脚本：`scripts/openclaw-ops/policy/workflow_setup.py`  
流程：探测 OpenClaw -> 选择目标 -> 同步脚本 -> bootstrap -> cron setup（含审计）。

## 2. 常用命令

```bash
# 1) 探测 openclaw 安装
python scripts/openclaw-ops/detect_openclaw_installations.py --emit-json

# 2) 预演同步（不落地）
python scripts/openclaw-ops/sync_openclaw_ops_files.py \
  --source-dir scripts/openclaw-ops \
  --target-ops-dir ~/.openclaw/ops \
  --dry-run \
  --emit-json

# 2.1) 初始化 API 测试配置（避免默认 example.com 噪音）
python scripts/openclaw-ops/init_api_test_config.py \
  --output-file ~/.openclaw/ops/api-test-config.json \
  --base-url http://127.0.0.1:8845 \
  --emit-json

# 2.2) 配置 runtime.env（命令化设置钉钉与其他变量）
python scripts/openclaw-ops/configure_runtime_env.py \
  --env-file ~/.openclaw/ops/runtime.env \
  --dingtalk-webhook-url "<your-webhook>" \
  --dingtalk-secret "<your-secret>" \
  --set OPENCLAW_ENV=prod \
  --emit-json

# 3) 仅执行 cron 审计+纠偏（不落地）
python scripts/openclaw-ops/cron_setup.py \
  --jobs-file ~/.openclaw/cron/jobs.json \
  --channel telegram \
  --to <target> \
  --dry-run \
  --emit-json

# 4) 一体化 setup（可直接落地）
python scripts/openclaw-ops/policy/workflow_setup.py init \
  --openclaw-home ~/.openclaw \
  --scan-root . \
  --install-cron-setup \
  --cron-channel telegram \
  --cron-to <target> \
  --emit-json

# 5) 校验 jobs payload 里的脚本路径是否存在
python scripts/openclaw-ops/verify_job_payload_paths.py \
  --jobs-file ~/.openclaw/cron/jobs.json \
  --strict \
  --emit-json
```

## 3. workflow_setup 新参数

- `--skip-openclaw-detect`
- `--openclaw-detect-scan-root`
- `--openclaw-detect-max-depth`
- `--openclaw-detect-max-results`
- `--skip-ops-sync`
- `--sync-source-dir`
- `--sync-manifest-file`
- `--sync-keep-stale-files`
- `--allow-nonstandard-sync-source`
- `--skip-init-api-test-config`
- `--api-test-config-file`
- `--api-test-base-url`
- `--configure-runtime-env`
- `--runtime-env-file`
- `--dingtalk-webhook-url`
- `--dingtalk-secret`
- `--set-runtime-env`
- `--skip-job-path-verify`
- `--skip-memory-restore`
- `--memory-restore-check-only`
- `--memory-source-dirname`
- `--memory-workspace`
- `--disable-memory-legacy-source`

## 4. 关键输出字段

- `openclaw_selection`: 目标选择来源（`cli-arg` / `interactive-select` / `detected-recommended` / `default`）
- `openclaw_detection`: 探测结果原始结构
- `ops_sync`: 文件同步结果（含新增、删除、移动）
- `install_cron_setup.detail.audit`: cron 审计前后对比

## 5. Memory Restore（2026-03-03）

- `workflow_setup.py` 现在默认执行项目记忆恢复（copy 模式）。
- 默认源目录：`<project>/openclaw-memory/`。
- 兼容旧目录：`<project>/.workflow/openclaw-memory/`（可通过 `--disable-memory-legacy-source` 关闭）。
- setup 输出新增 `memory_restore` 字段：
  - `warning_projects > 0` 代表存在“项目未同步记忆源目录”等待补齐。
