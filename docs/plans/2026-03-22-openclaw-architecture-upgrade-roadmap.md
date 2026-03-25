# 2026-03-22 OpenClaw 架构升级路线图
更新时间：2026-03-22（北京时间）

## 1. 文档定位

这份文档回答的是一个更具体的问题：

- 当前 `OpenClaw` 已经有哪些可升级基础
- 它距离“默认编码工作流驱动、可自我进化”的目标架构还差什么
- 后续应该按什么顺序，把现有架构从“脚本编排为主”推进到“默认编码工作流 + profile registry + capability routing + 评分晋升”的目标形态

它不是替代以下文档，而是把它们连成一条迁移路线：

- `docs/plans/2026-03-13-workflow-architecture-manifesto.md`
  - 定义目标边界与最终形态
- `docs/plans/2026-03-21-openclaw-workflow-evolution-upgrade-design.md`
  - 定义升级原则、评分回路与最小可写面
- `docs/plans/2026-03-22-openclaw-infrastructure-foundation-spec.md`
  - 定义哪些能力属于平台基建，以及最小 manifest 字段表
- `skills/library/openclaw-workflow-manager/references/workflow-map.md`
  - 定义当前系统的实际地图
- `docs/2026-03-14-agent-skill-hook-绑定现状与优化清单.md`
  - 定义当前 binding 与 manifest 收口缺口
- `docs/adr/2026-03-22-default-coding-workflow-profile.md`
  - 定义默认编码工作流与 HardFlow Core 的正式决策

本文件只做一件事：

`把“从当前架构迁移到默认编码工作流驱动、可自我进化的目标架构”拆成可执行的阶段路线。`

---

## 2. 先给结论

当前架构不是混乱不可用，而是：

`已经具备升级基础，但还没有完全进入“默认产品清晰、边界稳定、升级可比较”的状态。`

更准确地说，当前 OpenClaw 是一种混合架构：

- `installer + profile 雏形`
- `cron jobs + runners`
- `task-center + task-executor`
- `agent routing + capability preflight`
- `runtime overlay + local backup + git sync`
- `hardflow gate + acceptance + completion verification`

这种形态的优点是：

- 已经能稳定运行
- 已经有治理链路
- 已经有自动发现、自动派单、自动执行、自动 push 的部分闭环
- 已经有 manifest、binding、drift、score 的基础概念

它的限制也很明确：

- 默认 workflow 还没有完全制度化
- SSOT 还没有完全收口
- binding 还没有完全统一成声明式 manifest
- workflow 仍然更像“runner 串起来的脚本链”
- 评分与回流还没有正式接管晋升
- 统一输出、人机协作、异常升级、监控计量还没有完全显式成平台基建

所以，后续目标不是推倒重来，而是把它推进成：

`HardFlow Core + coding-default + workflow profile registry + capability routing + score-driven promotion`

同时平台总逻辑固定为：

`用户提需求 -> 需求澄清 -> 任务拆分 -> 选择 workflow -> 执行闭环 -> 验证 -> 评分反馈`

---

## 3. 目标状态

目标状态不是“抽象最多”，而是“默认产品清晰、边界稳定、升级可比较”。

达到目标状态时，应同时满足下面 6 个条件：

1. 有统一注册中心
   - workflow profile、job、agent capability、skill binding、hook effect 都能登记和查询
2. 有明确事实源
   - repo 模板、安装器、运行态、索引、生成产物之间谁是 SSOT 必须固定
3. 有声明式 manifest
   - 依赖、能力、边界、输出不藏在 prompt 和隐式约定里
4. 有装配式 workflow
   - 默认 `coding-default` 先稳定，其它 workflow 再复用底座扩展
5. 有能力路由
   - workflow 绑定 capability，而不是永远写死某个 agent
6. 有评分晋升
   - 每一轮升级都能比较 `baseline`、`candidate` 与 `delta`，并据此晋升

这里的关键不是“工厂模式”，而是：

`先有默认编码工作流，再有多 workflow 扩展；先有 stable/candidate 晋升，再谈自动进化放权。`

---

## 4. 当前架构到底卡在哪里

### 4.1 SSOT 还不够收口

当前同一类信息仍可能散落在多个位置：

- repo 模板
- installer 逻辑
- runtime 现值
- 索引文档
- 生成产物

这会导致最常见的升级障碍不是“不会改”，而是：

- 不知道应该改仓库模板还是改运行态
- 不知道索引是不是最新
- 不知道本次问题是配置漂移还是设计本身有问题

### 4.2 agent / capability / skill / hook 绑定还没完全统一

当前已经有：

- capability manifest
- runtime binding 检查
- task preflight

但还没有做到所有关键边界都只看一套声明式定义。很多规则虽然存在，但还不是“只改一处就能全链生效”的状态。

### 4.3 workflow 模块化程度还不够

当前已经有相对清晰的层次：

- 发现层
- 派单与执行层
- 推送与交付层

但模块接口还不够彻底稳定，很多时候仍需要直接理解具体 runner 才能安全修改。

### 4.4 评分回流还没有成为正式升级主链

当前已经有评分、review、复盘、governance scan，但仍然经常停留在：

`知道哪里不好`

而没有稳定推进到：

`低分 -> 分类 -> 改 workflow/capability/skill -> 复跑 -> 比分 -> 晋升新基线`

### 4.5 默认 workflow 还没有制度化

当前默认编码流已经存在事实入口：

```bash
bash scripts/hardflow/hardflow-run.sh workflow --task "..."
```

但它仍然更像“惯用入口”，还不是正式声明的：

- `coding-default@stable`
- 配套 profile manifest
- 配套 promotion policy

这会导致后续新增 workflow 时，容易重新复制一套 runner 链，而不是在同一底座上装配。

### 4.6 需求入口与 workflow 选择还没有显式层

当前讨论已经明确：workflow 不是系统第一步。  
系统第一步应该是：

1. 接收需求
2. 澄清目标与边界
3. 做任务拆分
4. 再决定走哪个 workflow

这条逻辑当前在实际协作里存在，但还没有被正式沉淀成独立的入口层与选择规则。

### 4.7 输出、人机、异常、监控仍不够平台化

当前这些能力已经零散存在，但还没有被严格定义成统一基建：

- 输出协议
- 人工确认与恢复
- 异常升级与 incident
- token / 耗时 / 成本 / 失败率计量

如果这四块不收口，后续做负载均衡、环节裁剪和 candidate/stable 晋升时，会缺少统一的事实层。

---

## 5. 迁移原则

整个升级过程都遵守下面 10 条原则：

1. 先修地图与事实源，再修实现细节。
2. 先找最小可写面，不做大爆炸重写。
3. 先改 repo 模板、manifest、installer，再考虑手改 runtime。
4. 能新增模块就不爆改旧链路。
5. workflow 升级与 skill 升级分开推进，但共享同一套评分语言。
6. runtime 只作为运行事实，不作为长期设计文档。
7. 任何“升级成功”都必须带上对比基线。
8. 自动化只在边界稳定后再加强，否则会放大现有混乱。
9. 先做默认编码工作流稳定化，再做多 workflow 扩展。
10. 先做 candidate/stable 晋升，再做更激进的自我进化。

---

## 6. 分阶段升级路线

## 阶段 0：冻结术语、边界与事实源

### 目标

先让所有人和 agent 对“系统是什么”说同一种语言。

### 本阶段优先改动

- `docs/plans/2026-03-13-workflow-architecture-manifesto.md`
- `skills/library/openclaw-workflow-manager/references/workflow-map.md`
- `docs/plans/2026-03-21-openclaw-workflow-evolution-upgrade-design.md`
- 本文件
- `docs/adr/2026-03-22-default-coding-workflow-profile.md`

### 本阶段要解决的问题

- 哪些是 repo 模板
- 哪些是运行态现值
- 哪些是生成产物
- 哪些是 SSOT
- 哪些问题应该落到 workflow、capability、skill、hook、agent、installer、runtime
- 默认 workflow 到底是什么

### 验收标准

- 新增问题能先被正确归类，再进入修改
- 不再频繁出现“直接改 `~/.openclaw/*` 才发现改错层”的情况

---

## 阶段 1：把默认编码工作流正式制度化

### 目标

把“事实默认入口”升级成“制度默认产品”。

### 本阶段优先改动

- HardFlow README
- workflow profile 相关文档/manifest
- ADR
- 安装器默认 profile 配置

### 本阶段要做的事

1. 正式命名 `coding-default`
2. 明确 `hardflow-run.sh workflow` 等价于 `coding-default@stable`
3. 定义默认阶段图、默认多角色闭环、默认评分链
4. 明确其它 workflow 只能作为新增 profile 出现

### 验收标准

- 文档里不再把 HardFlow 直接描述成唯一业务工作流
- 文档里能明确回答系统默认 workflow 是什么
- 后续任何新增 workflow 设计都必须先落到 profile 层

---

## 阶段 1.5：把“需求 -> 拆分 -> workflow 选择”正式化

### 目标

把平台总入口从“默认直接进某条 workflow”升级成“先理解需求，再选择 workflow”。

### 本阶段要做的事

1. 固定总入口逻辑：
   - 需求澄清
   - 任务拆分
   - workflow 选择
2. 明确默认选择规则：
   - 代码/配置/测试/重构/修复类任务默认进入 `coding-default`
3. 预留非编码任务进入其他 profile 的扩展点

### 验收标准

- 文档里不再把 `coding-default` 描述成平台第一步
- 文档里能明确回答“为什么这个需求进了这个 workflow”
- 后续 profile selector 可以独立演进，而不需要改 HardFlow Core

---

## 阶段 2：收口 SSOT 与声明式清单

### 目标

把“系统里有哪些对象、它们依赖什么、谁负责什么”继续收口成机器可读清单。

### 本阶段核心对象

- `Schedule Registry`
- `agent_capability_manifest.json`
- `hook_event_matrix.json`
- `cron_agent_capability_matrix.json`
- `workflow profile manifest`
- `output / human / incident / telemetry manifest`
- 后续可补的 jobs manifest

### 本阶段优先入口

- `scripts/openclaw-ops/inspect_runtime_bindings.py`
- `scripts/openclaw-ops/generate_runtime_binding_manifests.py`
- `scripts/openclaw-ops/export_schedule_registry.py`
- `docs/2026-03-14-agent-skill-hook-绑定现状与优化清单.md`
- profile manifest 生成/校验脚本

### 本阶段要做的事

1. 让索引文件更明确地变成“生成产物”
2. 让 manifest 与 runtime 检查成为默认验收步骤
3. 尽量避免同一事实分散在多个手工维护文件里
4. 让默认 `coding-default` 具备正式 manifest

### 验收标准

- 新增一个 agent / skill / hook / job 时，有明确登记入口
- 新增一个 workflow 时，有明确 profile manifest 入口
- drift 能被检查脚本发现，而不是靠人工记忆

---

## 阶段 3：把 binding 继续显式化

### 目标

让 agent、skill、hook、task constraint 真正进入统一约束层。

### 本阶段优先入口

- `scripts/openclaw-ops/policy/task_executor_runner.py`
- `scripts/openclaw-ops/policy/task_center.py`
- 各类 `*_runner.py`
- manifest 生成与校验脚本

### 本阶段要做的事

1. 继续强化任务层字段：
   - `required_capabilities`
   - `required_skills`
   - `allowed_agents`
   - `workflow_profile_id`
2. 减少只存在于 prompt 里的隐式执行规则
3. 让“零 skill agent / role_only capability”也有显式机器可读定义

### 验收标准

- 任务分配前能做更稳定的 preflight
- 能清楚回答“为什么这个任务该给这个 agent”
- manifest 错、binding 漂移、allowed agent 错误能更早失败

---

## 阶段 4：把 workflow 从脚本链推进到装配链

### 目标

把“发现、派单、执行、review、push、通知”逐渐抽成更清晰的模块边界。

### 本阶段不追求

- 一次性重写全部 runner
- 为了抽象而抽象
- 引入复杂框架替代现有可运行链路

### 本阶段要做的事

1. 明确哪些 runner 属于发现层
2. 明确哪些属于执行与回写层
3. 明确哪些属于交付与推送层
4. 逐渐让模块之间通过结构化输入输出对接

### 可优先观察的改造目标

- `self_evolution_todo.py`
- `governance_evolution_runner.py`
- `github_web_evolution_runner.py`
- `task_executor_runner.py`
- `git_sync_push_runner.py`
- 默认 `coding-default` 的 profile/stage 定义

### 验收标准

- 升级某一段闭环时，不需要同时理解全部 runner
- 新增一种 workflow 时，更多是装配模块，而不是复制粘贴整条链

---

## 阶段 5：把评分与回流正式接入主流程

### 目标

让升级变成一个可比较过程，而不是一次次手工修补。

### 本阶段优先入口

- `scripts/hardflow/*`
- `docs/2026-03-19-openclaw-工作流治理与执行闭环升级说明.md`
- `docs/2026-03-20-openclaw-workflow-主升级方案.md`
- `skills/library/openclaw-evolution-upgrader/assets/*`

### 本阶段要做的事

1. 固定 workflow 评分维度
2. 固定 capability / skill 评分维度
3. 固定 `baseline / candidate / delta` 的最小输出格式
4. 让 `coding-default@candidate` 能正式与 `coding-default@stable` 对比
5. 让 upgrade feedback 不只是“提建议”，而是能稳定驱动下一轮改动

### 验收标准

- 不再只知道“这一轮不好”，而是知道“差在哪、该改哪、改后有没有更好”
- 升级成功有对比分数，不靠口头描述

---

## 阶段 6：多 workflow 扩展

### 目标

在默认编码工作流稳定后，允许新增其它 workflow profile。

### 本阶段前置条件

- `coding-default@stable` 已稳定
- candidate/stable 晋升机制已跑通
- capability 边界已收口
- profile manifest 已稳定

### 可扩展对象

- `research-default`
- `ops-default`
- `docs-default`
- 其他垂直业务 workflow

### 验收标准

- 新增 workflow 不复制整套 runner 链
- 新增 workflow 能复用 HardFlow Core 的 Gate、证据、验收、完成前验证

---

## 阶段 7：外部下载与安装市场

### 说明

这一阶段明确属于后置阶段，不在当前实施范围。

只有在下面条件成立后，才允许进入：

1. 默认编码工作流已稳定
2. profile manifest 已成熟
3. candidate/stable 晋升机制已成熟
4. drift 与回滚机制已成熟

在此之前，外部 workflow / skill 只能作为评估输入，不能直接成为默认线上能力。

---

## 7. 当前推荐执行顺序

当前最合理的顺序是：

1. 先做术语、ADR、地图收口
2. 再做 `coding-default` 制度化
3. 再做 manifest 与 binding 收口
4. 再做 candidate/stable 晋升
5. 最后做多 workflow 扩展

如果顺序反过来，比如先做下载市场、先做多 workflow、先做动态负载均衡，只会把现有边界再次打散。
