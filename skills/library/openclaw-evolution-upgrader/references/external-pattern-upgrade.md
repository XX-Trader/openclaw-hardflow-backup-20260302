# 外部模式吸收升级

## 目标

把网络上的 workflow、skill、agent、hook、架构 pattern 转成可比较、可筛选、可落地的内部升级候选，而不是直接照抄。

## 适用场景

- 用户明确要求“看看网上怎么做”
- 当前仓库缺少某类能力，需要找外部范式
- 想比较“本仓做法”和“外部成熟方案”的差异
- 需要判断一个外部 skill / workflow 到底应不应该接入

## 信息源优先级

1. 官方文档
2. 官方仓库与 README
3. 官方设计说明、RFC、架构博客
4. issue / discussion / release notes
5. 二手总结文章

当外部信息会影响实现决策时，优先引用一手资料，不要仅依赖总结文。

## 固定分类

外部模式读完后，只能先落到这 4 个状态之一：

- `already_implemented`
- `present_but_disabled`
- `candidate_external_pattern`
- `not_applicable`

不要一上来就写成“缺失能力”。

## 差异评估问题

每次都回答这 5 个问题：

1. 我们当前有没有同类能力
2. 如果有，是已实现、未启用，还是实现不完整
3. 外部方案解决的是哪一层问题
4. 如果接入，最小落点是 skill、workflow、hook、agent、installer 还是 runtime
5. 它会不会破坏当前的边界、审计链、评分回路

## 落点判定

- 改“如何做、怎么验证、哪些行为禁止”：
  - 落 skill
- 改“什么时候触发、谁执行、如何闭环”：
  - 落 workflow
- 改“命令前后切面、约束、审计、提醒”：
  - 落 hook
- 改“角色能力边界、能力路由、默认执行人”：
  - 落 agent / capability manifest
- 改“安装、启停、同步、漂移修复”：
  - 落 installer / workflow-manager

## 推荐产物

每次吸收外部模式时，至少产出一张 pattern card，内容包括：

- 模式名称
- 来源链接
- 解决的问题
- 当前本仓状态
- 差异摘要
- 建议落点
- 风险与不采纳理由

## 明确禁止

- 不把外部文章的术语原样搬进内部架构，除非边界也一起对齐
- 不把二手总结直接当规范
- 不在未确认当前仓库现状前就宣布“我们没有”
- 不为了一次性接入外部方案而破坏现有 installer / task-center / executor 边界
