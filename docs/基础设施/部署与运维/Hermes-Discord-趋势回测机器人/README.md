# Hermes Discord 趋势回测机器人

> 状态：已配置完成，2026-05-08 已复验 WSL Hermes v0.13.0 模型路由
> 最后更新：2026-05-08

## 1. 需求定义

本子功能的目标是在**本机 WSL Ubuntu 中运行 Hermes Agent**，新建一个独立实例，名称为：

- 对外名称：`趋势回测机器人`
- 内部 profile：`trend-backtest`

该实例专门服务于 Discord 中的趋势回测讨论，不与当前主 Hermes 会话、主网关、主频道配置混用。

本次要完成的结果：

1. 升级本机 WSL 中的 `Hermes Agent` 到最新版本。
2. 创建 `trend-backtest` 独立 profile，隔离会话、配置、记忆和通道。
3. 为该 profile 配置独立 Discord bot token 与默认模型。
4. 根据真实 Discord guild / channel 拓扑，配置：
   - 大群：必须 `@` 机器人后才响应
   - 小群：不需要 `@`，可直接响应
5. 启动并验证该 profile 的 gateway 可正常接入 Discord。
6. 将该 profile 的 `SOUL.md` 收口为“专职回测 agent”，避免再次退化成通用聊天助手。
7. 为 `SmartTrendTracker` 本机仓库配置趋势回测机器人专用 GitHub 凭证链，避免复用其他全局 GitHub 凭证。
8. 为 `trend-backtest` 建立独立 Linux 工作副本，避免回测默认跑在 `/mnt/h` 挂载目录上。
9. 将本地 WSL `trend-backtest` 回测机器人的命令审批改为 profile 级自动执行，避免每次 GitHub/回测命令都要求人工点击批准。
10. 为 `trend-backtest` 显式开启 delegation，并允许在独立任务上并行启动多个子 agent。

## 2. 范围边界

本次只处理：

- 本机 WSL 内的 `Hermes Agent` 升级
- `trend-backtest` profile 创建
- Discord 通道接线与 guild / channel 规则
- 默认模型配置
- 主模型 / 回退模型配置
- 文档、任务盘与运行态验证
- `trend-backtest` 独立 Linux 工作副本与启动入口
- `trend-backtest` 本地自动执行审批
- `trend-backtest` delegation 并行子 agent 配置

本次不处理：

- 趋势回测策略本身的具体指标逻辑
- 回测数据源、回测引擎或策略脚本实现
- 主 Hermes profile 的 Telegram / Feishu 迁移
- 多 bot 编排、跨平台消息桥接

## 3. 子功能清单

- [x] 升级 Hermes Agent
- [x] 新建独立 profile
- [x] 写入 Discord token 与模型配置
- [x] 写入主模型 / 回退模型链
- [x] 获取真实 guild / channel ID
- [x] 配置大群 / 小群 mention 规则
- [x] 启动 gateway 并验证
- [x] 更新 `trend-backtest` 的 `SOUL.md`
- [x] 回写 `todo.md` / `done.md` / 索引文档
- [ ] 用户侧 Discord 消息烟测

## 4. 关键裁决

1. **不复用主 Hermes profile**
   `趋势回测机器人` 必须作为独立 profile 存在，避免污染当前主实例的会话、通道和记忆。

2. **Discord 规则按 guild / channel 精确配置**
   不能只做一个全局 `require_mention`，必须按真实频道分层：
   - 大群严控，避免误触发
   - 小群放开，提高回测交互效率

3. **敏感凭证只落运行时**
   Discord bot token、GitHub PAT 只写入 WSL profile 运行时配置或 `.env`，严禁写入仓库文件。

4. **升级先于配置**
   先把 `Hermes Agent` 升到最新，再创建 profile 和配置 Discord，避免旧版本配置口径漂移。

5. **回测工作目录使用 Linux 副本**
   `trend-backtest` 的默认工作目录必须指向 WSL 原生 Linux 文件系统中的独立仓库，而不是 `/mnt/h` 挂载目录。

6. **自动执行只限 `trend-backtest`**
   `trend-backtest` 是独立 Hermes profile，有自己的 `config.yaml`。因此自动执行应落在该 profile 的 `approvals.mode='off'`，而不是改其他 profile。

7. **并行子 agent 只做独立子任务**
   `delegate_task` 已由 `hermes-discord` 工具集原生提供，但只应用于互不冲突的独立任务；同一写入面仍保持串行，避免回测工作区互相踩改动。

## 5. 实际落地结果

- Hermes 已升级到 `v0.13.0 (2026.5.7)`
- `trend-backtest` 独立 profile 已创建
- 默认主模型已固定为 `openai-codex/gpt-5.5`，profile `agent.reasoning_effort=xhigh`
- 显式主回退链已固定为：`kimi-coding/kimi-k2.6 -> zai/glm-5.1`，回退项标注 `reasoning_effort=high`
- 常见文本辅助任务已显式配置：默认辅助任务使用 `zai/glm-4.7`，重要辅助任务 `compression` / `curator` 使用 `zai/glm-5.1`
- Kimi/Moonshot 直连 key 已配置（2026-05-08 已复验）：`KIMI_API_KEY` / `KIMI_CODING_API_KEY` 已注入 profile 运行时环境；`config check` 显示 Kimi/Moonshot configured，第一回退 `kimi-coding/kimi-k2.6` 与第二回退 `zai/glm-5.1` 均可用。
- 已通过 Discord API 核对到真实 guild：`智能趋势跟踪` (`1492491333653368894`)
- 已识别文本频道 5 个，其中小群 free-response 频道为：
  - `1495659215598125217` `趋势回测测试`
- 其余 Discord 文本频道默认保持 `require mention`
- `trend-backtest` 的 `SOUL.md` 已收口为“趋势回测专职研究员 / 本地多核回测执行官”
- `trend-backtest` gateway 已在 WSL `tmux` 会话 `trend-backtest-gateway` 中运行
- `/mnt/h/GitHub/SmartTrendTracker` 已绑定 `trend-backtest` 专用 Git credential helper，凭证从 profile `.env` 读取
- 已新增 Linux 工作副本：`/home/ubuntu/projects/SmartTrendTracker`
- Linux 工作副本根目录已写入本地 `HERMES.md`，用于覆盖项目内不适配 `trend-backtest` 的 `AGENTS.md`
- `trend-backtest` 启动入口已收敛为 profile 内 `start-gateway.sh`，默认固定 `TERMINAL_CWD=/home/ubuntu/projects/SmartTrendTracker`
- `trend-backtest/config.yaml` 已写入 `terminal.cwd=/home/ubuntu/projects/SmartTrendTracker`，不再依赖废弃环境变量口径
- `trend-backtest/config.yaml` 已写入 `approvals.mode='off'`，本地 WSL 回测机器人默认自动执行命令，不再弹审批框
- `trend-backtest/config.yaml` 已显式写入 `delegation` 配置，默认允许 `delegate_task` 使用 `terminal/file/web` 工具集并发启动最多 `3` 个子 agent
- Linux 工作副本根目录的本地 `HERMES.md` 已补充“默认自主执行、独立步骤优先并行、复杂任务可拆 delegation”的运行指令
- Hermes Discord 规则测试已通过：`34 passed`
- 2026-05-08 复验：三个 WSL profile `start-gateway.sh` 已显式加载 profile `.env` 并设置 `HERMES_GATEWAY_PLATFORM_CONNECT_TIMEOUT=120`；三个 profile gateway 已重启并 running，`trend-backtest` smoke session `20260508_174244_373cd2` 返回 OK 且 `0 tool calls`
- 运行时注意：Hermes 会按 session 缓存 system prompt，因此旧 Discord 会话如需立刻吃到新 `SOUL.md`，应执行一次 `/reset` 或直接开启新会话

## 6. 验收标准

- [x] `hermes --version` 显示已升级到最新可用版本
- [x] `hermes profile list` 中存在 `trend-backtest`
- [x] `trend-backtest` 具备独立 Discord 与模型配置
- [x] 能通过真实 Discord API 看到 bot 已加入目标 guild
- [ ] 大群消息不 `@` 机器人时不响应，`@` 后响应
- [ ] 小群不 `@` 机器人时可直接响应
- [x] gateway 启动成功并保留日志证据

## 7. 坑点记录

1. `approvals.mode` 写 YAML 时，`off` 不能裸写，必须写成字符串 `'off'`。
   否则 YAML 会把它解析成布尔 `false`，运行时虽然仍可能旁路审批，但配置读取口径会失真，后续排障很容易误判。

2. `trend-backtest` 已经是独立 profile，不需要再靠 `HERMES_YOLO_MODE=1` 这种进程级旁路长期维持自动执行。
   稳定方案应是把自动执行固定到该 profile 的 `config.yaml`，避免把临时 env 方案误当正式配置。

3. Discord 平台工具集不要只赌 Hermes 的隐式默认值。
   `trend-backtest/config.yaml` 应显式写 `platform_toolsets.discord=hermes-discord`，这样 `delegate_task`、`execute_code` 等能力是否对 live bot 可见就不会靠猜。
