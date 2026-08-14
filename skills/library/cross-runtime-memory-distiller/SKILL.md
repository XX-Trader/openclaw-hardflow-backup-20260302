---
name: cross-runtime-memory-distiller
description: >
  Hermes / OpenClaw 共用的跨宿主记忆蒸馏技能。
  从 Claude / Gemini / OpenClaw / Hermes 多源会话中提取归一化事件，
  经清洗、打分、分类后写入热记忆（USER.md / MEMORY.md），
  同时产出蒸馏报告、控制面桥接记录和技能候选草稿。
---

# Cross Runtime Memory Distiller

跨宿主记忆蒸馏共享技能 — 把 Hermes 已验证的记忆方法论重建为可同时服务 Hermes / OpenClaw 的通用技能。

## 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | ≥ 3.10 | 使用 `match` 语法和 `X \| Y` 类型联合 |
| Git | 任意 | `source_repo_delta` 模块需要，用于采集代码变更 |
| sqlite3 | 内置 | Python 自带，无需额外安装 |

**零第三方依赖** — 所有模块仅使用 Python 标准库（json / sqlite3 / hashlib / re / subprocess / pathlib / argparse / dataclasses / typing）。

## 安装

本技能是纯脚本集合，无需 `pip install`。克隆仓库后直接可用：

```bash
# 1. 克隆仓库（如果还没有）
git clone https://github.com/ORG/workflow-infra.git
cd workflow-infra

# 2. 验证安装
python skills/library/cross-runtime-memory-distiller/scripts/distill_runner.py --help
```

你应该看到完整的参数列表输出。如果看到 `ModuleNotFoundError`，请确认 Python ≥ 3.10：

```bash
python --version
```

### 目录结构

```text
skills/library/cross-runtime-memory-distiller/
├── SKILL.md                           ← 你正在读的文件
├── config/
│   ├── memory_limits.json             热记忆容量预算 + 敏感扫描规则
│   ├── storage_policy.json            证据存储路径与保留策略
│   └── session_search_policy.json     FTS 检索参数
├── scripts/
│   ├── distill_runner.py              ★ 主入口：编排全链路
│   ├── runtime_probe.py               逐宿主环境探测与路径解析
│   ├── host_adapter_hermes.py         Hermes 宿主适配
│   ├── host_adapter_openclaw.py       OpenClaw 宿主适配
│   ├── memory_write_gateway.py        热记忆写入网关
│   ├── evidence_store.py              SQLite 证据存储
│   ├── distill_source_adapters.py     多源数据适配器
│   ├── source_repo_delta.py           IDE 代码变更证据采集
│   ├── distill_cleaner.py             清洗 + 候选窗口切分 + 打分
│   ├── distill_classifier.py          分类 + 结构化摘要生成
│   ├── distill_reporter.py            蒸馏报告 + 控制面桥接报告
│   ├── skill_draft_generator.py       Pattern → 已有技能追加更新 / 新建草稿
│   └── skill_indexer.py               全平台技能索引（搜索/差异/对比）
└── references/
    ├── shared-host-contract.md        宿主契约
    └── parser-agent-contract.md       Parser Agent 契约
```

## 快速启动

### 第一步：探测模式（零副作用）

第一次使用建议先用 `--dry-run`，只做探测和打分，不写入任何文件：

```bash
python skills/library/cross-runtime-memory-distiller/scripts/distill_runner.py \
  --hosts openclaw \
  --sources claude,docs \
  --since-hours 48 \
  --dry-run
```

你会看到类似输出：

```json
{
  "timestamp": "2026-04-20T...",
  "status": "success",
  "summary": {
    "total_artifacts": 15,
    "high_value": 8,
    "index_only": 5,
    "skip": 2
  },
  "elapsed_seconds": 1.2
}
```

### 第二步：正式蒸馏

确认 dry-run 输出正常后，去掉 `--dry-run` 执行正式蒸馏：

```bash
# Windows PowerShell
python skills/library/cross-runtime-memory-distiller/scripts/distill_runner.py `
  --hosts openclaw `
  --sources claude,docs `
  --since-hours 48 `
  --emit-bridge-report `
  --workspace "C:/workspace/workflow-infra" `
  --report-dir "$HOME/.openclaw/ops/distill/reports"

# Linux / macOS / WSL
python skills/library/cross-runtime-memory-distiller/scripts/distill_runner.py \
  --hosts openclaw \
  --sources claude,docs \
  --since-hours 48 \
  --emit-bridge-report \
  --workspace "$HOME/GitHub/workflow-infra" \
  --report-dir ~/.openclaw/ops/distill/reports
```

蒸馏完成后，产物保存在：

```text
~/.openclaw/ops/distill/
├── distill.db                    SQLite 主库
├── reports/
│   ├── distill-20260420.json     蒸馏报告
│   └── bridge-20260420.json      控制面桥接报告
└── skill-candidates/             自动生成的技能草稿
```

### 第三步：手动写入热记忆（可选）

如果你想手动写入一条记忆到 USER.md 或 MEMORY.md：

```bash
python skills/library/cross-runtime-memory-distiller/scripts/memory_write_gateway.py \
  --action add \
  --target user \
  --content "- 偏好中文回复，技术文档使用中文注释" \
  --title "语言偏好" \
  --hot-memory-path ~/.openclaw/workspace/USER.md \
  --dry-run
```

去掉 `--dry-run` 后实际写入。写入网关会自动执行：去重检查 → 敏感信息扫描 → 容量预算校验 → 写前备份 → 写入。

### 第四步：技能索引（管理已有技能）

```bash
# 扫描全平台技能并生成索引
python skills/library/cross-runtime-memory-distiller/scripts/skill_indexer.py \
  --workspace "C:/workspace/workflow-infra" \
  --output skill-index.json

# 搜索技能
python skills/library/cross-runtime-memory-distiller/scripts/skill_indexer.py --search "deploy"
python skills/library/cross-runtime-memory-distiller/scripts/skill_indexer.py --search "蒸馏"

# 对比差异（新增/删除/变更）
python skills/library/cross-runtime-memory-distiller/scripts/skill_indexer.py \
  --workspace "C:/workspace/workflow-infra" \
  --output skill-index.json --diff
```

## 全部参数

```
distill_runner.py:
  --hosts              逗号分隔的宿主列表 (默认: openclaw,hermes)
  --sources            逗号分隔的数据源 (claude,gemini,openclaw,hermes,docs)
  --since-hours        回溯时间窗口（小时），默认 48
  --db-path            distill.db 路径 (默认: ~/.openclaw/ops/distill/distill.db)
  --report-dir         报告输出目录 (默认: ~/.openclaw/ops/distill/reports)
  --evidence-dir       证据包目录
  --classifier         确定性分类器（当前支持 rules）
  --skip-llm           旧版兼容参数，等同于 --classifier rules
  --emit-bridge-report 产出控制面桥接报告
  --dry-run            只探测+打分，不写入热记忆
  --workspace          工作区路径（用于 repo delta 采集代码变更）
  --task-id            关联任务 ID
  --trace-id           关联追溯 ID
  --log-level          日志级别 (INFO/DEBUG/WARNING)
  --log-file           日志文件路径

memory_write_gateway.py:
  --action             add | replace | remove
  --target             user | memory
  --content            写入内容
  --old-text           replace/remove 时匹配的旧文本
  --title              条目标题（用于去重指纹）
  --hot-memory-path    热记忆文件路径
  --db-path            distill.db 路径（用于去重记录）
  --dry-run            只校验不写入
```

## 数据源说明

| 数据源 | `--sources` 值 | 探测路径 | 说明 |
|--------|---------------|----------|------|
| Claude 会话 | `claude` | `~/.claude/projects/` 下的 JSONL 文件 | 自动发现所有项目会话 |
| Gemini Brain | `gemini` | `~/.gemini/antigravity/brain/` | Markdown 和 JSON 产物 |
| OpenClaw 会话 | `openclaw` | `~/.openclaw/sessions/` 下的 JSONL | OpenClaw agent 运行记录 |
| Hermes 会话 | `hermes` | WSL `/home/runtime-user/.hermes/sessions/` | 通过 UNC 路径读取 |
| 仓库文档 | `docs` | `--workspace` 下的 `docs/**/*.md` + `todo.md` + `done.md` | 需指定 `--workspace` |

多数据源可自由组合：`--sources claude,gemini,docs`

## 配置文件

所有配置文件位于 `config/` 目录，支持环境变量覆盖。

| 配置 | 文件 | 环境变量覆盖 | 作用 |
|------|------|-------------|------|
| 热记忆预算 | `config/memory_limits.json` | `MEMORY_LIMITS_CONFIG_PATH` | USER.md 2KB / MEMORY.md 8KB 预算 + 敏感扫描规则 |
| 存储策略 | `config/storage_policy.json` | `STORAGE_POLICY_CONFIG_PATH` | 证据存储路径与保留策略 |
| 检索策略 | `config/session_search_policy.json` | `SESSION_SEARCH_POLICY_CONFIG_PATH` | FTS 检索参数 |

覆盖示例：

```bash
# 使用自定义配置
MEMORY_LIMITS_CONFIG_PATH=/path/to/my-limits.json \
python skills/library/cross-runtime-memory-distiller/scripts/distill_runner.py --dry-run
```

## 运行测试

```bash
# 运行全部 78 个测试
python -m pytest tests/scripts_openclaw_ops/test_memory_write_gateway.py -v
python -m pytest tests/scripts_openclaw_ops/test_cross_runtime_memory_distiller_phase3to5.py -v

# 运行 Phase 1 契约测试
python -m pytest tests/scripts_openclaw_ops/test_cross_runtime_memory_distiller_phase1.py -v
```

## 蒸馏链路

```
Source Pull → Raw Landing → Normalize → Clean/Dedupe/Segment → Candidate Scoring
  → (high value) Classify → Post-Validation → Route + Store + Index
  → (low value) Index Only
  → Control-Plane Bridge → Report
```

## 硬边界

- 不直接改 `upgrade_feedback_runner.py` 主链
- 不直接改 `.hermes/state.db`
- 解析 Agent 只产出 artifact，不直接写 USER.md / MEMORY.md
- 热记忆写入统一走 `memory_write_gateway.py`
- 原始 transcript 不直接送入解析 Agent，必须先清洗打分
- 所有敏感信息写前扫描，prompt injection 直接拒绝

## 常见问题

**Q: 报 `ModuleNotFoundError: No module named 'utf8_runtime'`**
A: 这是正常的，`distill_runner` 会尝试加载仓库共享的 UTF-8 运行时模块，找不到时自动降级，不影响功能。

**Q: 蒸馏后没有事件？**
A: 检查 `--since-hours` 是否足够大，以及 Claude/Gemini 数据路径是否存在。`claude` 源需要 `~/.claude/projects/` 下有 JSONL 文件。

**Q: 想只蒸馏特定项目？**
A: 目前是全量扫描后按时间窗口过滤。你可以通过 `--since-hours` 缩小范围，或手动指定更精确的路径。

## 参考文档

- `references/shared-host-contract.md` — 宿主契约
- `references/parser-agent-contract.md` — Parser Agent 契约
