# PatternCard 字段规范（v1）

**Goal:** 把外部模式学习流水线中的 `PatternCard` 从概念对象收紧为可直接实现的工程化数据契约，供 `pattern_extractor.py`、评估脚本、任务晋升逻辑和文档归档统一使用。

**Status:** Draft v1

**Scope:** 本规范定义 `PatternCard` 的字段结构、类型、必填约束、枚举值、归一化规则、校验规则、派生字段和推荐存储方式。

---

## 1. 对象边界

`PatternCard` 是“单个外部候选模式”的标准化记录对象。

它负责表达：

- 这个模式来自哪里
- 它解决什么问题
- 它的输入输出与执行边界是什么
- 它和当前 OpenClaw 工作流的适配度如何
- 它是否值得进入沙箱评估、TODO、正式资产草案或仅归档

它**不是**下面这些对象：

- 原始网页或仓库归档
- benchmark 原始运行日志
- 最终生成的 skill / agent / hook 文件
- 单纯的人类阅读摘要

## 2. 推荐落盘形式

### 2.1 Source of Truth

推荐以 JSON 作为真源：

- `docs/patterns/cards/{pattern_id}.json`

### 2.2 Human Summary

可选输出 Markdown 摘要：

- `docs/patterns/reviews/{pattern_id}.md`

### 2.3 Benchmark Artifacts

评估结果单独落盘：

- `docs/patterns/benchmarks/{pattern_id}.json`

### 2.4 Canonical Path Policy

- `PatternCard` 的 JSON 契约只允许使用本文定义的 canonical nested paths。
- 允许在说明性 prose 中使用短写，例如 `title`、`artifact_type`、`source_url`。
- 但在下列场景中，必须写 canonical paths，而不是短写：
  - JSON 样例
  - 校验器
  - 测试数据
  - 自动生成产物
  - “Required Fields” 之类的字段清单
- 例如：
  - `title` 的 canonical path 是 `identity.title`
  - `artifact_type` 的 canonical path 是 `identity.artifact_type`
  - `source_url` 的 canonical path 是 `source.source_url`
- 禁止再定义一套 flat top-level aliases 作为实现契约。

## 3. 顶层结构

`PatternCard` v1 采用固定顶层结构：

```json
{
  "schema_version": "pattern-card/v1",
  "pattern_id": "ptn-example-1a2b3c4d",
  "status": "draft",
  "identity": {},
  "source": {},
  "extraction": {},
  "contracts": {},
  "operational": {},
  "scoring": {},
  "promotion": {},
  "evidence": [],
  "audit": {}
}
```

## 4. 顶层字段定义

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema_version` | `string` | 是 | 当前固定为 `pattern-card/v1` |
| `pattern_id` | `string` | 是 | 全局唯一 ID |
| `status` | `string` | 是 | 卡片生命周期状态 |
| `identity` | `object` | 是 | 候选模式的基础身份信息 |
| `source` | `object` | 是 | 来源、抓取和许可信息 |
| `extraction` | `object` | 是 | 抽取出的模式语义 |
| `contracts` | `object` | 是 | 输入输出与工具契约 |
| `operational` | `object` | 是 | 权限、运行时、guardrail 和副作用边界 |
| `scoring` | `object` | 是 | 多维评分与综合结论 |
| `promotion` | `object` | 是 | 晋升建议与后续动作 |
| `evidence` | `array<object>` | 是 | 证据引用列表，至少 1 条 |
| `audit` | `object` | 是 | 抽取、审阅、评估、回写审计信息 |

## 5. 生命周期状态

`status` 允许取值：

- `draft`
- `reviewed`
- `benchmarked`
- `promoted`
- `archived`
- `rejected`

约束：

- 新抽取出的卡片默认 `draft`
- 完成结构化人工或 agent 复核后可进入 `reviewed`
- 存在 benchmark 结果后进入 `benchmarked`
- 已生成正式资产草案或被正式采纳后进入 `promoted`
- 明确保留但不继续推进时进入 `archived`
- 明确不采用时进入 `rejected`

## 6. `pattern_id` 规范

格式要求：

- 正则：`^ptn-[a-z0-9][a-z0-9-]{7,63}$`
- 全小写
- 只允许字母、数字、连字符

推荐生成方式：

- `ptn-{slug}-{short_hash}`

示例：

- `ptn-claude-code-hook-guardrail-a13f9c2d`
- `ptn-review-workflow-fanout-7b42e811`

## 7. `identity` 字段定义

```json
{
  "title": "Hook-based Guardrail Review Loop",
  "artifact_type": "workflow",
  "summary": "使用 hook 在任务完成前做质量拦截的工作流模式",
  "keywords": ["hook", "guardrail", "review", "workflow"],
  "workflow_shape": {
    "primary": "review-loop",
    "tags": ["scheduled-scan", "quality-gate"]
  }
}
```

### 7.1 字段表

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `identity.title` | `string` | 是 | 模式名，人类可读 |
| `identity.artifact_type` | `string` | 是 | 候选模式类别 |
| `identity.summary` | `string` | 是 | 1 到 240 字的单段摘要 |
| `identity.keywords` | `array<string>` | 否 | 关键词标签 |
| `identity.workflow_shape` | `object` | 是 | 工作流形态 |

### 7.2 `artifact_type` 枚举

- `agent`
- `skill`
- `hook`
- `plugin`
- `workflow`
- `prompt-pattern`
- `evaluation-pattern`
- `guardrail-pattern`

### 7.3 `workflow_shape.primary` 枚举

- `standalone-task`
- `manager-worker`
- `fan-out-fan-in`
- `handoff-chain`
- `review-loop`
- `scheduled-scan`
- `retrieval-augmented`
- `guardrailed-execution`
- `hybrid`

### 7.4 `workflow_shape.tags` 推荐值

- `parallel`
- `human-gate`
- `background`
- `benchmarkable`
- `repo-aware`
- `network-bound`
- `read-only`
- `write-capable`
- `tool-heavy`

## 8. `source` 字段定义

```json
{
  "source_kind": "community-repo",
  "source_url": "https://github.com/example/repo",
  "source_domain": "github.com",
  "trust_tier": "tier2",
  "retrieval_method": "github_search",
  "query_hits": ["claude code hooks workflow"],
  "upstream_repo": "example/repo",
  "upstream_ref": "main",
  "captured_at": "2026-03-14T03:40:00Z",
  "published_at": "2026-02-01T00:00:00Z",
  "last_verified_at": "2026-03-14T03:45:00Z",
  "freshness_days": 42,
  "license_or_usage_note": "MIT, 可参考实现但需保留原许可说明"
}
```

### 8.1 字段表

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `source.source_kind` | `string` | 是 | 来源类型 |
| `source.source_url` | `string` | 是 | 主要来源 URL |
| `source.source_domain` | `string` | 是 | 从 URL 派生出的域名 |
| `source.trust_tier` | `string` | 是 | 来源信号层级 |
| `source.retrieval_method` | `string` | 是 | 当前卡片如何被发现 |
| `source.query_hits` | `array<string>` | 否 | 命中的查询列表 |
| `source.upstream_repo` | `string` | 条件必填 | 如果来源为仓库，必须填写 `owner/repo` |
| `source.upstream_ref` | `string` | 否 | 分支、tag 或 commit |
| `source.captured_at` | `string` | 是 | 首次归档时间，UTC ISO8601 |
| `source.published_at` | `string` | 否 | 内容公开发布时间 |
| `source.last_verified_at` | `string` | 否 | 最近一次重新验证时间 |
| `source.freshness_days` | `integer` | 否 | 派生字段，按天计算 |
| `source.license_or_usage_note` | `string` | 是 | 许可、引用、使用限制说明 |

### 8.2 `source_kind` 枚举

- `official-doc`
- `community-repo`
- `curated-index`
- `blog`
- `video`
- `forum`
- `marketplace`
- `manual-note`

### 8.3 `trust_tier` 枚举

- `tier1`
- `tier2`
- `tier3`
- `tier4`

映射建议：

- `tier1`: 官方文档、官方 SDK、官方仓库
- `tier2`: 高质量可执行社区仓库
- `tier3`: curated index、转述型资料
- `tier4`: 博客、视频、论坛、二手整理

### 8.4 `retrieval_method` 枚举

- `github_search`
- `web_fetch`
- `skill4agent`
- `manual_seed`
- `vendor_registry`
- `project_registry_hint`

## 9. `extraction` 字段定义

```json
{
  "problem": "在 agent 完成任务时补充强制质量门，避免低质量结果直接标记完成",
  "trigger_conditions": [
    "任务进入完成阶段",
    "存在可执行质量检查命令"
  ],
  "core_steps": [
    "捕获任务完成事件",
    "执行验证逻辑",
    "失败时阻断完成并给出反馈",
    "通过后允许任务关闭"
  ],
  "strengths": [
    "质量门位置明确",
    "能复用现有 hook 机制"
  ],
  "failure_modes": [
    "验证命令过重导致吞吐下降",
    "误拦截引起循环修复"
  ],
  "anti_patterns": [
    "在主 prompt 中隐式要求模型自检但没有外部校验"
  ],
  "fit_targets": ["reviewer", "optimization-agent"],
  "not_fit_targets": ["high-frequency-low-value-scan"]
}
```

### 9.1 字段表

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `extraction.problem` | `string` | 是 | 该模式解决的核心问题 |
| `extraction.trigger_conditions` | `array<string>` | 是 | 触发条件 |
| `extraction.core_steps` | `array<string>` | 是 | 核心执行步骤 |
| `extraction.strengths` | `array<string>` | 是 | 优势 |
| `extraction.failure_modes` | `array<string>` | 是 | 常见失败模式 |
| `extraction.anti_patterns` | `array<string>` | 否 | 不应如何使用 |
| `extraction.fit_targets` | `array<string>` | 否 | 适合接入的本仓目标 |
| `extraction.not_fit_targets` | `array<string>` | 否 | 不适合接入的场景 |

### 9.2 校验约束

- `core_steps` 至少 2 项，最多 12 项
- `failure_modes` 至少 1 项
- 所有列表去重后不得为空

## 10. `contracts` 字段定义

```json
{
  "input_contract": {
    "required_inputs": ["task payload", "quality command", "status context"],
    "optional_inputs": ["diff summary", "historical failure count"],
    "assumptions": ["执行环境可运行验证命令"]
  },
  "output_contract": {
    "primary_outputs": ["pass_or_block_decision", "feedback_message"],
    "success_criteria": ["通过时允许任务完成", "失败时给出明确反馈"],
    "failure_signals": ["validation_timeout", "missing_quality_command"]
  },
  "tooling": [
    {
      "tool_name": "hook-event-handler",
      "required": true,
      "purpose": "拦截任务完成事件"
    },
    {
      "tool_name": "bash",
      "required": true,
      "purpose": "执行质量检查命令"
    }
  ]
}
```

### 10.1 字段表

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `contracts.input_contract` | `object` | 是 | 输入要求 |
| `contracts.output_contract` | `object` | 是 | 输出要求 |
| `contracts.tooling` | `array<object>` | 是 | 所需工具列表 |

### 10.2 `input_contract` 子字段

| 字段 | 类型 | 必填 |
|---|---|---|
| `required_inputs` | `array<string>` | 是 |
| `optional_inputs` | `array<string>` | 否 |
| `assumptions` | `array<string>` | 否 |

### 10.3 `output_contract` 子字段

| 字段 | 类型 | 必填 |
|---|---|---|
| `primary_outputs` | `array<string>` | 是 |
| `success_criteria` | `array<string>` | 是 |
| `failure_signals` | `array<string>` | 是 |

### 10.4 `tooling` 子字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `tool_name` | `string` | 是 | 工具名 |
| `required` | `boolean` | 是 | 是否必须 |
| `purpose` | `string` | 是 | 用途说明 |
| `notes` | `string` | 否 | 附加说明 |

## 11. `operational` 字段定义

```json
{
  "permissions": {
    "mode": "workspace-write",
    "network_required": false,
    "shell_required": true,
    "sensitive_operations": ["task state transition gating"]
  },
  "guardrails": [
    {
      "name": "task-completed-gate",
      "scope": "task-completion",
      "mechanism": "hook",
      "blocking": true
    }
  ],
  "runtime_requirements": ["task-center access", "hook runtime", "quality command"],
  "human_gate_required": false,
  "side_effect_level": "medium"
}
```

### 11.1 字段表

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `operational.permissions` | `object` | 是 | 权限要求 |
| `operational.guardrails` | `array<object>` | 是 | 风险控制手段 |
| `operational.runtime_requirements` | `array<string>` | 是 | 运行时依赖 |
| `operational.human_gate_required` | `boolean` | 是 | 是否需要人工确认 |
| `operational.side_effect_level` | `string` | 是 | 副作用等级 |

### 11.2 `permissions.mode` 枚举

- `read-only`
- `workspace-write`
- `network-read`
- `network-write`
- `shell-exec`
- `elevated`
- `hybrid`

说明：

- 如果一个模式涉及多种权限，`mode` 填 `hybrid`，并在其他字段展开说明

### 11.3 `guardrails` 子字段

| 字段 | 类型 | 必填 |
|---|---|---|
| `name` | `string` | 是 |
| `scope` | `string` | 是 |
| `mechanism` | `string` | 是 |
| `blocking` | `boolean` | 是 |
| `notes` | `string` | 否 |

### 11.4 `side_effect_level` 枚举

- `none`
- `low`
- `medium`
- `high`

## 12. `scoring` 字段定义

```json
{
  "signal_score": 82,
  "fit_score": 88,
  "safety_score": 74,
  "eval_score": 68,
  "novelty_score": 61,
  "reuse_score": 79,
  "adoptability_score": 78,
  "scoring_rationale": "适配现有 hook / task 完成链路，安全性中等，需要 benchmark 再决定是否推广"
}
```

### 12.1 字段表

| 字段 | 类型 | 必填 | 范围 |
|---|---|---|---|
| `signal_score` | `integer` | 是 | `0..100` |
| `fit_score` | `integer` | 是 | `0..100` |
| `safety_score` | `integer` | 是 | `0..100` |
| `eval_score` | `integer` | 是 | `0..100` |
| `novelty_score` | `integer` | 是 | `0..100` |
| `reuse_score` | `integer` | 是 | `0..100` |
| `adoptability_score` | `integer` | 是 | `0..100` |
| `scoring_rationale` | `string` | 是 | 简明结论 |

### 12.2 `adoptability_score` 推荐计算公式

```text
adoptability_score =
0.25 * signal_score +
0.25 * fit_score +
0.20 * safety_score +
0.15 * eval_score +
0.10 * novelty_score +
0.05 * reuse_score
```

取整规则：

- 四舍五入到整数

### 12.3 附加约束

- `tier4` 来源默认不得直接给出高于 `sandbox_eval` 的晋升建议
- `safety_score < 50` 时不得推荐 `draft_asset`
- `eval_score < 40` 时不得推荐跳过 benchmark

## 13. `promotion` 字段定义

```json
{
  "recommendation": "sandbox_eval",
  "recommended_asset_kinds": ["hook", "workflow"],
  "followup_actions": [
    "为 reviewer 流程设计 benchmark",
    "验证 hook 阻断后的反馈文案"
  ],
  "blocking_issues": [
    "缺少真实项目上的吞吐评估"
  ]
}
```

### 13.1 字段表

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `promotion.recommendation` | `string` | 是 | 晋升建议 |
| `promotion.recommended_asset_kinds` | `array<string>` | 否 | 推荐最终落成的资产种类 |
| `promotion.followup_actions` | `array<string>` | 是 | 后续动作 |
| `promotion.blocking_issues` | `array<string>` | 否 | 阻塞项 |

### 13.2 `recommendation` 枚举

- `archive_only`
- `sandbox_eval`
- `draft_asset`
- `human_review_required`
- `reject`

### 13.3 `recommended_asset_kinds` 枚举

- `skill`
- `agent`
- `hook`
- `plugin`
- `workflow`
- `benchmark`
- `doc`

## 14. `evidence` 字段定义

`evidence` 必须至少包含 1 条记录。

```json
[
  {
    "ref_id": "ev-001",
    "ref_type": "url",
    "locator": "https://github.com/example/repo/blob/main/hooks.json",
    "title": "hooks.json",
    "snippet": "TaskCompleted hook blocks completion until validation passes"
  }
]
```

### 14.1 字段表

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `ref_id` | `string` | 是 | 证据 ID |
| `ref_type` | `string` | 是 | 证据类型 |
| `locator` | `string` | 是 | URL、文件路径或引用定位 |
| `title` | `string` | 否 | 证据标题 |
| `snippet` | `string` | 否 | 简短摘录，建议不超过 200 字 |

### 14.2 `ref_type` 枚举

- `url`
- `repo-file`
- `archive-file`
- `summary-note`
- `benchmark-report`

## 15. `audit` 字段定义

```json
{
  "extracted_by": "optimization-agent",
  "extraction_run_id": "run-20260314-001",
  "reviewed_by": "reviewer",
  "reviewed_at": "2026-03-14T04:20:00Z",
  "benchmark_report_ref": "docs/patterns/benchmarks/ptn-example-1a2b3c4d.json",
  "promotion_task_id": "task_123456"
}
```

### 15.1 字段表

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `audit.extracted_by` | `string` | 是 | 抽取执行者 |
| `audit.extraction_run_id` | `string` | 否 | 抽取运行 ID |
| `audit.reviewed_by` | `string` | 否 | 审阅者 |
| `audit.reviewed_at` | `string` | 否 | 审阅时间 |
| `audit.benchmark_report_ref` | `string` | 否 | benchmark 报告引用 |
| `audit.promotion_task_id` | `string` | 否 | 对应的 TaskCenter 任务 ID |

## 16. 归一化规则

所有写入 `PatternCard` 的数据都应先做归一化：

- 时间统一为 UTC ISO8601，格式如 `2026-03-14T04:20:00Z`
- 字符串去首尾空白
- 列表按大小写不敏感去重
- 仓库名统一为 `owner/repo` 小写格式
- 域名统一为小写
- 枚举值统一为小写连字符风格
- 分数统一为整数
- `summary` 保持单段，不允许换行

## 17. 校验规则

### 17.1 Hard Fail

以下情况必须拒绝落卡：

- `schema_version` 非 `pattern-card/v1`
- 缺少任一必填顶层字段
- `pattern_id` 不符合命名规则
- `artifact_type`、`status`、`recommendation` 等枚举非法
- `evidence` 为空
- `source_url` 为空或不是有效 URL
- `upstream_repo` 格式非法但 `source_kind=community-repo`
- 任一分数字段超出 `0..100`

### 17.2 Soft Warning

以下情况允许落卡，但必须产生日志或 warning：

- `license_or_usage_note` 为 `unknown`
- `tier3` / `tier4` 来源缺少二次验证
- `fit_targets` 为空
- `benchmark_report_ref` 缺失但推荐值不是 `archive_only`
- `summary` 超过推荐长度

## 18. 推荐晋升规则

默认规则建议如下：

- `adoptability_score >= 80` 且 `safety_score >= 70`
  - 推荐：`draft_asset` 或 `human_review_required`
- `60 <= adoptability_score < 80`
  - 推荐：`sandbox_eval`
- `40 <= adoptability_score < 60`
  - 推荐：`archive_only`
- `< 40`
  - 推荐：`reject`

但下列规则优先级更高：

- `trust_tier=tier4` 时，最高只能推荐到 `sandbox_eval`
- `side_effect_level=high` 时，必须 `human_review_required`
- 缺少 benchmark 证据时，不得自动进入正式资产

## 19. 最小示例

```json
{
  "schema_version": "pattern-card/v1",
  "pattern_id": "ptn-task-completed-gate-a13f9c2d",
  "status": "reviewed",
  "identity": {
    "title": "Task Completed Hook Gate",
    "artifact_type": "guardrail-pattern",
    "summary": "在任务完成前通过 hook 执行阻断式质量校验。",
    "keywords": ["hook", "task-completed", "guardrail", "quality-gate"],
    "workflow_shape": {
      "primary": "review-loop",
      "tags": ["human-gate", "tool-heavy"]
    }
  },
  "source": {
    "source_kind": "community-repo",
    "source_url": "https://github.com/example/repo",
    "source_domain": "github.com",
    "trust_tier": "tier2",
    "retrieval_method": "github_search",
    "query_hits": ["claude code hooks workflow"],
    "upstream_repo": "example/repo",
    "upstream_ref": "main",
    "captured_at": "2026-03-14T03:40:00Z",
    "published_at": "2026-02-01T00:00:00Z",
    "last_verified_at": "2026-03-14T03:45:00Z",
    "freshness_days": 42,
    "license_or_usage_note": "MIT, 可参考实现"
  },
  "extraction": {
    "problem": "需要在任务完成前强制执行质量门，避免低质量输出直接关闭任务。",
    "trigger_conditions": ["任务进入完成阶段", "存在可执行验证命令"],
    "core_steps": ["拦截完成事件", "执行验证", "失败则阻断", "通过则放行"],
    "strengths": ["能复用现有 hook 面", "反馈链路清晰"],
    "failure_modes": ["验证超时", "误拦截导致循环修复"],
    "anti_patterns": ["只靠 prompt 自检而没有外部阻断"],
    "fit_targets": ["reviewer", "optimization-agent"],
    "not_fit_targets": ["high-frequency-low-value-scan"]
  },
  "contracts": {
    "input_contract": {
      "required_inputs": ["task payload", "quality command"],
      "optional_inputs": ["historical failures"],
      "assumptions": ["运行环境支持 shell 命令"]
    },
    "output_contract": {
      "primary_outputs": ["pass_or_block_decision", "feedback_message"],
      "success_criteria": ["通过时允许完成", "失败时输出明确反馈"],
      "failure_signals": ["validation_timeout", "missing_quality_command"]
    },
    "tooling": [
      {
        "tool_name": "hook-event-handler",
        "required": true,
        "purpose": "拦截任务完成事件"
      },
      {
        "tool_name": "bash",
        "required": true,
        "purpose": "执行验证命令"
      }
    ]
  },
  "operational": {
    "permissions": {
      "mode": "workspace-write",
      "network_required": false,
      "shell_required": true,
      "sensitive_operations": ["task completion gating"]
    },
    "guardrails": [
      {
        "name": "task-completed-gate",
        "scope": "task-completion",
        "mechanism": "hook",
        "blocking": true
      }
    ],
    "runtime_requirements": ["hook runtime", "task-center access", "validation command"],
    "human_gate_required": false,
    "side_effect_level": "medium"
  },
  "scoring": {
    "signal_score": 82,
    "fit_score": 88,
    "safety_score": 74,
    "eval_score": 68,
    "novelty_score": 61,
    "reuse_score": 79,
    "adoptability_score": 78,
    "scoring_rationale": "贴合当前 hook 和任务治理链路，建议先做沙箱评估。"
  },
  "promotion": {
    "recommendation": "sandbox_eval",
    "recommended_asset_kinds": ["hook", "workflow"],
    "followup_actions": ["为 reviewer 链路添加 benchmark", "验证误拦截率"],
    "blocking_issues": ["缺少吞吐评估数据"]
  },
  "evidence": [
    {
      "ref_id": "ev-001",
      "ref_type": "url",
      "locator": "https://github.com/example/repo/blob/main/hooks.json",
      "title": "hooks.json",
      "snippet": "TaskCompleted hook blocks completion until validation passes"
    }
  ],
  "audit": {
    "extracted_by": "optimization-agent",
    "extraction_run_id": "run-20260314-001",
    "reviewed_by": "reviewer",
    "reviewed_at": "2026-03-14T04:20:00Z",
    "benchmark_report_ref": "",
    "promotion_task_id": ""
  }
}
```

## 20. 与后续实现的直接映射

这份规范可以直接对应到后续实现：

- `pattern_extractor.py`
  - 负责构造 `identity/source/extraction/contracts/evidence/audit`
- `pattern_sandbox_eval.py`
  - 负责补充 `scoring` 和 `audit.benchmark_report_ref`
- `pattern_promotion_gate.py`
  - 负责写入 `promotion`、更新 `status`
- `policy_enforcer` / `TaskCenter`
  - 负责消费 `promotion` 结果，把候选模式转成受管任务或资产草案

## 21. 版本升级规则

- 向后兼容的小改动：
  - 增加非必填字段
  - 增加 warning 规则
- 需要升级 `schema_version` 的改动：
  - 删除现有必填字段
  - 修改字段语义
  - 改变枚举值含义
  - 调整顶层结构
