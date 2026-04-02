# Runtime Skills

这套 workflow 现在把“运行时必须补齐的外部技能/二进制”单独收敛到一个 manifest：

- 清单文件：`scripts/openclaw-ops/runtime-required-skills.json`
- 执行脚本：`scripts/openclaw-ops/ensure_runtime_skills.py`

## 当前已记录的运行时依赖

- `frontend-design-ultimate`
  - 来源：`kesslerio/ultimate-frontend-design-openclaw-skill`
  - 安装位置：`~/.openclaw/skills/` 与 `~/.openclaw/workspace/skills/`
  - 冲突替换：如果发现旧的 `frontend-design`，会先移除
- `summarize`
  - 不是额外 skill 文件，而是内置 `summarize` skill 依赖的 CLI
  - npm 包：`@steipete/summarize`

## 已接入的工作流入口

- `python scripts/openclaw-ops/install_workflow_profile.py`
  - 默认执行 `ensure_runtime_skills`
  - 可用 `--no-ensure-runtime-skills` 跳过
- `python scripts/openclaw-ops/policy/workflow_setup.py init`
  - 默认执行 `ensure_runtime_skills`
  - 可用 `--skip-runtime-skill-ensure` 跳过

## 常用命令

```bash
# 只检查/预演，不落地
python scripts/openclaw-ops/ensure_runtime_skills.py \
  --openclaw-home ~/.openclaw \
  --dry-run \
  --emit-json

# 实际补齐
python scripts/openclaw-ops/ensure_runtime_skills.py \
  --openclaw-home ~/.openclaw \
  --emit-json
```

## 后续新增技能怎么做

1. 在 `runtime-required-skills.json` 里补一条 skill 或 command 记录。
2. 如果是 skill，优先写清楚：
   - `name`
   - `conflicts`
   - `install.targets`
   - `install.repo_url` / `install.archive_url`
3. 如果是 CLI 依赖，写清楚：
   - `name`
   - `install.command`
   - `install.npm_package`
   - `install.verify_args`
4. 运行：

```bash
python -m unittest \
  tests.scripts_openclaw_ops.test_ensure_runtime_skills \
  tests.scripts_openclaw_ops.test_cron_quiet_modes
```
