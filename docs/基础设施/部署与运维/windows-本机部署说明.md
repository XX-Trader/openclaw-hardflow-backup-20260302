# OpenClaw Windows 本机部署说明

## 1. 文档目标

这份文档用于说明 `Windows 本机` 上如何部署当前 `OpenClaw + 工作流 + 通道 + OpenViking 记忆` 基线。

适用场景：

- 本机开发
- 本机联调
- 本机演示
- 本机作为 `Telegram + Feishu` 双通道入口

当前文档只说明：

- 安装入口
- 关键参数
- Windows 本机推荐结构
- `Telegram + Feishu`
- `OpenViking`
- `hooks + jobs + auto-evolution`

当前文档不重复展开安装脚本内部实现。

## 2. Windows 本机基线

当前本机推荐基线：

- `OpenClaw` 已安装
- 工作流通过仓库脚本安装
- 标准配置文件：
  - `C:\Users\superma\.openclaw\openclaw.json`
- `Feishu` 通过 `openclaw-lark` 插件接入
- 记忆采用：
  - 官方内置能力
  - `OpenViking`
- `auto-evolution` 强制启用

## 3. 标准安装入口

Windows 本机仍然以仓库脚本为标准入口：

- `scripts/openclaw-ops/install_workflow_profile.py`
- `setup.py`

推荐理解方式：

- `install_workflow_profile.py` 负责实际安装、同步、校准
- `setup.py` 负责提供仓库层统一入口

建议优先方式：

```bash
python scripts/openclaw-ops/install_workflow_profile.py --profile core --workflow-repo-path .
```

如果后续做技能，技能应调用现有脚本，而不是重新造一套 Windows 手工安装流程。

## 4. 安装脚本参数

Windows 本机最常关注的参数如下。

### 4.1 基础参数

- `--profile`
  - 常用 `core` 或 `all`
- `--python-bin`
  - 指定本机 Python
- `--openclaw-home`
  - 指定运行时目录
- `--workflow-repo-path`
  - 指向当前仓库
- `--overlay-config-source`
  - 指定 overlay 配置源

### 4.2 配置同步参数

- `--sync-overlay-config`
  - 把仓库 overlay 合并到本机 `openclaw.json`
- `--ensure-runtime-skills`
  - 补齐运行时技能
- `--required-skills-manifest`
  - 指定技能清单
- `--reconcile-gateway-service`
  - 校准 gateway 运行方式
- `--gateway-service-prefer`
  - 本机通常更偏 `user`

### 4.3 工作流与任务参数

- `--project-registry`
- `--task-db`
- `--workflow-repo-id`
- `--jobs-file`

### 4.4 定时任务频率参数

- `--todo-every-ms`
- `--task-executor-every-ms`
- `--project-index-every-ms`
- `--git-sync-every-ms`
- `--auto-update-install-every-ms`

### 4.5 调试参数

- `--dry-run`
- `--emit-json`

推荐先演练：

```bash
python scripts/openclaw-ops/install_workflow_profile.py --profile core --workflow-repo-path . --dry-run --emit-json
```

## 5. Windows 本机工作流结构

本机工作流推荐仍然与服务器保持同一套逻辑，只是运行方式更轻量。

### 5.1 入口与角色

推荐结构按四层理解：

- 入口层：`arbitrageagent`、`spreadagent` 两个 Hermes profile 模板。
- 工作流层：`smart-arb-pipeline` 调用 `pipeline_runner.py`。
- 逻辑 owner 层：`coordinator`、`project-agent`、`web-agent`、`reviewer`、`backend-dev`、`frontend-dev`、`tester`、`deployer`、`doc-writer`。
- 定时任务层：`ops-agent`、`project-agent`、`optimization-agent`。

### 5.2 任务模型

任务采用双池：

- `todo`
- `jobs`

建议本机也保留这套结构，不因为是本地环境就退回“全靠人工临时调度”。

### 5.3 本机更关注的点

Windows 本机更关注：

- 配置是否正确合并
- `Telegram + Feishu` 是否都可用
- `OpenViking` 是否能启动
- hooks 是否真正启用
- jobs 是否安装到位

## 6. Hooks 结构

Windows 本机应启用两类 hooks。

### 6.1 强制启用的 auto-evolution hooks

- `hardflow-experience-capture`
- `hardflow-experience-recall`
- `hardflow-experience-evolve`

这三项视为强制项，不做可选分支。

### 6.2 配套治理 hooks

- `hardflow-command-guard`
- `hardflow-audit`
- `hardflow-stop-gate-reminder`

### 6.3 Windows 注意事项

Windows 本机不建议直接把未编译的 `.ts` hook 作为运行时入口。

推荐原则：

- 运行时入口应尽量使用稳定可执行形式
- 避免出现 `Unknown file extension ".ts"` 这类装载错误
- hooks 路径通过 `hooks.internal.load.extraDirs` 统一接入

## 7. Jobs 结构

Windows 本机建议保留以下 jobs 类型：

- `task-executor`
- `git-sync`
- `project-index`
- `reviewer-scan`
- `todo-patrol`
- `governance-evolution`
- `web-intel`
- `auto-update-install`

本机 jobs 的目标不是追求“数量多”，而是保证：

- 能跑
- 能留痕
- 能重装
- 能重启后恢复

## 8. 配置同步

Windows 本机配置同步采用 overlay 模式。

仓库配置源：

- `openclaw/openclaw.json`

运行时目标：

- `C:\Users\superma\.openclaw\openclaw.json`

建议原则：

- 仓库保存基线
- 本机保存最终运行态
- 由安装脚本负责合并

## 9. Telegram 与 Feishu

### 9.1 Telegram

Windows 本机建议保留：

- bot token
- `dmPolicy`
- `groupPolicy`
- 代理配置

如果本机不能直连 Telegram，应在 `openclaw.json` 中按通道配置代理，而不是优先污染系统全局代理。

### 9.2 Feishu

Windows 本机接入 `Feishu` 的标准方式：

```bash
npx -y @larksuite/openclaw-lark install
```

说明：

- 这是当前推荐安装方式
- 本机应把 `Feishu` 视为正式通道
- 后续服务器也可以采用同样方式补齐 `Feishu`

## 10. OpenViking 记忆方案

Windows 本机记忆路线统一为：

- 官方内置能力
- `OpenViking`

标准仓库：

- <https://github.com/volcengine/OpenViking>

### 10.1 官方安装方式

根据官方仓库，`OpenViking` 可通过 Python 包安装：

```bash
pip install openviking --upgrade --force-reinstall
```

### 10.2 Windows 本机配置文件

官方建议配置文件路径：

- `%USERPROFILE%\.openviking\ov.conf`

`cmd.exe` 下可设置：

```bash
set "OPENVIKING_CONFIG_FILE=%USERPROFILE%\\.openviking\\ov.conf"
```

### 10.3 启动方式

标准启动命令：

```bash
openviking-server
```

### 10.4 当前本机建议

官方默认常见端口是：

- `127.0.0.1:1933`

但 Windows 本机如果遇到端口占用或低位端口权限问题，可以改到更稳的端口，例如：

- `127.0.0.1:29333`

原则是：

- 端口一旦调整
- `OpenViking` 侧与 `OpenClaw` 侧配置必须同步修改
- 文档必须同步记录

### 10.5 OpenClaw 侧绑定

Windows 本机推荐：

- 由 `memory-openviking` 提供增强记忆
- `plugins.allow` 中加入 `memory-openviking`
- `plugins.slots.memory` 指向 `memory-openviking`

## 11. auto-evolution 必须启用

Windows 本机也必须启用 `auto-evolution`。

理由：

- 本机环境同样需要沉淀经验
- 本机更适合作为工作流验证与迭代入口
- 如果本机不启用，很多问题只能在服务器上被动暴露

所以本机标准不是“能跑就行”，而是：

- 能跑
- 能记忆
- 能进化

## 12. 推荐本机部署顺序

推荐顺序：

1. 安装或更新 `OpenClaw`
2. 运行工作流安装脚本
3. 同步 overlay 配置
4. 安装 `Feishu` 插件
5. 配置 `Telegram + Feishu`
6. 安装并启动 `OpenViking`
7. 配置 `memory-openviking`
8. 强制启用 auto-evolution hooks
9. 安装 jobs
10. 做本机状态检查

## 13. 本机验收建议

建议最少检查：

- `openclaw --version`
- `openclaw gateway status`
- `openclaw status`
- `openclaw plugins list`
- `OpenViking` 健康检查
- `Telegram` 状态
- `Feishu` 状态

## 14. 当前允许的取舍

为了快速上线，当前允许：

- provider key 先放在配置中
- 不把 secret 管理作为本阶段阻塞项

但这只是阶段性策略，不是长期目标。


## 2026-03-20 补充更新

Windows 本机当前还应补充遵循这两条规则：

1. `OpenViking` 标准检查
   - 统一入口：
     - `python scripts/openclaw-ops/check_openviking_stack.py --workspace-root .`
   - 若当前是官方默认记忆，应得到 `mode=official-default`
   - 若当前是增强记忆，应得到 `mode=openviking`

2. hooks 运行时目录
   - 本机运行时目录应统一为：
     - `%USERPROFILE%\\.openclaw\\hooks-runtime`
   - `hooks.internal.load.extraDirs` 应指向该运行时目录
   - 不再建议把仓库源码 `hooks/` 目录直接作为运行时 extraDirs
