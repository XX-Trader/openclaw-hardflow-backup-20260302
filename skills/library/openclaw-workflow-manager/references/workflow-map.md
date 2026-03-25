# OpenClaw Workflow Map

本文件描述当前 OpenClaw 工作流体系的“实际地图”，不是目标架构宣言。  
阅读本文件时，始终区分：

- 仓库模板
- 运行态现值
- 默认稳定流
- 候选进化流

从 2026-03-22 起，本地图统一采用如下口径：

- `HardFlow Core` 是共享底座
- `coding-default` 是唯一默认工作流
- workflow 的选择发生在“需求澄清 + 任务拆分”之后
- `skill` 不是主产品，`workflow profile` 才是主产品
- 当前阶段只做仓内自升级，不做外部下载市场

---

## 1. 当前总体判断

当前仓库不是“没有平台”，而是“平台已经出现雏形，但默认产品还没有完全收口”。

已经存在的关键底座有：

- profile 安装与卸载
- cron/job 模板
- task-center 与 task-executor
- HardFlow G0-G6 评分门禁
- 部署后验收与完成前验证
- upgrade feedback 评分产物

当前最大缺口不是缺 runner，而是：

1. 默认 workflow 还没有正式声明成 `coding-default`
2. “需求澄清 -> 任务拆分 -> workflow 选择” 还没有完全制度化
3. workflow、capability、skill 之间的边界还不够硬
4. candidate 与 stable 的升级控制面还没有成为默认主链

---

## 2. 当前实际分层

### 2.1 仓库模板层

描述“理论上应该如何运行”。

- `scripts/hardflow/*`
  - HardFlow Core 的阶段、Gate 与证据规则
- `cron/jobs.json`
  - 仓库内 job 模板
- `openclaw/openclaw.json`
  - overlay 配置源
- `scripts/openclaw-ops/install_workflow_profile.py`
  - 把仓库模板安装到 runtime

### 2.2 运行态层

描述“机器当前实际如何运行”。

- `~/.openclaw/openclaw.json`
- `~/.openclaw/cron/jobs.json`
- `~/.openclaw/ops/task-center/task_center.db`
- `~/.openclaw/ops/...`

### 2.3 编排与执行层

描述“任务如何被发现、派单、执行、回写”。

- `self_evolution_todo.py`
- `governance_evolution_runner.py`
- `github_web_evolution_runner.py`
- `policy/task_executor_runner.py`
- reviewer / tester / project index 相关 runner

### 2.4 反馈与晋升层

描述“如何判断这一轮是否更好”。

- `scripts/hardflow/score-policy.json`
- `scripts/openclaw-ops/workflow_upgrade_scoring.py`
- `scripts/openclaw-ops/upgrade_feedback_runner.py`
- executor runs / scorecards / review reports

### 2.5 需求入口与 workflow 选择层

这是本轮文档收口后新增强调的一层，负责：

- 接收用户需求
- 澄清目标与边界
- 拆分任务
- 决定当前任务该进入哪个 workflow profile

当前这层已有事实能力，但还没有完全制度化成独立 profile selector。

---

## 3. 当前默认主链

当前实际默认主链，应理解为：

`需求澄清 -> 任务拆分 -> workflow 选择 -> HardFlow Core -> coding-default@stable -> 评分回流 -> 候选升级任务`

虽然仓库里还没有完整的 workflow profile 注册中心，但从运行习惯和脚本入口上看，以下命令已经是默认编码流入口：

```bash
bash scripts/hardflow/hardflow-run.sh workflow --task "..."
```

因此当前地图上的事实是：

- `hardflow-run.sh workflow` 已经承担默认编码工作流职责
- 只是它还没有完全被正式命名为 `coding-default@stable`
- 未来新增 workflow 时，应复用 HardFlow Core，而不是复制一套平行脚本链

---

## 4. 当前比较完整的闭环

目前最完整的自动闭环是：

1. workflow 仓库变化，或治理扫描发现问题
2. 生成任务写入 task-center
3. `task_executor_10m` 调用相应 agent 执行
4. agent 修改 workflow 仓库
5. `ops_git_sync_push` 推送远端
6. `ops_upgrade_feedback_daily` 汇总运行结果，生成 workflow/skill 评分产物
7. 低分结果可继续回流为升级任务

这条链路说明：

- “发现 -> 建单 -> 执行 -> 推送 -> 反馈”已经存在
- “需求 -> 拆分 -> 选 workflow -> 执行” 这条入口逻辑已经存在事实能力，但还缺正式显式层
- 但“candidate -> compare -> promote”还没有完全制度化

---

## 5. 当前不完整的闭环

### 5.1 运行态反哺仓库

当前存在：

1. `~/.openclaw` 运行态变化
2. `ops_local_openclaw_git_backup` 本地备份

当前缺失：

3. 自动把运行态变化转成正式候选 profile 变更
4. 自动进入 stable/candidate 对比

### 5.2 workflow profile 注册中心

当前存在安装器与模板，但仍缺少正式的 profile registry，导致：

- 默认编码工作流更多是“事实默认”，不是“制度默认”
- 后续新增 workflow 时，容易退回复制脚本链

### 5.3 capability 边界

当前已有 capability manifest 和 preflight 雏形，但仍需要进一步收口：

- task 层明确 `required_capabilities`
- workflow 层明确 `profile -> stage -> capability`
- skill 层退为 capability 的实现说明

### 5.4 需求入口与 workflow selector

当前默认编码流已经很强，但平台总流程还需要更明确地表达：

1. 用户先提需求
2. 系统先做澄清和拆分
3. 然后再决定用哪个 workflow 执行

否则默认编码流容易被误解成“系统一开始就先套进去”的第一步。

---

## 6. 自动化边界

| 能力 | 当前状态 | 说明 |
| --- | --- | --- |
| HardFlow G0-G6 主流程 | 已实现 | 当前已是默认编码流骨架 |
| profile 安装到 runtime | 已实现 | 通过 `install_workflow_profile.py` |
| 部署后验收 / 完成前验证 | 已实现 | 已进入 HardFlow 主链 |
| workflow 仓库 git sync push | 已实现 | 可持续回推远端 |
| upgrade feedback 评分产物 | 已实现 | 已有 scorecard 生成脚本 |
| 默认 `coding-default` 正式注册 | 未完成 | 目前只有事实入口，没有正式 profile 注册 |
| stable/candidate 晋升控制面 | 未完成 | 已有评分，尚未正式接管晋升 |
| 外部 workflow 下载与安装 | 当前不做 | 不属于本阶段范围 |

---

## 7. 当前文件到目标架构的映射

| 目标层 | 当前主要文件 | 当前状态 |
| --- | --- | --- |
| `HardFlow Core` | `scripts/hardflow/*` | 已具备核心骨架 |
| `Workflow Profile` | `install_workflow_profile.py`、overlay、job 模板 | 有安装能力，缺正式 profile registry |
| `Capability Layer` | capability manifest、task preflight、agent routing | 有雏形，仍需收口 |
| `Evidence & Score` | run 产物、scorecards、upgrade reports | 已可用，需接入晋升决策 |
| `Evolution Lab` | governance/self-evolution/upgrade feedback runner | 已有材料，尚未完全制度化 |

---

## 8. 对未来新增 workflow 的约束

以后如果要新增其他 workflow，必须满足以下条件：

1. 新增的是 `workflow profile`，不是平行脚本链
2. 必须复用 HardFlow Core 的证据、Gate、验收、完成前验证
3. 必须声明自己依赖哪些 capability
4. 必须有 stable/candidate 晋升路径
5. 不能绕过默认编码工作流的治理口径

换句话说：

`未来可以多 workflow，但只能单底座。`
