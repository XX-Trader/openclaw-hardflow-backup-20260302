# Multica Managed Agents 平台研究

> 研究日期：2026-04-23
> 目标：判断 `multica-ai/multica` 对当前 OpenClaw / Hermes / 项目交付优先工作流是否有可借鉴价值。

## 1. 结论

Multica 是一个开源的 Managed Agents 平台，用 Web 看板、Issue、Agent、Runtime、Skill、Autopilot 把多个编码 Agent 管起来。它不是新的大模型，也不是独立编码 Agent，本质上是把本机已有的 `codex`、`openclaw`、`hermes`、`claude`、`gemini`、`cursor-agent` 等 CLI 包装成可分配任务的团队成员。

对当前 OpenClaw 体系的判断：

1. 不建议把现有 OpenClaw 手机 / Discord 主入口迁移到 Multica。
2. 不建议照搬 Multica 的完整 Web + Go + PostgreSQL + daemon 编排栈。
3. 建议借鉴它的轻量机制：Runtime 心跳、任务队列状态机、执行 transcript、Skill 绑定、daemon 健康检查、Autopilot 触发模型。
4. 若后续要做本地需求管理面，应优先做 OpenClaw 原生的轻量控制台或脚本状态面，而不是引入一套平行平台。

## 2. 形态区别

| 形态 | 含义 | 用途 |
|------|------|------|
| `multica.exe` / `multica-cli-*.zip` | CLI + 本地 daemon 的二进制产物 | 登录、配置 server、启动 daemon、检测本机 agent CLI、执行任务 |
| `multica-desktop-*.exe` | Electron 桌面客户端 | 桌面 UI + 管理 daemon + 同步 token + 自动更新 |
| GitHub 仓库 | 完整源码 | Next.js Web、Go 后端、PostgreSQL migrations、daemon、CLI、桌面端、自部署脚本 |
| Cloud Web | 官方托管网页端 | 通过 `https://multica.ai/app` 使用官方平台 |
| Self-host Web | 自部署网页端 | Docker 启动后访问 `http://localhost:3000` |

## 3. 中文与网页版本

Multica 有中文 README，也有 landing page 的中英文 i18n。源码中 `apps/web/features/landing/i18n/zh.ts` 说明官网落地页支持中文。

但核心应用控制台没有完整中文化迹象。`packages/views/*` 下大量业务 UI 文案是英文硬编码，例如 `Agents`、`Settings`、`Run now`、`New autopilot`、`Sign in to Multica`。因此用户看到“全英文”基本是准确的：中文主要覆盖 README / 落地页，不等于控制台全中文。

网页版本是存在的，分两种：

1. 官方 Cloud Web：连接官方 Multica 服务。
2. 自部署 Web：本地或服务器上跑 Next.js Web + Go API + PostgreSQL，再由本机 daemon 连接。

## 4. 使用路径

### 4.1 Cloud 模式

适合快速试用。

1. 安装 CLI 或桌面端。
2. 确保本机已安装至少一个 agent CLI，例如 `openclaw`、`codex`、`hermes`。
3. 运行 `multica setup`。
4. 打开 Multica Web，进入 Settings -> Runtimes，确认本机 runtime 在线。
5. 进入 Settings -> Agents，基于某个 runtime/provider 创建 Agent。
6. 在看板创建 Issue，并分配给 Agent。

### 4.2 Self-host 模式

适合私有化验证，但复杂度更高。

1. 安装 Docker / Docker Compose。
2. 启动 self-host server。
3. 打开 `http://localhost:3000`。
4. 运行 `multica setup self-host`，让本机 CLI/daemon 连接本地服务。
5. 后续流程与 Cloud 模式一致。

## 5. Agent 是否内置

Multica 不内置真实编码 Agent。它内置的是 Agent 管理模型和 provider 适配器。

真实执行依赖本机已有 CLI：

- `claude`
- `codex`
- `copilot`
- `opencode`
- `openclaw`
- `hermes`
- `gemini`
- `pi`
- `cursor-agent`
- `kimi`

daemon 启动时会用 `exec.LookPath()` 探测这些命令。没有任何可用 CLI 时，daemon 会直接报错。因此如果要实现类似本地需求，正确做法不是“内置一批 Agent”，而是维护 provider registry，把已有 OpenClaw / Codex / Hermes runtime 注册进去。

这点与当前项目文档里的裁决一致：`project-agent` 不应做成新的常驻 Agent，而应是 Skill + 脚本组合。

## 6. 架构观察

Multica 的核心链路如下：

```text
Web / Desktop
-> Go Backend + WebSocket
-> PostgreSQL
-> local multica daemon
-> detected agent CLI
-> isolated work directory
-> task transcript / status / comments 回传
```

关键数据对象：

- `workspace`：工作区。
- `agent`：平台里的 Agent 配置。
- `agent_runtime`：某台机器上某个 provider 的 runtime。
- `issue`：任务载体。
- `comment`：人和 Agent 的对话载体。
- `agent_task_queue`：任务队列与执行状态。
- `skill` / `agent_skill`：技能实体和 Agent 绑定。
- `autopilot`：计划任务或手动触发任务。

## 7. 可借鉴之处

### 7.1 Runtime registry + heartbeat

Multica 把本机 daemon 探测到的 provider 注册成 runtime，并通过心跳维护在线状态。这个机制适合借鉴到 OpenClaw 运维侧，用于明确区分：

- OpenClaw 服务是否在线。
- 某个 agent CLI 是否可用。
- 某个 workspace 是否可执行任务。
- 当前任务是否卡在 queued / running / failed。

### 7.2 统一任务状态机

`agent_task_queue` 使用 queued、dispatched、running、completed、failed、cancelled 等状态，能把“任务到底有没有执行”说清楚。当前 OpenClaw 的移动端体验很好，但长期任务排查仍需要更明确的任务状态账本。

建议借鉴为本地 NDJSON / SQLite 账本，而不是马上引入 PostgreSQL。

### 7.3 执行 transcript 标准化

Multica 把 Agent 执行过程统一成 text、tool-use、tool-result、error、status 等消息。这对排障很有价值，适合并入现有记忆蒸馏和失败学习机制。

### 7.4 Skill 发现与注入

Multica 按 provider 处理不同 Skill 路径：

- Codex：`CODEX_HOME/skills`
- OpenClaw：`~/.openclaw/skills`
- Claude：`~/.claude/skills`
- Cursor：`~/.cursor/skills`

并在执行目录写入 `AGENTS.md`、`CLAUDE.md` 或 `GEMINI.md`。这个思路可借鉴，但当前仓库已经有项目级三件套、Skill 化架构和 project memory，不需要另起一套 Skill 市场。

### 7.5 Desktop daemon manager

桌面端负责 CLI 下载、daemon 启停、token 同步、版本不一致时等待任务 drain 后重启。这个工程细节值得借鉴，尤其适合后续做 Windows 本地守护进程管理。

### 7.6 Autopilot

Autopilot 支持定时触发 Agent 任务，但当前 CLI 文档显示主要暴露 `create_issue` 模式，`run_only` 数据模型存在但链路未完全暴露。这个方向可参考，但不应替代当前 cron/jobs + OpenClaw 轻量调度。

## 8. 不建议照搬之处

1. **完整 Web 平台过重**：Next.js + Go + PostgreSQL + auth + daemon 对单人或手机指令链路太重。
2. **移动端入口不如 OpenClaw 自然**：OpenClaw 通过 Discord / 手机即可使用，Multica 更像桌面/网页工作台。
3. **控制台中文化不足**：核心应用英文硬编码较多，直接给中文用户用体验不佳。
4. **Agent 编排复杂度高**：如果只是调用脚本、交付项目、维护记忆，OpenClaw -> scripts -> runtime 的链路更简单。
5. **商业许可需注意**：内部使用问题不大，但作为 SaaS / 托管服务 / 嵌入商业产品给第三方用，有额外许可限制。

## 9. 对当前项目的建议

### 保留 OpenClaw 主链

继续以 OpenClaw 作为外部唯一入口，尤其保留手机 / Discord 交互优势。

### 借鉴 Multica 的轻量内核

优先做以下小模块，而不是引入 Multica：

1. `runtime_status_registry`：记录 agent/provider/workspace 在线状态。
2. `task_execution_ledger`：记录任务状态迁移和执行 transcript。
3. `skill_binding_report`：列出每个 agent 实际加载的 Skill。
4. `run_comment_contract`：强制任务完成后回写结果，而不是只留在终端日志。
5. `daemon_health_panel`：只读健康面，不做复杂控制面。

### 不内置 Agent

不要把 Agent 做成内置黑盒。应保持：

```text
OpenClaw / Codex / Hermes / Gemini 等外部 CLI
-> 本地 provider registry
-> Skill + 项目记忆注入
-> 脚本 / runtime 执行
```

这符合当前仓库“项目交付优先”和“不要发明额外 workflow service”的方向。

## 10. 来源

- GitHub 仓库：<https://github.com/multica-ai/multica>
- README：<https://github.com/multica-ai/multica/blob/main/README.md>
- 中文 README：<https://github.com/multica-ai/multica/blob/main/README.zh-CN.md>
- CLI / Daemon 文档：<https://github.com/multica-ai/multica/blob/main/CLI_AND_DAEMON.md>
- Self-host 文档：<https://github.com/multica-ai/multica/blob/main/SELF_HOSTING.md>
- Windows 安装脚本：<https://github.com/multica-ai/multica/blob/main/scripts/install.ps1>
- License：<https://github.com/multica-ai/multica/blob/main/LICENSE>
