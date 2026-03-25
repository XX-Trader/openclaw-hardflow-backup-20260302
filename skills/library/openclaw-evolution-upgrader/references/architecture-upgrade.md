# 架构升级落点

## 当前架构是什么

当前 OpenClaw 更接近一种混合架构：

- `installer + profile`
- `cron jobs + runners`
- `task-center + task-executor`
- `agent routing + capability preflight`
- `runtime overlay + local backup + git sync`

它已经具备升级基础，但还没有完全进入“最容易升级”的状态。

## 目标架构是什么

目标不是纯工厂模式，而是：

`注册中心 + 声明式 manifest + 可装配 workflow + 能力路由 + 评分反馈`

原因很简单：

- 纯工厂模式更擅长“创建对象”
- 但 OpenClaw 需要回答的还有：
  - 如何注册
  - 什么时候启用
  - 与哪些 workflow 组合
  - 失败后如何回流
  - 分数低了该改哪层

所以更适合的目标是“装配式架构”，不是单纯的“创建式架构”。

## 当前到目标之间还差什么

### 1. SSOT 继续收口

仍然存在 repo 模板、runtime、索引文档、生成产物之间的漂移风险。
先把“哪个是事实源”彻底固定，升级速度才会稳定。

### 2. binding 继续 manifest 化

agent、skill、hook、task constraint 虽然已有一部分显式化，但还没完全收敛成统一 manifest。

### 3. workflow 从脚本编排升级到模块装配

当前更多还是“installer 写 job、job 调 runner”。
目标是把发现、派单、执行、review、push、通知这些环节拆成更清晰的模块接口。

### 4. 评分回流进入主链

现在已有复盘和评分意识，但还没形成稳定的：

`低分 -> 分类 -> 升级 skill/workflow -> 再验证 -> 晋升新基线`

## 最容易升级的架构特征

满足下面 5 点时，系统升级成本最低：

1. 有统一注册中心
2. 能力和依赖是声明式 manifest，不藏在 prompt 里
3. workflow 可以组装，而不是每次手写一条完整链路
4. agent 绑定的是 capability，不是写死单个角色
5. 每轮升级都有评分回流和基线比较

## 迁移顺序建议

### 阶段 1：先修地图和 SSOT

- 统一 repo 模板、runtime、索引、生成产物的边界
- 优先修 manifest、index、installer 漂移

### 阶段 2：继续补 declarative binding

- 把 agent / skill / hook / capability / task constraint 的绑定继续显式化
- 减少靠 prompt 和记忆维持的隐式规则

### 阶段 3：抽 workflow 模块边界

- 把发现、派单、执行、验收、push、通知的接口继续拆清楚
- 尽量让模块之间通过结构化产物交互

### 阶段 4：补评分与晋升机制

- 形成 baseline / candidate / delta
- 低分先归因，再决定升级 workflow 还是 skill

### 阶段 5：最后再动更多自动化

- 当地图、manifest、评分回流都稳定以后，再补更强的自动进化脚本
- 否则自动化只会放大当前结构问题

## 升级某块时优先改哪里

| 目标 | 优先落点 | 不建议先改 |
| --- | --- | --- |
| job 频率、触发、安装方式 | `cron/jobs.json`、`cron_setup.py`、`install_*_job.py` | 直接手改运行态 jobs |
| 任务发现、派单、执行、回写 | `policy/task_executor_runner.py`、`task_center.py`、runner 脚本 | 只改 prompt 绕过现有 preflight |
| agent 行为规范 | `skills/library/<skill>/SKILL.md` 与 `references/` | 只在某次任务里临时补说明 |
| hook 切面与约束 | `hooks/`、`openclaw/openclaw.json`、`install_workflow_profile.py` | 在单个 agent 里私自复制一套逻辑 |
| runtime 同步与安装对齐 | installer、overlay、workflow-manager | 先改 `~/.openclaw/*` 现值 |

## 结论

当前架构不是不能升级，而是“基础不错，但还没完全装配化”。
后续判断是否在朝目标架构演进时，优先看这句话是否越来越成立：

`先看注册与地图，再看 manifest 约束，再看模块装配，最后用评分决定下一轮升级落点。`

## 继续阅读

如果问题已经不是“目标架构是什么”，而是“从当前架构具体怎么迁移过去、按什么阶段推进”，继续阅读：

- `../../../docs/plans/2026-03-22-openclaw-architecture-upgrade-roadmap.md`
