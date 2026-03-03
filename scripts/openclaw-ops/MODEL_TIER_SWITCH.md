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

# 一句话切换（脚本会自动识别）
python scripts/openclaw-ops/switch_model_tier.py "切换顶级模型"
python scripts/openclaw-ops/switch_model_tier.py "切换高级模型"

# 仅预览，不写入
python scripts/openclaw-ops/switch_model_tier.py 顶级 --dry-run
```

Windows 也可直接使用：

```powershell
.\scripts\openclaw-ops\switch_model_tier.ps1 顶级
.\scripts\openclaw-ops\switch_model_tier.ps1 高级
```

## Tier Rules

- 顶级：`openai-codex/gpt-5.3-codex`
  - 回退：`kimicode/Doubao-Seed-2.0-Code`, `glmcode/glm-5`, `glmcode/glm-4.7`
  - thinkingDefault：`xhigh`
- 高级：`kimicode/Doubao-Seed-2.0-Code`
  - 回退：`glmcode/glm-5`, `glmcode/glm-4.7`, `openai-codex/gpt-5.3-codex-spark`
  - agent 覆盖：`reviewer -> openai-codex/gpt-5.3-codex`，`optimization-agent -> openai-codex/gpt-5.3-codex`
  - thinkingDefault：`high`
- 中级：`glmcode/glm-5`
  - 回退：`glmcode/glm-4.7`
  - thinkingDefault：`medium`
- 低级：`glmcode/glm-4.7`
  - 回退：无
  - thinkingDefault：`low`
