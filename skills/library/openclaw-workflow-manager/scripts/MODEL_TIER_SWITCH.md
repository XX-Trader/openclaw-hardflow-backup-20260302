# Model Tier Switch

一个命令切换模型档位，并同步以下文件：

- `openclaw/openclaw.json`
- `agents/agent_index.json`
- `agents/agent_index.md`
- `scripts/openclaw-ops/policy/policy-config.json`
- `scripts/hardflow/hardflow-run.sh`

每次切换会自动备份：

- 文件备份目录：`.tmp/model-switch-backups/<timestamp>_<tier>/`
- 档位快照目录：`.tmp/model-switch-profiles/`

## Usage

```bash
# 查看可用档位
python scripts/openclaw-ops/switch_model_tier.py --list-tiers

# 一键切换（支持档位关键字）
python scripts/openclaw-ops/switch_model_tier.py 顶级
python scripts/openclaw-ops/switch_model_tier.py 高级
python scripts/openclaw-ops/switch_model_tier.py high_doubao

# 一句话切换（脚本会自动识别）
python scripts/openclaw-ops/switch_model_tier.py "切换顶级模型"
python scripts/openclaw-ops/switch_model_tier.py "切换高级模型"
python scripts/openclaw-ops/switch_gpt54_layer_to_doubao.sh

# 仅预览，不写入
python scripts/openclaw-ops/switch_model_tier.py 顶级 --dry-run
```

Windows 也可直接使用：

```powershell
.\scripts\openclaw-ops\switch_model_tier.ps1 顶级
.\scripts\openclaw-ops\switch_model_tier.ps1 高级
.\scripts\openclaw-ops\switch_gpt54_layer_to_doubao.ps1
```

## Tier Rules

- 顶级：`openai-codex/gpt-5.5`
  - 回退：`openai-codex/gpt-5.4`, `openai-codex/gpt-5.3-codex`, `glmcode/glm-5`, `glmcode/glm-4.7`
  - thinkingDefault：`high`
  - Codex 模型默认 `xhigh`；非 Codex 模型默认 `high`
- 高级：`openai-codex/gpt-5.5`
  - 回退：`openai-codex/gpt-5.4`, `openai-codex/gpt-5.3-codex`, `glmcode/glm-5`, `glmcode/glm-4.7`
  - owner 覆盖：`coordinator/project-agent/web-agent/reviewer/backend-dev/frontend-dev/tester/deployer/doc-writer/ops-agent/optimization-agent -> gpt-5.5`
  - thinkingDefault：`high`
  - Codex 模型默认 `xhigh`；非 Codex 模型默认 `high`
- 高级豆包版：`kimicode/doubao-seed-2.0-pro`
  - 回退：`openai-codex/gpt-5.5`, `openai-codex/gpt-5.4`, `glmcode/glm-5`, `glmcode/glm-4.7`
  - owner 覆盖：只替换讨论/审查层，`coordinator/reviewer -> doubao-seed-2.0-pro`；项目、Web、编码、测试、部署、文档、运维和仓库精简 owner 保持 `gpt-5.5`
  - 入口：`switch_model_tier.py high_doubao` 或 `switch_gpt54_layer_to_doubao.{sh|ps1}`
  - thinkingDefault：`high`
  - Codex 模型默认 `xhigh`；非 Codex 模型默认 `high`
- 中级：`glmcode/glm-5`
  - 回退：`glmcode/glm-4.7`
  - thinkingDefault：`high`
  - Codex 模型默认 `xhigh`；非 Codex 模型默认 `high`
- 低级：`glmcode/glm-4.7`
  - 回退：无
  - thinkingDefault：`high`
  - Codex 模型默认 `xhigh`；非 Codex 模型默认 `high`
