---
description: 新增 OpenClaw Agent 的标准化流程（本地文件 + 远程部署 + 配置注册）
---

# 新增 OpenClaw Agent 工作流

// turbo-all

## 前置条件
- SSH 可连通目标服务器（`ssh -F F:/ssh_keys/ssh_config <服务器别名> echo ok`）
- 了解新 Agent 的角色定位、模型选择、调度关系

## 流程

### 1. 规划 Agent 设计
确定以下信息：
- Agent ID（英文小写，如 `explorer`）
- 角色名称（中文，如 `探索者`）
- 主模型（如 `openai-codex/gpt-5.4-mini`、`glmcode/glm-4.7`）
- 可调度的子 Agent 列表
- 哪些 Agent 可以调度它（通常是 coordinator 和 main）

### 2. 创建本地 Agent 目录
在项目的 `agents/` 目录下创建以 Agent ID 命名的子目录，包含 3 个文件：

```
agents/<agent-id>/
├── SOUL.md            # 角色定义（必须）
├── models.json        # 模型配置（必须）
└── auth-profiles.json # 认证配置（必须，通常为空模板）
```

**SOUL.md 必须包含：**
- 角色定位（一句话说清楚做什么）
- 核心职责（3-5 条）
- 执行边界（明确禁止什么）
- 输出规范（格式要求）
- 输出语言：中文（简体，zh-CN）
- UTF-8 基线
- 行为铁律（PUA 引擎三条铁律）
- Score Mission

**models.json 模板**（参考现有 agent 的格式）：
```json
{
  "providers": {
    "<provider-name>": {
      "baseUrl": "<API endpoint>",
      "api": "openai-completions",
      "models": [
        {
          "id": "<model-id>",
          "name": "<Model Name>",
          "reasoning": false,
          "input": ["text"],
          "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
          "contextWindow": 200000,
          "maxTokens": 8192,
          "api": "openai-completions"
        }
      ]
    }
  }
}
```

**auth-profiles.json 模板：**
```json
{
  "version": 1,
  "profiles": {},
  "lastGood": {},
  "usageStats": {}
}
```

### 3. 提交到 Git
```powershell
git add agents/<agent-id>/
git commit -m "feat(agents): 新增 <agent-id> Agent - <一句话描述>"
```

### 4. 部署到远程服务器
通过 Python paramiko 脚本（避免 PowerShell 转义问题）：

1. **上传 agent 文件** → `/root/.openclaw/agents/<agent-id>/`
2. **更新 openclaw.json**（`/root/.openclaw/openclaw/openclaw.json`）：
   - 在 `agents.list` 数组中添加新条目
   - 在 `tools.agentToAgent.allow` 中添加 agent ID
   - 在需要调度它的 agent（如 coordinator、main）的 `subagents.allowAgents` 中添加

**openclaw.json 中的 agent 条目格式：**
```json
{
  "id": "<agent-id>",
  "name": "<角色名称>",
  "workspace": "/home/ubuntu/.openclaw/workspace-<agent-id>",
  "model": "<provider>/<model-id>",
  "subagents": {
    "allowAgents": ["<可调度的子agent>"]
  }
}
```

3. **[可选] 修改其他 agent 的 SOUL.md**，添加与新 agent 的联动协议

### 5. 重启/验证
```powershell
# 检查 OpenClaw 进程
ssh -F F:/ssh_keys/ssh_config <别名> "ps aux | grep openclaw | grep -v grep"

# OpenClaw 通常通过 tmux session 运行
# 如果配置有 watch 模式（skills.load.watch: true），配置变更会自动重载
# 否则需要手动重启：
ssh -F F:/ssh_keys/ssh_config <别名> "tmux send-keys -t openclaw C-c; sleep 2; tmux send-keys -t openclaw 'openclaw gateway --port 18789' Enter"
```

### 6. 验证 Agent 可用
- 方式一：通过 Telegram 发送 `/<agent-id> <任务>` 验证响应
- 方式二：通过 Gateway API 检查 agent 列表

## 模型选择参考

| 定位 | 推荐模型 | 说明 |
|------|---------|------|
| 核心执行（写代码/审核） | `openai-codex/gpt-5.4` | 最强精确执行能力 |
| 辅助调度/文档 | `kimicode/Doubao-Seed-2.0-pro` | 性价比高，质量可靠 |
| 运维/部署/采集 | `glmcode/glm-4.7` | 国产模型，成本最低 |
| 创意/发散/探索 | `openai-codex/gpt-5.4-mini` | 创意能力强，适合梦想家角色 |

## 注意事项
- 部署前务必**备份** openclaw.json（脚本应自动做）
- 新 agent 的 `workspace` 目录会在首次运行时自动创建
- 如果新 agent 有 `agentDir` 需求（自定义 agent 代码），需要额外创建  
  `/home/ubuntu/.openclaw/agents/<agent-id>/agent/` 目录
