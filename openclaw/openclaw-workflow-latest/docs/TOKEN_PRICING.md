# Token 费用配置说明

## 统一维护位置
- 单价文件：`/home/ubuntu/.openclaw/ops/task-center/token-pricing.json`
- 模型来源：`/home/ubuntu/.openclaw/openclaw.json`（`models.providers.*.models[].id`）
- 管理脚本：`/home/ubuntu/.openclaw/ops/token_pricing_manager.py`

## 目录可配置（不写死）
- `OPENCLAW_HOME`：OpenClaw 根目录（默认 `$HOME/.openclaw`）
- `OPENCLAW_OPS_DIR`：ops 目录（默认 `$OPENCLAW_HOME/ops`）
- `OPENCLAW_CONFIG_PATH`：主配置文件（默认 `$OPENCLAW_HOME/openclaw.json`）
- `OPENCLAW_TASK_CENTER_ROOT`：任务中心目录（默认 `$OPENCLAW_OPS_DIR/task-center`）

示例（临时会话生效）：
```bash
export OPENCLAW_HOME=/data/openclaw
export OPENCLAW_OPS_DIR=/data/openclaw/ops
export OPENCLAW_CONFIG_PATH=/data/openclaw/openclaw.json
export OPENCLAW_TASK_CENTER_ROOT=/data/openclaw/ops/task-center
```

## 目标
- 不把模型写死在代码里。
- 后续新增模型后，自动同步到单价文件，再手动补单价。

## 常用命令
- 查看当前单价配置：
```bash
python3 /home/ubuntu/.openclaw/ops/token_pricing_manager.py show
```

- 同步 openclaw 模型到单价表（新增模型会自动补 0 单价）：
```bash
python3 /home/ubuntu/.openclaw/ops/token_pricing_manager.py sync-models
```

- 查看“模型是否已配置单价”：
```bash
python3 /home/ubuntu/.openclaw/ops/token_pricing_manager.py list-models
```

- 设置某个模型单价（单位：每 1M token）：
```bash
python3 /home/ubuntu/.openclaw/ops/token_pricing_manager.py set \
  --model glmcode/glm-5 \
  --input-per-m 0.80 \
  --output-per-m 2.40
```

- 设置默认单价（新模型未配置时会兜底）：
```bash
python3 /home/ubuntu/.openclaw/ops/token_pricing_manager.py set-default \
  --input-per-m 0.50 \
  --output-per-m 1.50
```

## 推荐流程（新增模型时）
1. 先在 `openclaw.json` 增加模型配置。
2. 执行 `sync-models`。
3. 对新模型执行 `set --model ...` 补单价。
4. 运行日报/汇总流水线，验证成本估算是否更新。
