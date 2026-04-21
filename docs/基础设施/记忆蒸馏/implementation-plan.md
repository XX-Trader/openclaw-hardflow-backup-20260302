# 知识蒸馏引擎 — 实施计划

> ⛔ **本文档已冻结，不再作为实施依据。**
> 唯一有效的实施规划文档是 [Hermes-风格记忆蒸馏升级/Hermes-风格记忆蒸馏升级实施规划.md](Hermes-风格记忆蒸馏升级/Hermes-风格记忆蒸馏升级实施规划.md)。
> 本文档仅保留作为通用蒸馏流水线的旧骨架参考。

> 版本：v1.0 | 2026-04-02（冻结于 2026-04-15）
> 架构文档：[architecture.md](architecture.md)

## 0. 文档状态裁决

本文不再作为直接排期与编码依据，只保留“通用蒸馏流水线”的旧骨架。以下旧实施口径全部降级：

- 直接在 `skills/library/openclaw-evolution-upgrader/` 下新建蒸馏主实现
- 以 `distill_archiver.py` 为中心的单宿主落盘方案
- 把 `~/.openclaw/memory/` 作为热记忆主写入目标
- 按本文 `Phase 1 ~ Phase 3` 直接开发，而不经过 Hermes 子目录六阶段方案

当前实施应统一以 `Hermes-风格记忆蒸馏升级/` 目录下的实施规划为准。

## 0.1 清理裁决

| 项目 | 当前处理 | 原因 |
|------|----------|------|
| `architecture.md` / `implementation-plan.md` | 保留但冻结 | 仍可作为通用抽象参考，但不能再指导具体实现 |
| `AI多端会话跨端捕获引擎/` 文档 | 保留但降级为“采集侧历史方案” | 只覆盖 source capture，不覆盖存储/热记忆/LLM 主链 |
| `记忆知识沉淀工作流/` 文档 | 保留 | 它是下游消费工作流，不是蒸馏核心设计 |
| `skills/library/ai-session-distiller/` | 已删除 | 旧 cron 入口与实现目录均已退役 |
| `skills/library/memory-vectorization/` | 已删除 | 旧向量化技能与旧蒸馏产物路径绑定已整体退役 |

## 0.2 真正的下一步

后续代码实施只允许做两件事：

1. 先把 `cross-runtime-memory-distiller` 共享技能骨架落地。
2. 再把旧历史文档入口统一改成“历史方案/已退役”，避免继续误导实现。

## 实施策略

按**从内到外、脚本先行**的原则分 3 个阶段：
- Phase 1 打通纯脚本管道（清洗 → 归档 → 报告），不涉及 LLM
- Phase 2 接入 LLM 分类器
- Phase 3 Cron 集成 + 模式识别

## Phase 1：纯脚本管道（预估 2 天）

### Step 1.1 — distill_cleaner.py（会话清洗器）

- [ ] 扫描 `~/.openclaw/agents/*/sessions/` 目录
- [ ] 按 `state.json.last_scan_cutoff` 增量读取新 session
- [ ] 实现 5 条清洗规则（心跳/空回复/重复 stdout/超长输出/系统 prompt）
- [ ] 输出 `fragments[]` 列表，每个包含 source/agent/timestamp/content/context
- [ ] 单元测试：准备 3 个 mock session 文件验证过滤率

### Step 1.2 — distill_archiver.py（归档器 + 去重）

- [ ] 实现 MD5 指纹去重逻辑
- [ ] 实现 FACT 追加写入（按 tag 聚合到对应文件）
- [ ] 实现 EXPERIENCE 追加写入（按主题文件聚合）
- [ ] 指纹库持久化到 `fingerprints.json`
- [ ] 写前备份：复用 memtidy 的 `create_backup()` 函数
- [ ] 单元测试：验证去重（同一内容写 2 次只生效 1 次）

### Step 1.3 — distill_reporter.py（报告器）

- [ ] 生成 JSON 格式报告
- [ ] 生成 Markdown 格式报告
- [ ] 输出到 `~/.openclaw/ops/distill-reports/`

### Step 1.4 — distill_runner.py（入口 + 编排）

- [ ] CLI 参数：`--sessions-dir`, `--state-file`, `--output-dir`, `--dry-run`, `--task-id`
- [ ] 串联：清洗 → （分类占位，默认全标 FACT）→ 归档 → 报告
- [ ] state.json 更新逻辑
- [ ] 集成测试：dry-run 模式下完整跑通

## Phase 2：LLM 分类器（预估 1 天）

### Step 2.1 — distill_classifier.py

- [ ] 构造分类 prompt（FACT / EXPERIENCE / PATTERN / NOISE）
- [ ] 实现批量分类（每批 ≤ 20 片段）
- [ ] 解析 LLM JSON 输出 + 错误重试（最多 2 次）
- [ ] confidence < 0.6 标记 `needs_review`
- [ ] 降级策略：LLM 不可用时 fallback 为全标 FACT

### Step 2.2 — 替换 Phase 1 的占位分类

- [ ] 在 `distill_runner.py` 中接入真实分类器
- [ ] 添加 `--skip-llm` 参数支持纯脚本模式

## Phase 3：Cron 集成 + 模式识别（预估 1 天）

### Step 3.1 — Cron 挂载

- [ ] **方案 A**（推荐）：在现有 `optimize 自我进化总结` Job 的 payload.message 中追加蒸馏步骤
- [ ] **方案 B**：新增独立 Job `knowledge_distillation_daily`
- [ ] 配置 `toolsAllow: ["exec", "read"]` + `lightContext: true`

### Step 3.2 — 模式识别（D5）

- [ ] 实现操作频次统计（读取过去 30 天蒸馏报告累计 PATTERN 计数）
- [ ] 同一操作 ≥ 3 次 → 自动生成 SKILL.md 草稿
- [ ] 草稿存入 `~/.openclaw/ops/distill-reports/skill-candidates/`
- [ ] 通过 Telegram delivery 通知用户确认

## 文件布局（旧骨架，已冻结）

```
skills/library/cross-runtime-memory-distiller/
└── scripts/
    ├── distill_runner.py        # 主入口 [NEW]
    ├── distill_cleaner.py       # 会话清洗 [NEW]
    ├── distill_classifier.py    # LLM 分类 [NEW]
    ├── memory_write_gateway.py  # 受控写入 [NEW]
    ├── session_search_index.py  # 检索层 [NEW]
    └── distill_reporter.py      # 报告生成 [NEW]

config/
└── distill_rules.json           # 蒸馏规则配置 [NEW]
```

> 详细文件拆分与阶段顺序以 Hermes 子目录实施规划为准；这里不再保留单宿主实现落点。

## 验证计划

### 自动化测试

```bash
# Phase 1 单元测试
pytest tests/scripts_openclaw_ops/test_distill_cleaner.py -v
pytest tests/scripts_openclaw_ops/test_distill_archiver.py -v

# Phase 1 集成测试（dry-run）
python3 distill_runner.py \
  --sessions-dir /tmp/mock-sessions/ \
  --state-file /tmp/distill-state.json \
  --output-dir /tmp/distill-reports/ \
  --dry-run
```

### 手动验证

1. 准备 3 个真实 session 文件（复制自远端 `~/.openclaw/agents/ops-agent/sessions/`）
2. 运行 `distill_runner.py --dry-run`
3. 检查报告中的 fragments 分类是否合理
4. 去掉 `--dry-run` 运行，检查 MEMORY.md 是否新增了正确内容
5. 再次运行，确认去重生效（报告中 `duplicates_skipped > 0`）

## 风险与依赖

| 风险 | 缓解措施 |
|------|---------|
| sessions/ 目录结构因版本更新变化 | 清洗器适配多种目录结构，发现未知结构时 warn 而非 crash |
| LLM 分类不准确 | confidence 阈值 + `needs_review` 标记 + `--skip-llm` 降级 |
| MEMORY.md 写入冲突 | 追加模式 + 文件锁 + 写前备份 |
| 远端 sessions 目录权限 | 脚本只需读权限，不涉及 sudo |
