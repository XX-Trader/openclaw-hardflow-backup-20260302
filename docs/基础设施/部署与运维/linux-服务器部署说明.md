# OpenClaw Linux 服务器部署说明

## 1. 文档目标

这份文档用于说明 `Linux 服务器` 上如何部署当前 `OpenClaw + 工作流 + 通道 + OpenViking 记忆` 基线。

适用场景：

- 单台服务器部署
- 多台服务器统一部署
- 远程运维
- 工作流长期运行

当前文档只说明：

- 标准安装入口
- 关键参数
- 服务器工作流结构
- hooks 与 jobs
- `Telegram + Feishu`
- `OpenViking`
- `auto-evolution`

当前文档不重复展开安装脚本内部实现。

## 2. Linux 服务器基线

Linux 服务器推荐基线：

- `OpenClaw` 安装在服务器本地
- 通过仓库脚本安装工作流
- 运行时目录使用 `~/.openclaw`
- 统一配置文件：
  - `~/.openclaw/openclaw.json`
- 通道默认支持 `Telegram`
- 服务器同样支持补充 `Feishu`
- 记忆统一为：
  - 官方内置能力
  - `OpenViking`
- `auto-evolution` 强制启用

## 3. 标准安装入口

Linux 服务器仍以仓库脚本为标准入口：

- `scripts/openclaw-ops/install_workflow_profile.py`
- `setup.py`

推荐理解方式：

- `install_workflow_profile.py` 负责真正安装与同步
- `setup.py` 负责提供仓库统一入口

推荐方式：

```bash
python scripts/openclaw-ops/install_workflow_profile.py --profile core --workflow-repo-path .
```

## 4. 安装脚本参数

Linux 服务器更常用的参数如下。

### 4.1 基础参数

- `--profile`
- `--python-bin`
- `--jobs-file`
- `--openclaw-home`
- `--workflow-repo-path`
- `--overlay-config-source`

### 4.2 同步与 service 参数

- `--sync-overlay-config`
- `--ensure-runtime-skills`
- `--required-skills-manifest`
- `--reconcile-gateway-service`
- `--gateway-service-prefer`

服务器通常更适合关注：

- `--reconcile-gateway-service`
- `--gateway-service-prefer system`

### 4.3 工作流参数

- `--project-registry`
- `--task-db`
- `--workflow-repo-id`
- `--channel`
- `--to`

如果 Linux 服务器上的 cron 需要统一发到机器人所在群，而不是私聊某个用户，推荐直接在运行时配置 `~/.openclaw/openclaw.json` 中写入：

- `channels.telegram.cronDeliveryChannel = "telegram"`
- `channels.telegram.cronDeliveryChatId = "<group_chat_id>"`

之后再执行：

```bash
python scripts/openclaw-ops/install_workflow_profile.py --profile core --workflow-repo-path .
```

安装器在没有显式传 `--channel/--to` 时，会优先读取这两个本机字段作为 cron 默认投递目标。

### 4.4 jobs 频率参数

- `--todo-every-ms`
- `--task-executor-every-ms`
- `--project-index-every-ms`
- `--git-sync-every-ms`
- `--auto-update-install-every-ms`
- `--install-web-intel-jobs`
- `--install-multi-project-*`

### 4.5 调试参数

- `--dry-run`
- `--emit-json`

推荐先演练：

```bash
python scripts/openclaw-ops/install_workflow_profile.py --profile core --workflow-repo-path . --dry-run --emit-json
```

## 5. 服务器工作流结构

Linux 服务器上的 workflow 应作为长期运行基线，而不是临时脚本集合。

### 5.1 入口与角色

推荐结构按四层理解：

- 入口层：`arbitrageagent`、`spreadagent` 两个 Hermes Discord profile。
- 工作流层：`/home/arbops/.local/bin/smart-arb-pipeline` 调用 `/home/arbops/.hermes/ops/pipeline_runner.py`。
- 逻辑 owner 层：`coordinator`、`project-agent`、`web-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester`、`deployer`、`doc-writer`。
- 定时任务层：`coordinator`、`project-agent`。

### 5.2 双池模型

任务采用：

- `todo`
- `jobs`

服务器端更强调：

- 长期调度
- 稳定留痕
- 自动重试
- 升级人工

### 5.3 服务器侧更关注的点

服务器更关注：

- gateway service 是否稳定
- jobs 是否按频率运行
- hooks 是否持续启用
- `OpenViking` 是否长期健康
- 多通道是否可用

## 6. Hooks 结构

Linux 服务器应启用两类 hooks。

### 6.1 强制启用的 auto-evolution hooks

- `hardflow-experience-capture`
- `hardflow-experience-recall`
- `hardflow-experience-evolve`

这三项属于强制启用，不做环境特判。

### 6.2 治理 hooks

- `hardflow-command-guard`
- `hardflow-audit`
- `hardflow-stop-gate-reminder`

### 6.3 服务端加载方式

推荐通过 `hooks.internal` 体系启用：

- `hooks.internal.enabled=true`
- `hooks.internal.load.extraDirs` 指向 hooks 目录
- 每个 hook 独立 `enabled=true`

## 7. Jobs 结构

Linux 服务器上建议保留这些 jobs：

- `task-executor`
- `git-sync`
- `project-index`
- `reviewer-scan`
- `todo-patrol`
- `governance-evolution`
- `web-intel`
- `auto-update-install`

服务器端 jobs 的核心要求：

- 有固定频率
- 有标准日志
- 能自动重装
- 能定位失败原因

## 8. 配置同步

Linux 服务器配置同步采用 overlay 模式。

仓库配置源：

- `openclaw/openclaw.json`

运行时目标：

- `~/.openclaw/openclaw.json`

建议原则：

- 仓库保存基线
- 服务器保存运行时最终态
- 安装脚本负责同步

## 9. 运行方式

Linux 服务器更适合长期运行方式。

可选方式通常包括：

- system service
- tmux 常驻
- 受控 supervisor

当前推荐原则：

- 优先使用稳定的常驻方式
- service 配置应与安装脚本校准逻辑一致
- 不建议长期依赖人工手敲启动

## 10. Telegram 与 Feishu

### 10.1 Telegram

服务器端 `Telegram` 通常是默认标准通道之一。

建议保留：

- bot token
- `dmPolicy`
- `groupPolicy`
- 代理配置

### 10.2 Feishu

服务器端同样可以接入 `Feishu`，只是当前有些服务器尚未补齐。

标准安装方式：

```bash
npx -y @larksuite/openclaw-lark install
```

建议理解：

- `Feishu` 不是本机专属能力
- 服务器也应纳入统一支持范围
- 只是部署节奏上可以晚于 `Telegram`

## 11. OpenViking 记忆方案

Linux 服务器记忆统一采用：

- 官方内置能力
- `OpenViking`

标准仓库：

- <https://github.com/volcengine/OpenViking>

### 11.1 官方安装方式

根据官方仓库，推荐安装方式：

```bash
pip install openviking --upgrade --force-reinstall
```

### 11.2 官方配置文件

建议配置文件：

- `~/.openviking/ov.conf`

环境变量：

```bash
export OPENVIKING_CONFIG_FILE=~/.openviking/ov.conf
```

### 11.3 启动方式

标准启动命令：

```bash
openviking-server
```

后台方式可自行采用：

- `systemd`
- `tmux`
- `nohup`

### 11.4 端口建议

官方常见端口：

- `127.0.0.1:1933`

服务器端推荐优先保持默认端口，便于多机统一。

### 11.5 OpenClaw 侧绑定

服务器端推荐：

- 使用 `memory-openviking`
- `plugins.allow` 中加入 `memory-openviking`
- `plugins.slots.memory` 指向 `memory-openviking`

## 12. auto-evolution 必须启用

Linux 服务器必须强制启用 `auto-evolution`。

原因：

- 服务器承担长期经验沉淀
- 服务器承担周期维护
- 服务器上的 workflow 更需要稳定 recall 与 evolve

所以服务器部署时应把它作为验收项，而不是附加项。

## 13. 推荐服务器部署顺序

推荐顺序：

1. 安装或更新 `OpenClaw`
2. 运行工作流安装脚本
3. 同步 overlay 配置
4. 配置 `Telegram`
5. 视需要安装 `Feishu`
6. 安装并启动 `OpenViking`
7. 配置 `memory-openviking`
8. 强制启用 auto-evolution hooks
9. 安装 jobs 与 cron/定时维护
10. 做服务状态检查

## 14. 服务器验收建议

建议最少检查：

- `openclaw --version`
- `openclaw gateway status`
- `openclaw status`
- `openclaw plugins list`
- hooks 状态
- jobs/cron 状态
- `OpenViking` 健康状态
- `Telegram` 状态
- `Feishu` 状态

## 15. 当前允许的取舍

为了快速上线，当前允许：

- provider key 先放配置
- Secret 管理后置治理

但必须清楚这是上线阶段取舍，不是长期规范。


## 2026-03-20 补充更新

Linux 服务器当前还应补充遵循这两条规则：

1. `OpenViking` 标准检查
   - 统一入口：
     - `python scripts/openclaw-ops/check_openviking_stack.py --workspace-root .`
   - 若使用增强记忆，必须同时满足：
     - `plugins.slots.memory = "memory-openviking"`
     - `memory-openviking` 插件层通过
     - `OpenViking` 服务健康检查通过

2. hooks 运行时目录
   - 服务端运行时目录应统一为：
     - `~/.openclaw/hooks-runtime`
   - `hooks.internal.load.extraDirs` 应指向该运行时目录
   - 不再建议把仓库源码 `hooks/` 目录直接作为运行时 extraDirs
