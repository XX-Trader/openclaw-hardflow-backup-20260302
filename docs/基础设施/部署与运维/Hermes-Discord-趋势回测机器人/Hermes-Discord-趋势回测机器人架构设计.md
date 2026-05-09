# Hermes Discord 趋势回测机器人架构设计

> 最后更新：2026-05-08

## 1. 问题定义

当前本机已经存在一个运行在 WSL Ubuntu 中的主 `Hermes Agent`，其配置、记忆和消息通道已承载其他用途。

这次新增的 `趋势回测机器人` 有三个核心要求：

1. 单独的 Discord bot 接入
2. 单独的模型配置
3. 大群 / 小群采用不同的 mention 规则

如果把这套配置直接塞进当前主 profile，会出现三个问题：

- 频道规则互相污染
- 回测会话和其他业务会话混在一起
- 后续升级、排障和回滚难以收敛

因此本次方案采用**独立 profile + 独立 gateway 配置 + 实时 guild/channel 探测**。

## 2. 总体架构

```text
Windows PowerShell
    └── wsl.exe -d Ubuntu
            └── Hermes Agent（trend-backtest profile）
                    ├── profile 独立配置
                    ├── 独立 memories / sessions
                    ├── Discord bot token（运行时密钥）
                    ├── GitHub PAT（运行时密钥）
                    ├── Linux 工作副本（/home/ubuntu/projects/SmartTrendTracker）
                    ├── Profile 级自动执行（approvals.mode='off'）
                    ├── delegation 并行子 agent（max_concurrent_children=3）
                    ├── 模型配置（默认 openai-codex/gpt-5.5，xhigh）
                    ├── 主回退链（kimi-coding/kimi-k2.6 -> zai/glm-5.1）
                    ├── 辅助任务路由（默认 zai/glm-4.7，重要任务 zai/glm-5.1）
                    └── gateway run
                            └── Discord guild / channel
                                    ├── 大群：require mention
                                    └── 小群：free response
```

## 3. 配置分层

### 3.1 Profile 层

- profile 名称：`trend-backtest`
- 对外显示名：`趋势回测机器人`
- SOUL 定位：`趋势回测专职研究员 / 本地多核回测执行官`
- 与主 profile 隔离：
  - `config.yaml`
  - `.env`
  - `sessions`
  - `memories`
  - gateway 状态文件
  - `start-gateway.sh`

该 profile 的 persona 已显式收口为“只负责趋势回测”。这一步是必要的，因为 Hermes 新建 profile 默认是通用助手口径，如果不改 `SOUL.md`，后续在 Discord 中很容易再次漂移回“泛聊天 + 泛建议”模式。

### 3.2 模型层

当前本机落地结果：

- 主 provider：`openai-codex`
- 主 model：`gpt-5.5`
- 主思考强度：`agent.reasoning_effort=xhigh`
- 主 fallback：`kimi-coding/kimi-k2.6 -> zai/glm-5.1`
- 子 agent delegation：`openai-codex/gpt-5.5`，`delegation.reasoning_effort=xhigh`
- 文本辅助任务默认：`zai/glm-4.7`
- 重要辅助任务：`compression` / `curator` 使用 `zai/glm-5.1`

这样做的原因是：

- 主聊天继续优先保证回测讨论质量
- 主回退使用高质量模型兜底，不把 `glm-4.7` 放进主回退链
- 辅助任务多数是标题、搜索摘要、审批判断、MCP/web extract 等短任务，默认使用更快的 `glm-4.7`
- 压缩和记忆整理会影响长期上下文质量，因此使用 `glm-5.1`
- 旧 `auxiliary.provider=auto` 曾在 compression/title 链路中 fallback 到 OpenRouter；显式配置文本辅助任务可以避免聊天记录再出现这类 OpenRouter 辅助路由

注意：Kimi/Moonshot 直连 key 已按 profile 运行时变量补齐；`config check` 已验证 OpenRouter unset、Z.AI/GLM configured、Kimi/Moonshot configured。`kimi-coding/kimi-k2.6` 与 `zai/glm-5.1` 作为主回退链并行可用。

### 3.3 工作目录层

- 默认工作仓库：`/home/ubuntu/projects/SmartTrendTracker`
- Windows 共享副本：`/mnt/h/GitHub/SmartTrendTracker`
- 启动入口：`/home/ubuntu/.hermes/profiles/trend-backtest/start-gateway.sh`
- profile 配置：`config.yaml -> terminal.cwd=/home/ubuntu/projects/SmartTrendTracker`
- 审批策略：`config.yaml -> approvals.mode='off'`
- delegation 策略：`config.yaml -> delegation.default_toolsets + max_concurrent_children`

设计裁决：

1. **Linux 仓库是回测主目录**
   回测通常包含 Git、pytest、SQLite、日志、缓存和批量文件 I/O，这些操作不应默认落在 `/mnt/h` 的 9p 挂载上。

2. **Windows 副本只作为共享入口**
   `/mnt/h/GitHub/SmartTrendTracker` 保留给 Windows 侧查看、编辑和共享，但不作为 `trend-backtest` 默认执行目录。

3. **通过本地 HERMES.md 覆盖项目 AGENTS**
   该项目根目录已有与 `trend-backtest` 不一致的 `AGENTS.md`。因此在 Linux 工作副本根目录新增本地 `HERMES.md`，避免回测机器人误吃新闻分析 Agent 设定。

4. **工作目录配置使用 `terminal.cwd`**
   `TERMINAL_CWD` 环境变量口径已进入废弃路径，因此当前以 `trend-backtest/config.yaml` 中的 `terminal.cwd` 作为正式配置源。

5. **自动执行使用 profile 级 approvals.mode**
   `trend-backtest` 是独立 Hermes profile，拥有自己的 `config.yaml`。因此最稳妥的做法是仅在该 profile 内设置 `approvals.mode='off'`，而不是靠进程级 `HERMES_YOLO_MODE` 旁路。

6. **并行子 agent 显式固定上限**
   Hermes 原生支持 `delegate_task` 并发子 agent。当前对 `trend-backtest` 明确固定 `delegation.max_concurrent_children=3`，既满足并行拆任务，又避免本机回测环境被无限制放大并发压垮。

### 3.4 Discord 路由层

规则按真实 guild / channel 精确配置：

- **大群**：
  - 默认静默
  - 只有明确 `@趋势回测机器人` 才响应
- **小群**：
  - 允许直接对话
  - 不要求 `@`

这里不能靠“群名猜测”，必须通过 Discord API 拉取真实 guild / channel 列表后再配置。

当前已确认的真实拓扑：

- guild：`智能趋势跟踪` (`1492491333653368894`)
- 大群文本频道：
  - `1492491334144098407` `趋势策略监控`
  - `1493156322495955035` `新闻分析测试`
  - `1493156430285635715` `趋势策略测试`
  - `1494221314922250352` `因子分析`
- 小群 free-response 频道：
  - `1495659215598125217` `趋势回测测试`

当前规则落地方式：

- `discord.require_mention: true`
- `DISCORD_FREE_RESPONSE_CHANNELS=1495659215598125217`
- `DISCORD_ALLOW_ALL_USERS=true`

## 4. 安全与密钥

### 4.1 密钥落点

Discord token 只能放在：

- WSL 中 `trend-backtest` 对应 profile 的运行时环境

GitHub PAT 也只能放在：

- WSL 中 `trend-backtest` 对应 profile 的运行时环境
- 由仓库级 `credential.helper` 在需要访问 `SmartTrendTracker` 时按需读取

不能放在：

- 仓库文档
- 仓库配置文件
- 任何会进入 Git 的文件

### 4.2 日志与脱敏

执行过程中：

- 输出中禁止回显完整 token
- 文档和总结中只记录“已写入 Discord token”，不记录明文
- 文档和总结中只记录“已写入 GitHub PAT”，不记录明文

## 5. 影响面分析

### 5.1 直接影响

- WSL 中的 Hermes profile 目录
- Hermes 运行时配置
- Discord guild / channel 访问范围
- Linux 工作副本与启动脚本
- `trend-backtest` 的审批行为

### 5.2 间接影响

- 本机 WSL 中可能新增一个独立 gateway 运行实例
- 后续趋势回测策略 prompt、技能、记忆会默认挂到该 profile 下
- `trend-backtest` 的默认上下文文件将来自 Linux 工作副本根目录的 `HERMES.md`
- `trend-backtest` 将绕过命令审批弹窗，适合本地回测/研究，但也意味着该 profile 的危险命令保护已被显式关闭
- `trend-backtest` 默认允许在独立任务上调用 `delegate_task` 并发拆分最多 3 个子 agent

## 6. 失败回滚策略

若本次配置失败：

1. 保留主 Hermes profile 不变
2. 删除或停用 `trend-backtest` profile
3. 不修改主 profile 的 Telegram / Feishu 配置
4. 只回滚新增 profile 的 Discord / 模型配置

## 7. 验证点

1. `Hermes Agent` 已成功升级到 `v0.10.0`
2. `trend-backtest` profile 已创建成功
3. Discord token 已在独立 profile 生效
4. Linux 工作副本已成功克隆并能访问 GitHub 远端
5. bot 已能读到目标 guild / channel
6. Hermes gateway 已成功连上 Discord 并同步 Slash Commands
7. Hermes Discord 规则测试已通过
8. 剩余一项：用户侧真实消息烟测

## 8. 坑点记录

1. `approvals.mode` 使用 YAML 时，`off` 必须写成字符串 `'off'`，不能裸写。
   裸写会被 YAML 解析成布尔 `false`，导致运行时读取到的不是正式审批模式字符串。

2. 对独立 Hermes profile，长期自动执行应优先落 `config.yaml -> approvals.mode='off'`。
   `HERMES_YOLO_MODE=1` 只适合作为进程级旁路或临时验证手段，不适合作为稳定配置真相源。

3. `trend-backtest` 的 Discord 平台工具集应显式绑定 `hermes-discord`。
   否则 live bot 是否拿到 `delegate_task` / `execute_code` 会依赖隐式默认配置，增加排障不确定性。
