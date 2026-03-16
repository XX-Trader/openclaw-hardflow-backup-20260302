# 2026-03-16 pm-website Telegram + OpenViking 运行修复手册

## 目标

把 `pm-website` 上这轮 Telegram 机器人与 `memory-openviking` 的实际修复动作沉淀为可复用 runbook，供其他 OpenClaw 服务器照此实施。

本文只记录已经在 `pm-website` 实机验证过的动作，不记录推测性方案。

## 适用范围

- OpenClaw Telegram 私聊机器人
- `coordinator` 作为默认聊天 agent
- `memory-openviking` 作为长期记忆插件
- 本地 OpenViking 服务，云端 embedding

## 已验证的稳定基线

### 1. OpenClaw 与运行方式

- OpenClaw CLI / gateway 版本：`v2026.3.13`
- 服务器上只保留 1 套 OpenClaw 安装
- `openclaw-gateway.service` 指向最新版 CLI，不再混跑旧 unit

### 2. Telegram 基线

- 机器人模式：`polling`
- 私聊白名单：`allowFrom = ["1309629117", "1730012345"]`
- 私聊会话隔离：`session.dmScope = "per-channel-peer"`
- 正常运行时关闭 Telegram HTTP 诊断：
  - `diagnostics.enabled = false`
  - `diagnostics.flags = []`

### 3. coordinator 基线

- 默认聊天模型：`kimicode/Doubao-Seed-2.0-Code`
- `agents.defaults.memorySearch.enabled = false`

说明：
- 这台机器最终稳定方案不是依赖 `openai-codex` 作为默认聊天模型。
- `openai-codex` OAuth 曾参与排障，但不属于最终稳定基线的一部分。

### 4. memory-openviking 基线

- 插件启用：`enabled = true`
- 模式：`local`
- OpenViking 配置文件：`~/.openviking/ov.conf`
- 本地服务地址：`http://127.0.0.1:1933`
- `autoRecall = true`
- `autoCapture = true`
- `recallLimit = 4`
- `recallScoreThreshold = 0.55`

### 5. OpenViking 当前实际模型

来自 `~/.openviking/ov.conf`：

- embedding:
  - `provider = openai`
  - `api_base = https://openrouter.ai/api/v1`
  - `model = baai/bge-m3`
  - `dimension = 1024`
- vlm:
  - `provider = openai`
  - `api_base = https://ark.cn-beijing.volces.com/api/coding/v3`
  - `model = Doubao-Seed-2.0-Code`

结论：
- OpenViking 服务进程是本地跑的
- 记忆存储也是本地的
- embedding 与 vlm 都是云端调用，不是本地推理

## 这轮实际改过的内容

### A. 清理错误群目标

目标：
- 清掉错误 Telegram 群目标 `-1003333097130`

实际处理：
- 从活跃 `~/.openclaw/cron/jobs.json` 中删除/禁用该目标
- 从活跃 `~/.openclaw/delivery-queue/{pending,failed,deferred}` 中移除该目标
- 历史档案和备份文件保留，不作为当前运行阻塞项

最终验收标准：
- 活跃配置与活跃投递队列中不再出现 `-1003333097130`

### B. 清理会话与记忆污染

目标：
- 把已损坏的 Telegram slash/direct 会话清掉
- 避免旧脏会话继续卡住新消息

实际处理：
- 清理 `~/.openclaw/agents/coordinator/sessions/sessions.json` 中的坏会话
- 删除缺失 transcript 的 `telegram:slash:*` / `telegram:direct:*` 残留记录
- 重启 `openclaw-gateway.service`

必要时还做过：
- 清空历史会话
- 清空持久化记忆
- 重启 gateway 释放内存中的旧状态

### C. 修复 workspace-coordinator 启动污染

目标：
- 避免普通文本被错误带入 onboarding / bootstrap 流程

实际处理：
- 删除 `~/.openclaw/workspace-coordinator/BOOTSTRAP.md`
- 重写 `~/.openclaw/workspace-coordinator/IDENTITY.md`
- 重写 `~/.openclaw/workspace-coordinator/USER.md`

说明：
- 如果服务器上还保留 `BOOTSTRAP.md`，普通文本可能不直接回答问题，而先进入“我是谁/你是谁”的初始化对话。

### D. 补齐 HardFlow 核心文件

如果 `/new` 回：

- `[HardFlow Guard] required files are missing`

则需要确保 `workspace-coordinator` 内存在：

- `todo.md`
- `done.md`
- `scripts/hardflow/hardflow-v1.lobster.yaml`
- `scripts/hardflow/score-policy.json`
- `scripts/hardflow/check-score-gate.mjs`

否则 `/new` 会被 guard 拦住。

### E. Telegram 私聊会话隔离

在 `~/.openclaw/openclaw.json` 中启用：

```json
{
  "session": {
    "dmScope": "per-channel-peer"
  }
}
```

目的：
- 避免所有私聊共用 `agent:coordinator:main`
- 避免 slash 命令和普通消息互相污染

### F. memory-openviking 关键修复

#### 1. 先修插件可加载性

曾出现过：

- `ParseError: Unterminated string constant`

因此第一步必须先保证：

- `~/.openclaw/extensions/memory-openviking/index.ts` 可正常加载
- gateway 日志中不再出现 `memory-openviking failed to load`

#### 2. 给 autoRecall 增加 fail-fast 超时

最终策略：
- recall 允许继续使用
- 但必须有超时保护，避免拖死整条回复链

实际做法：
- 在 `before_agent_start` 的 autoRecall 主逻辑外面包一层 `withTimeout(...)`
- 超时上限：`5000ms`

目标：
- recall 慢可以跳过
- 但不能把 Telegram 普通文本整条卡死

#### 3. 把召回规模收紧

最终调整：

- `recallLimit = 4`
- `recallScoreThreshold = 0.55`
- 候选检索规模从：
  - `Math.max(cfg.recallLimit * 4, 20)`
- 改为：
  - `Math.max(cfg.recallLimit * 2, 8)`

目的：
- 先缩小候选集合
- 降低后续排序、过滤、读取和 prompt 注入体积

#### 4. 不再逐条读取全文

这轮最重要的性能修改之一：

- 不再对每条命中的 level 2 memory 执行 `client.read(item.uri)` 读取全文
- 改为优先注入 `abstract`
- 并把摘要裁到约 `220` 字符以内

原因：
- 逐条读全文会显著拖慢首轮回复
- 大段全文还会扩大模型上下文，进一步拉高生成延迟

#### 5. autoCapture 保留，但不再叠加 memorySearch

最终基线是：

- `memory-openviking.autoCapture = true`
- `agents.defaults.memorySearch.enabled = false`

原因：
- 只保留一条记忆路径，避免双重记忆链叠加

## 实机验证结果

### 1. 功能验证

已确认的有效状态：

- `/new` 可回复
- `/help` / `/models` 可回复
- 普通文本可进入正常聊天链
- gateway 日志中可见：
  - `memory-openviking: local server started`
  - `memory-openviking: injecting X memories into context`

### 2. 速度验证

以：

```bash
openclaw agent --agent coordinator --message 'Reply with exactly OK'
```

做对照压测：

- 优化前：约 `24.851s`
- 优化后：约 `21.719s`

结论：
- 记忆链负担已经降低
- 但总耗时仍高，说明剩余主瓶颈更偏向模型生成本身，而不是 recall 本身

## 对其他服务器的推荐落地顺序

### 第 1 步：统一 OpenClaw 基线

- 升级到最新稳定 OpenClaw
- 确保服务器上只有 1 套 OpenClaw 安装
- 确保 `openclaw-gateway.service` 指向最新版

### 第 2 步：先修 Telegram 基线

在 `~/.openclaw/openclaw.json` 中确认：

- `channels.telegram.allowFrom`
- `session.dmScope = "per-channel-peer"`
- `diagnostics.enabled = false`
- `diagnostics.flags = []`

并清理：

- 活跃 `cron/jobs.json` 中的错误 chat target
- 活跃 `delivery-queue/*` 中的错误 chat target

### 第 3 步：清理会话污染

如果出现以下现象之一：

- `/new` 正常，普通文本不回
- `/help` 正常，普通文本不回
- 日志反复出现 `stuck session ... state=processing`

则优先：

- 清坏会话
- 清缺失 transcript 的 slash/direct 会话
- 重启 gateway

### 第 4 步：检查 workspace-coordinator

确认：

- 没有 `BOOTSTRAP.md`
- `IDENTITY.md` / `USER.md` 不是错误模板
- HardFlow 核心文件齐全

### 第 5 步：部署 memory-openviking 调优

在 `~/.openclaw/openclaw.json` 中设为：

```json
{
  "plugins": {
    "entries": {
      "memory-openviking": {
        "enabled": true,
        "config": {
          "mode": "local",
          "configPath": "/home/ubuntu/.openviking/ov.conf",
          "targetUri": "viking://user/memories",
          "autoRecall": true,
          "autoCapture": true,
          "recallLimit": 4,
          "recallScoreThreshold": 0.55
        }
      }
    }
  },
  "agents": {
    "defaults": {
      "memorySearch": {
        "enabled": false
      }
    }
  }
}
```

并同步插件逻辑：

- autoRecall 包 `5000ms` 超时
- 候选检索规模收紧
- 只注入短摘要，不读全文

### 第 6 步：最后再看模型层

如果完成以上步骤后仍然慢：

- 优先检查默认聊天模型
- 再决定是否切更快模型

不要先把锅甩给 OpenViking。

## 验收清单

其他服务器照此实施后，至少跑以下检查：

### A. 服务状态

```bash
systemctl --user status openclaw-gateway.service --no-pager
```

### B. 插件与 OpenViking 状态

```bash
journalctl --user -u openclaw-gateway.service --since '10 minutes ago' --no-pager | grep 'memory-openviking:'
```

应至少看到：

- `local server started`
- `injecting`

且不应看到：

- `failed to load`
- `ParseError`

### C. 活跃错误群目标

应确认活跃 `jobs.json` 和活跃 `delivery-queue` 中不再有：

```text
-1003333097130
```

### D. 基础聊天压测

```bash
openclaw agent --agent coordinator --message 'Reply with exactly OK'
```

应返回：

- `OK`

### E. Telegram 实际聊天验证

至少验证：

1. `/new`
2. `/help`
3. `/models`
4. 普通文本：`你好`

## 当前结论

对其他服务器的复用建议不是“照搬所有临时排障动作”，而是：

1. 先落稳定基线
2. 再按故障类型使用对应补救动作
3. 记忆优先保留，但必须配合 fail-fast 与轻量召回

一句话版本：

> `pm-website` 的最终稳定方案不是“关掉记忆”，而是“保留记忆优先，但把 recall 做轻、把坏会话清干净、把 workspace/bootstrap 污染去掉”。 
