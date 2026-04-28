# 知识蒸馏引擎 — 架构设计

> ⛔ **本文档已冻结，不再作为实施依据。**
> 唯一有效的架构设计文档是 [Hermes-风格记忆蒸馏升级/Hermes-风格记忆蒸馏升级架构设计.md](Hermes-风格记忆蒸馏升级/Hermes-风格记忆蒸馏升级架构设计.md)。
> 本文档仅保留作为通用蒸馏流水线的抽象参考。

> 版本：v1.0 | 2026-04-02（冻结于 2026-04-15）
> 需求文档：[README.md](README.md)

## 0. 文档状态裁决

本文已降级为**通用骨架说明**，不再作为具体实现蓝图。以下旧口径全部作废：

- `~/.openclaw/memory/` 作为热记忆第一落点
- 直接把蒸馏实现塞进 `openclaw-evolution-upgrader` 作为主交付物
- 以 `distill_archiver.py` 为中心的单宿主落盘模型

当前唯一有效的详细实施方案是：

- `docs/基础设施/记忆蒸馏/Hermes-风格记忆蒸馏升级/README.md`
- `docs/基础设施/记忆蒸馏/Hermes-风格记忆蒸馏升级/Hermes-风格记忆蒸馏升级架构设计.md`
- `docs/基础设施/记忆蒸馏/Hermes-风格记忆蒸馏升级/Hermes-风格记忆蒸馏升级实施规划.md`

## 1. 系统全景

```
                    Cron 触发（每日 04:37）
                           │
                           ▼
            ┌──────────────────────────┐
            │  distill_runner.py       │
            │  (蒸馏引擎入口)           │
            └──────┬───────────────────┘
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
┌────────┐   ┌──────────┐   ┌────────────┐
│ Step 1 │   │ Step 2   │   │ Step 3-4   │
│ 清洗   │   │ 分类     │   │ 归档+去重  │
│        │   │          │   │            │
│ 纯脚本 │   │ LLM 辅助 │   │ 纯脚本    │
└───┬────┘   └────┬─────┘   └─────┬──────┘
    │             │               │
    ▼             ▼               ▼
  噪声过滤     分类清单       写入目标层
  统计报告    (事实/经验/     MEMORY.md
             模式)          experience/
                            Skill 草稿
```

## 2. 数据流

### 2.1 输入：Agent 会话目录

```
~/.openclaw/agents/*/sessions/
├── coordinator/sessions/
│   ├── 2026-04-01_task_abc.md
│   └── 2026-04-02_task_def.md
├── ops-agent/sessions/
│   ├── 2026-04-01_patrol.md
│   └── ...
└── ...
```

每个 session 文件是一次 Agent 执行记录，包含：
- 用户指令 / 系统 prompt
- Agent 推理过程
- 工具调用和输出（stdout/stderr）
- 最终回复

### 2.2 清洗规则（Step 1 — 纯脚本）

| 过滤目标 | 匹配模式 | 说明 |
|----------|---------|------|
| 心跳/空回复 | `NO_REPLY`、空字符串 | Cron 任务的静默输出 |
| 重复 stdout | 连续相同 > 3 行 | 脚本大量输出 |
| 工具 raw output | `> Tool output: ...`（超 200 行） | 保留前 10 行摘要 |
| 系统 prompt | `<system>...</system>` | 无信息量 |
| 模板化回复 | 纯格式化表格/无实际数据 | 低价值 |

清洗后得到 **有效片段列表**，每个片段包含：
```json
{
  "source": "ops-agent/sessions/2026-04-02_patrol.md",
  "agent": "ops-agent",
  "timestamp": "2026-04-02T03:00:00Z",
  "content": "发现 /var/log/trader/ 磁盘使用超 80%，执行了日志轮转...",
  "context": "定时巡检任务 todo_patrol"
}
```

### 2.3 分类规则（Step 2 — LLM 辅助）

给 LLM 一个结构化 prompt，让它对每个有效片段分类：

```
请将以下片段分类为以下之一：
- FACT: 可直接引用的事实（项目路径、端口、命令、配置值）
- EXPERIENCE: 可复用的经验（排障方法、最佳实践、踩坑记录）
- PATTERN: 重复出现的操作模式（同一流程出现 ≥ 2 次）
- NOISE: 无价值内容（跳过）

对每个非 NOISE 片段，输出 JSON：
{
  "category": "FACT | EXPERIENCE | PATTERN",
  "title": "一句话标题",
  "body": "提炼后的结构化内容",
  "tags": ["项目名", "领域"],
  "confidence": 0.0-1.0
}
```

**安全约束**：
- `confidence < 0.6` 的条目标记为 `needs_review`，不自动写入
- 每次 LLM 调用限制输入 ≤ 20 个片段，避免上下文膨胀

### 2.4 归档目标层与复用闭环（Step 3 — 通用骨架）

蒸馏引擎只负责**写入**，写入后需要打通 Agent 的**读取复用**闭环：

| 分类 | 目标位置 | 写入与复用策略 |
|------|---------|---------|
| FACT | `workspace/USER.md` / `workspace/MEMORY.md` | **写入**：只把稳定、高价值、长期有效的事实写入热层；旧 `openclaw-memory/` 仅保留兼容/归档语义 |
| EXPERIENCE | `.workflow/experience/` | **写入**：按主题聚合，检索时通过摘要或索引引用，不再强依赖向 `MEMORY.md` 追加冗长索引 |
| PATTERN | `skill drafts/` + `reports/skill-candidates/` | **写入**：生成 Skill draft 与来源证据，人工确认后再正式安装 |

### 2.5 去重策略（Step 4 — 纯脚本）

```python
# 去重指纹 = MD5(normalize(title + body))
def normalize(text: str) -> str:
    """去除空白、标点差异，统一小写后取指纹。"""
    return re.sub(r'\s+', ' ', text.lower().strip())
```

- 指纹库存储在 `~/.openclaw/ops/distill-state/fingerprints.json`
- 同一指纹只写入一次
- 指纹库定期清理（> 90 天的旧指纹自动移除）

## 3. 核心数据结构

### 3.1 蒸馏状态文件

```json
// ~/.openclaw/ops/distill-state/state.json
{
  "version": 1,
  "last_run": "2026-04-02T04:37:00Z",
  "last_scan_cutoff": "2026-04-01T04:37:00Z",
  "total_sessions_processed": 156,
  "total_facts_written": 42,
  "total_experiences_written": 18,
  "total_patterns_detected": 3,
  "fingerprint_count": 63
}
```

### 3.2 蒸馏报告

```json
// ~/.openclaw/ops/distill-reports/distill-20260402.json
{
  "timestamp": "2026-04-02T04:37:00Z",
  "sessions_scanned": 12,
  "fragments_extracted": 28,
  "fragments_after_filter": 11,
  "classification": {
    "FACT": 5,
    "EXPERIENCE": 3,
    "PATTERN": 1,
    "NOISE": 2
  },
  "written": {
    "facts": 4,
    "experiences": 2,
    "patterns": 1
  },
  "duplicates_skipped": 2,
  "needs_review": 1,
  "items": [...]
}
```

## 4. 模块拆分（以跨宿主共享技能为准）

| 模块 | 文件 | 职责 | LLM 依赖 |
|------|------|------|:--------:|
| 宿主探测 | `runtime_probe.py` | 逐宿主解析路径与运行环境 | ❌ |
| 源适配器 | `distill_source_adapters.py` | 多源会话 / 工件 / 验证证据归一化 | ❌ |
| 清洗器 | `distill_cleaner.py` | 过滤噪声、切片、去重、敏感扫描 | ❌ |
| 分类器 | `distill_classifier.py` | 调用 LLM 做结构化提取 | ✅ |
| 写入网关 | `memory_write_gateway.py` | 受控写入热记忆与知识层 | ❌ |
| 检索层 | `session_search_index.py` | 建立检索索引与摘要缓存 | ❌ |
| 报告器 | `distill_reporter.py` | 生成 JSON + MD 报告 | ❌ |
| 入口 | `distill_runner.py` | 端到端编排 | ❌ |

> 当前以共享技能骨架为准；旧 `distill_archiver.py` 命名和单宿主文件布局不再作为推荐实现。

## 5. 与现有系统的关系

```
┌─────────────────────────────────────────┐
│ 已有                                     │
│                                         │
│ Hermes 原生记忆整理 → 文件层面整理        │
│ optimize_incremental_scan.py → 变更扫描 │
│ Cron: optimize 自我进化总结             │
│                                         │
├─────────────────────────────────────────┤
│ 新增 / 继承                              │
│                                         │
│ 共享蒸馏技能 → 知识层面蒸馏              │
│ runtime_probe/source adapters           │
│ distill_cleaner / classifier            │
│ memory_write_gateway / session_search   │
│ distill_reporter / distill_runner       │
│                                         │
│ 由 Hermes / OpenClaw 宿主适配器调用      │
│ upgrade feedback 只消费结构化产物        │
└─────────────────────────────────────────┘
```

## 6. 安全与约束

| 约束 | 说明 |
|------|------|
| 只读会话 | 绝不修改/删除 sessions/ 下的原始文件 |
| LLM 成本控制 | 单次分类限 20 片段；confidence < 0.6 不写入 |
| 写前备份 | 修改 MEMORY.md 前先备份，使用蒸馏模块自带轻量备份或 Hermes 原生备份能力 |
| 人工确认 | PATTERN → Skill 升级必须经人确认 |
| 幂等执行 | 指纹去重保证重复运行不产生重复知识 |
| Fail-Fast | 任何 I/O 错误立即终止 + 报告，不静默跳过 |
