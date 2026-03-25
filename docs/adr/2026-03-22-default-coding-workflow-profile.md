# ADR 2026-03-22：默认编码工作流与 HardFlow Core 收口决策

状态：Accepted  
日期：2026-03-22

## 背景

当前仓库已经具备：

- HardFlow G0-G6 评分门禁
- 部署后验收与完成前验证
- task-center / task-executor
- governance / self-evolution / upgrade feedback

但系统仍存在一个关键问题：

`默认 workflow 已经存在事实入口，却还没有成为正式制度对象。`

这带来三个风险：

1. HardFlow 容易继续被理解成“唯一业务流”，而不是共享底座
2. skill 容易继续被误当成系统主产品
3. 自我进化容易直接碰默认稳定流程，缺少 candidate/stable 晋升缓冲

## 决策

### 1. HardFlow 重新定位为 Core

`HardFlow` 从“一个默认编码工作流”上升为“所有 workflow 共享的流程内核”。

它负责：

- 阶段编排
- Gate 评分
- 部署后验收
- 完成前验证
- 证据落盘
- 回流整改

### 2. 默认 workflow profile 固定为 `coding-default`

系统唯一默认 workflow profile 定义为：

- `coding-default`

当前默认入口：

```bash
bash scripts/hardflow/hardflow-run.sh workflow --task "..."
```

被正式解释为：

`coding-default@stable`

这里的含义是：

- 平台先做需求澄清与任务拆分
- 当任务被判断为编码类任务时，默认选择 `coding-default`
- 因此 `coding-default` 是默认执行工作流，不是平台第一步

### 3. skill 不再是一等真值源

workflow 不直接绑定 skill。  
workflow 应先绑定 capability，再由 capability 绑定默认 agent、required skill、runtime requirement。

优先级改为：

`workflow profile > capability binding > skill implementation`

### 4. 自我进化必须通过 candidate/stable 晋升

任何默认工作流升级都必须经过：

1. 生成 candidate
2. 跑基准任务
3. 生成 scorecard
4. 比较 stable/candidate
5. 晋升或回滚

禁止：

- 自我进化直接覆盖默认 stable
- 只凭报告、不做对比就宣称升级完成

### 5. 其它 workflow 以后可以扩展，但不能绕过底座

未来允许新增：

- `research-default`
- `ops-default`
- `docs-default`

但它们必须：

1. 复用 HardFlow Core
2. 有独立 profile/manifest
3. 走同一套评分与晋升机制

## 结果

### 正向结果

- 默认产品变清晰
- HardFlow 的定位变稳定
- capability 与 skill 的边界更清楚
- 自我进化风险下降
- 多 workflow 扩展路径更清晰

### 成本与代价

- 需要补 profile manifest 与 promotion policy
- 需要在文档、安装器、评分产物里统一 `coding-default` 口径
- 短期内需要并存“事实入口”和“制度命名”的兼容解释

## 落地要求

1. 架构文档统一写入本决策
2. HardFlow README 明确 Core 定位
3. workflow map 明确默认工作流是 `coding-default`
4. 路线图优先做默认编码工作流制度化，再做多 workflow
