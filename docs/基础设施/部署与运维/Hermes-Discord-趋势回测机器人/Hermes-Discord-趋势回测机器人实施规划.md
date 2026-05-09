# Hermes Discord 趋势回测机器人实施规划

> 最后更新：2026-05-08

## 1. 实施策略

按“**文档准入 -> 运行态核实 -> 升级 -> 配置 -> 验证**”顺序执行，避免在旧版本或未知 Discord 拓扑上直接写配置。

## 2. 执行步骤

### Phase 0: 文档与任务盘

- [x] 建立文档目录
- [x] 创建 `README.md`
- [x] 创建架构设计文档
- [x] 创建实施规划文档
- [x] 更新 `todo.md`
- [x] 更新 `docs/基础设施/部署与运维/README.md`
- [x] 更新 `docs/INDEX.md`

### Phase 1: 本机运行态核实

- [x] 确认当前 `Hermes Agent` 版本
- [x] 确认是否存在升级提示
- [x] 确认当前 gateway 状态
- [x] 确认现有 `.env` 中是否已有 Discord token
- [x] 确认当前 Discord 相关配置是否只是空壳

### Phase 2: Hermes 升级

- [x] 执行 `hermes update`
- [x] 复查升级后版本
- [x] 确认配置未损坏
- [x] 若升级改动了配置 schema，执行必要迁移

### Phase 3: 独立 Profile

- [x] 创建 `trend-backtest` profile
- [x] 验证 profile 路径与主 profile 隔离
- [x] 为该 profile 写入默认模型
- [x] 为该 profile 写入显式回退模型链
- [x] 为该 profile 写入 Discord token
- [x] 为该 profile 写入 GitHub PAT 环境变量
- [x] 为该 profile 写入专职回测 `SOUL.md`
- [x] 修复 profile `.env` / `config.yaml` 的 UTF-8 BOM 问题
- [x] 补齐 `DISCORD_ALLOW_ALL_USERS=true`
- [x] 为 `SmartTrendTracker` 仓库绑定 `trend-backtest` 专用 Git credential helper
- [x] 克隆 Linux 工作副本：`/home/ubuntu/projects/SmartTrendTracker`
- [x] 为 Linux 工作副本写入本地 `HERMES.md`
- [x] 为 Linux 工作副本绑定 `trend-backtest` 专用 Git credential helper
- [x] 新增 `start-gateway.sh`，显式固定 Linux 工作目录
- [x] 在 `config.yaml` 写入 `terminal.cwd=/home/ubuntu/projects/SmartTrendTracker`
- [x] 为 profile 新增独立 `MEMORY.md`
- [x] 在 `trend-backtest/config.yaml` 写入 `approvals.mode='off'`，只对 `trend-backtest` 关闭命令审批弹窗
- [x] 在 `trend-backtest/config.yaml` 写入 `delegation` 配置，显式开启并行子 agent
- [x] 固定 `delegation.max_concurrent_children=3`
- [x] 2026-05-08 将主模型升级配置为 `openai-codex/gpt-5.5` + `agent.reasoning_effort=xhigh`
- [x] 2026-05-08 将主回退链改为 `kimi-coding/kimi-k2.6 -> zai/glm-5.1`
- [x] 2026-05-08 将文本辅助任务显式收口为默认 `zai/glm-4.7`、重要任务 `zai/glm-5.1`

### Phase 4: Discord 拓扑探测与规则写入

- [x] 通过 Discord API 读取 bot 所在 guild 列表
- [x] 读取目标 guild 的 channel 列表
- [x] 根据真实列表确定“大群”和“小群”
- [ ] 写入 mention 规则：
  - [x] 大群 require mention
  - [x] 小群 free response

### Phase 5: 启动与验证

- [x] 启动 `trend-backtest` gateway
- [x] 验证 Discord 登录成功
- [x] 运行 Hermes Discord 规则测试
- [ ] 验证大群不 `@` 时静默
- [ ] 验证大群 `@` 时响应
- [ ] 验证小群无需 `@` 也响应
- [x] 回写 `done.md`

## 3. 关键命令策略

### 3.1 升级

优先使用 Hermes 官方升级命令：

```bash
hermes update
```

### 3.2 Discord 探测

使用真实 Discord Bot API 拉取：

- guild 列表
- channel 列表

不靠手工猜群名和频道名。

### 3.3 密钥写入

Discord token、GitHub PAT、Z.AI/Kimi/OpenRouter 等 provider key 都只写 profile 运行时环境，不写入仓库；Git 仓库访问通过 repo-local helper 从 profile `.env` 读取。`trend-backtest` 的默认工作目录固定为 `/home/ubuntu/projects/SmartTrendTracker`。命令审批通过该 profile 的 `config.yaml` 固定为 `approvals.mode='off'`，并显式启用 `delegation` 以支持并行子 agent。

### 3.4 模型路由复验

```bash
hermes -p trend-backtest fallback list
hermes -p trend-backtest config check
hermes -p trend-backtest status
hermes -p trend-backtest chat -q '只回复 OK，不要调用工具。'
```

2026-05-08 复验结论：

- `fallback list`：`gpt-5.5 -> kimi-k2.6 -> glm-5.1`
- `config check`：OpenRouter unset，Z.AI/GLM configured，Kimi/Moonshot configured
- gateway：`trend-backtest=16901`、`multicore=16904`、`multicorerouter=16907`
- start scripts：三个 profile `start-gateway.sh` 已 source profile `.env` 并设置 `HERMES_GATEWAY_PLATFORM_CONNECT_TIMEOUT=120`
- smoke：`trend-backtest` session `20260508_174244_373cd2` 返回 OK，`0 tool calls`

## 4. 风险与缓解

### 风险 1：升级后配置 schema 漂移

缓解：

- 升级后立刻跑 `hermes doctor`
- 必要时执行 `hermes config migrate`

### 风险 2：Discord bot 已入 guild，但缺频道权限

缓解：

- 先读 guild / channel 拓扑
- 再启动 gateway
- 最后做真实消息验证

### 风险 3：大群 / 小群判断错位

缓解：

- 先拿真实 channel ID
- 配置按 ID，而不是按名字模糊匹配

### 风险 4：YAML 与隐式默认值导致配置口径漂移

缓解：

- `approvals.mode` 中的 `off` 必须显式写成字符串 `'off'`
- `platform_toolsets.discord` 显式绑定为 `hermes-discord`
- profile 级正式配置优先于进程级 `HERMES_YOLO_MODE` 临时旁路

## 5. 验证输出

最终需要留下的证据：

- 升级后版本号
- profile 列表与 `trend-backtest` 存在证据
- Discord guild / channel 探测结果
- gateway 启动日志
- Linux 工作副本 `git fetch` / `git status` 验证结果
- Hermes Discord 规则测试结果
- 大群 / 小群真实消息烟测结果
