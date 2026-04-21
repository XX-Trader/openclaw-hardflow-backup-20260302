# Hermes 风格记忆蒸馏升级实施规划

> 版本：v1.0 | 2026-04-15
> 架构文档：[Hermes-风格记忆蒸馏升级架构设计.md](Hermes-风格记忆蒸馏升级架构设计.md)

## 1. 实施策略

执行顺序固定为：

`先收口共享技能骨架与宿主契约 -> 再收口热记忆与动作接口 -> 再收口证据存储契约、控制面桥接契约与增量游标 -> 再接入 IDE/多源证据检索 -> 再补宿主内 Parser Agent 解析 -> 再做技能化 -> 最后做迁移切流并接到 OpenClaw 升级反馈主链`

原因：

- 如果先把实现塞进 `openclaw-evolution-upgrader`，就会和“通用技能”目标直接冲突
- 如果先写多源采集，热记忆边界没定，会把错误数据直接灌进长期记忆
- 如果不先定义证据落盘与游标，全量历史一多就只能反复重扫，成本会失控
- 如果先写升级反馈，蒸馏层还没有结构化产物，评分只能继续吃原始日志噪音

## 1.1 重复文件与清理裁决

当前仓库里与“记忆蒸馏”相关的入口不止一套，必须先定边界：

| 路径 | 现状 | 裁决 |
|------|------|------|
| `docs/基础设施/记忆蒸馏/Hermes-风格记忆蒸馏升级/` | 新主方案 | **保留，唯一权威** |
| `docs/基础设施/记忆蒸馏/README.md` | 父级索引 | **保留，但只做入口** |
| `docs/基础设施/记忆蒸馏/architecture.md` | 旧通用骨架 | **保留但冻结，待主实现落地后可归档** |
| `docs/基础设施/记忆蒸馏/implementation-plan.md` | 旧通用骨架 | **保留但冻结，待主实现落地后可归档** |
| `docs/专项场景工作流/AI多端会话跨端捕获引擎/` | 采集侧历史方案 | **保留，但已标记为退役历史文档** |
| `docs/专项场景工作流/记忆知识沉淀工作流/` | 下游消费工作流 | **保留，不删除** |
| `skills/library/ai-session-distiller/` | 旧采集技能 | **已退役删除，旧 cron 入口已移除** |
| `skills/library/memory-vectorization/` | 旧向量化技能 | **已退役删除，旧向量化路径不再保留** |

一句话裁决：

- **已经删掉的**：旧 `ai-session-distiller`、`memory-vectorization` 及其配置引用。
- **现在该改的**：所有仍把 `openclaw-memory/`、`dream_distiller.py`、单宿主落盘当主方案的文档。
- **以后该归档的**：旧通用骨架文档和采集侧历史方案文档。

## 1.2 共享技能 + 宿主内 Agent 裁决

本轮文档完善后，执行边界进一步收口为：

1. **共享技能**：负责候选准备、解析 schema、结果校验、路由落盘、桥接报告输出
2. **Hermes 宿主**：复用 Hermes 内部解析 Agent 处理候选窗口
3. **OpenClaw 宿主**：复用 OpenClaw 内部解析 Agent 处理候选窗口
4. **硬边界**：解析 Agent 只产出 artifact，不能直接改 `USER.md` / `MEMORY.md`
5. **控制面桥接**：所有高价值 artifact 都必须补齐 `trace_id / task_id / run_id`，否则不能进入升级反馈主链

> Parser Agent 调度协议、输入输出 schema、错误处理策略详见 [架构设计](Hermes-风格记忆蒸馏升级架构设计.md) 附录 B。
> 热记忆容量预算详见 [架构设计](Hermes-风格记忆蒸馏升级架构设计.md) 附录 A。
> 敏感信息扫描规则详见 [架构设计](Hermes-风格记忆蒸馏升级架构设计.md) 附录 D。

## 1.3 与项目交付优先工作流的记忆边界裁决

> 2026-04-21 架构评审新增

[项目交付优先工作流](../../核心主工作流/项目交付优先工作流/README.md) 引入了"项目级记忆分仓"（`.workflow/project-memory/<project_key>/`），与本方案的热记忆落点（`USER.md` / `MEMORY.md`）存在潜在双真相源风险。必须在此裁决清楚。

### 裁决结论

| 记忆类型 | 落点 | owner | 更新触发 |
|----------|------|-------|----------|
| 跨项目通用规则（宿主事实、runtime 边界、通用编码纪律） | `USER.md` / `MEMORY.md` | 蒸馏 gateway | cron / 手动蒸馏 |
| 项目级决策、API 来源、交付规则、项目架构经验 | `.workflow/project-memory/<key>/DECISIONS.md` | project-agent | 项目事件 / 手动 |
| 项目级踩坑经验（由蒸馏产出） | 蒸馏先产出 artifact → project-agent 路由到项目记忆 | 蒸馏产出 + project-agent 消费 | 蒸馏完成后 |

### 路由规则

1. `distill_classifier.py` 输出的每条 artifact，如果关联了 `project_key` 字段，则**不写入全局 `MEMORY.md`**，而是输出到蒸馏报告的 `project_routed_artifacts` 列表。
2. `project-agent` 消费蒸馏报告时，把 `project_routed_artifacts` 写入对应项目记忆模块。
3. 没有 `project_key` 的 artifact（跨项目通用经验、宿主事实、runtime 边界）走原有路径进入 `USER.md` / `MEMORY.md`。
4. **同一条经验严禁同时出现在全局记忆和项目记忆中**——蒸馏层是唯一产出源，project-agent 是唯一消费者，不允许两边独立写入。

### project_key 推断逻辑

`distill_classifier.py` 按以下优先级推断 `project_key`：

1. 任务来源的 `task_id` 中显式携带 `project_key`（由 task_center 注入）
2. 证据包中的 `workspace` 路径匹配已注册项目的仓库路径
3. 会话内容中出现已注册项目的名称关键词（模糊匹配，confidence ≥ 0.8 才生效）
4. 以上均未命中 → `project_key = null` → 进入全局记忆

### 对本方案已完成 Phase 的影响

| 受影响组件 | 变更内容 | 紧迫度 |
|-----------|---------|--------|
| `distill_classifier.py` | 增加 `project_key` 推断逻辑和输出字段 | P1 |
| `distill_reporter.py` | 报告 schema 增加 `project_routed_artifacts` 字段 | P1 |
| `memory_write_gateway.py` | 不直接写项目记忆——只负责全局热记忆 | 无变更（已满足） |
| `upgrade_feedback_runner.py` | 消费报告时区分全局 vs 项目路由的 artifacts | P2 |

## 2. 阶段拆分

## Phase 0：文档与冲突收口 ✅ 已完成

### 目标

把 Hermes 风格方案写成正式设计，并把目标收口为跨宿主通用技能，而不是继续停留在口头判断。

### 任务

- [x] 建立子功能目录三件套
- [x] 识别并裁决热记忆落点冲突
- [x] 补齐基础设施目录与 INDEX 入口
- [x] 识别并裁决“OpenClaw 私有脚本”与“跨宿主通用技能”之间的冲突

### 产物

- 本目录三件套
- `docs/INDEX.md`
- `docs/基础设施/README.md`

## Phase 1：共享技能骨架与宿主契约 ✅ 已完成

> 2026-04-15 进度：共享技能骨架、`runtime_probe.py`、`host_adapter_hermes.py`、`host_adapter_openclaw.py` 与基础契约测试已落地。

### 目标

先把主交付物从“单宿主脚本”收口为“共享技能”：

- 共享 `SKILL.md`
- 共享 scripts / config / references
- Hermes 宿主适配接口
- OpenClaw 宿主适配接口

### 新增文件

- `skills/library/cross-runtime-memory-distiller/SKILL.md`
- `skills/library/cross-runtime-memory-distiller/scripts/runtime_probe.py`
- `skills/library/cross-runtime-memory-distiller/scripts/host_adapter_hermes.py`
- `skills/library/cross-runtime-memory-distiller/scripts/host_adapter_openclaw.py`
- `skills/library/cross-runtime-memory-distiller/references/shared-host-contract.md`
- `skills/library/cross-runtime-memory-distiller/references/parser-agent-contract.md`

### 具体步骤

1. 定义宿主无关的核心输入 / 输出契约
2. 实现 `runtime_probe.py`，按宿主分别判定 `windows / linux / wsl`
3. 定义 Hermes / OpenClaw 两侧 `Parser Agent` 的输入输出 schema
4. 定义 Hermes 宿主落点与 OpenClaw 宿主落点
5. 明确共享技能与 `openclaw-evolution-upgrader` 的边界
6. 固化安装 / 调用方式，避免后续再次退回单宿主实现

### 验证点

- Hermes / OpenClaw 两边都能指向同一套共享脚本
- 宿主差异只存在于 adapter 层，不进入核心蒸馏逻辑
- 同一台机器可同时得到 `OpenClaw=Windows`、`Hermes=WSL` 的探测结果
- `Parser Agent Contract` 在 Hermes / OpenClaw 两边都能用同一份 schema 校验
- `--dry-run` 能输出每个宿主最终解析出的路径

## Phase 2：热记忆层与写入网关 ✅ 已完成

### 目标

把最核心的 Hermes 设计落地到共享技能核心：

- `USER.md`
- `MEMORY.md`
- `add/replace/remove`
- 容量预算
- 安全扫描

### 新增文件

- `skills/library/cross-runtime-memory-distiller/scripts/memory_write_gateway.py`
- `skills/library/cross-runtime-memory-distiller/config/memory_limits.json`

### 去重裁决

> **正文 `fingerprints.json` 方案已废弃，统一使用 SQLite `dedup_fingerprints` 表。**
> 参见 [架构设计](Hermes-风格记忆蒸馏升级架构设计.md) 附录 C `dedup_fingerprints` 表定义。

- 去重指纹 = MD5(normalize(title + body))
- normalize: 去除空白差异、标点差异，统一小写，不做中文折叠
- 指纹存储在 `distill.db` 的 `dedup_fingerprints` 表中，与事件/候选/桥接共用同一库
- 写入前先查指纹表，命中则跳过并计入 `duplicates_skipped`
- Phase 3 落地 `evidence_store.py` 时初始化 SQLite，Phase 2 先用独立的小 SQLite 或内存字典做临时存储

### 写前备份机制

不依赖 memtidy 内部函数，独立实现轻量备份：

```python
def backup_file(path: Path, max_backups: int = 3) -> Path:
    """写前备份，保留最近 N 个版本。

    Args:
        path: 要备份的文件
        max_backups: 最多保留几个备份

    Returns:
        备份文件路径
    """
    backup_dir = path.parent / ".memory-backups"
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{path.stem}.{ts}{path.suffix}"
    shutil.copy2(path, backup_path)
    # 清理旧备份
    backups = sorted(backup_dir.glob(f"{path.stem}.*{path.suffix}"))
    for old in backups[:-max_backups]:
        old.unlink()
    return backup_path
```

备份保留策略：最近 3 个版本，自动清理更早的。

### 配置加载策略

```python
import json
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

def load_config(name: str) -> dict:
    """加载 config/ 下的 JSON 配置文件。

    加载优先级：
    1. 环境变量 {NAME}_CONFIG_PATH 指定的路径（覆盖）
    2. config/{name} 文件

    Args:
        name: 配置文件名（如 "memory_limits", "distill_rules"）

    Returns:
        配置字典

    Raises:
        FileNotFoundError: 配置文件不存在
        json.JSONDecodeError: 配置文件格式错误
    """
    env_key = f"{name.upper().replace('.', '_').replace('-', '_')}_CONFIG_PATH"
    env_path = os.environ.get(env_key)
    config_path = Path(env_path) if env_path else CONFIG_DIR / f"{name}.json"
    return json.loads(config_path.read_text(encoding="utf-8"))
```

### 具体步骤

1. 基于 `runtime_probe.py` 定义 `USER.md` 与 `MEMORY.md` 的宿主映射位置
2. 实现 `add/replace/remove` 三种动作（按 [架构设计 §6.6](Hermes-风格记忆蒸馏升级架构设计.md) 文件格式规范解析）
3. 实现唯一子串匹配（按 [架构设计 §6.6.3](Hermes-风格记忆蒸馏升级架构设计.md) 算法）
4. 实现去重（SQLite `dedup_fingerprints` 表）、预算校验（[附录 A](Hermes-风格记忆蒸馏升级架构设计.md)）、写前备份
5. 实现敏感信息扫描（按 [附录 D](Hermes-风格记忆蒸馏升级架构设计.md) 规则）
6. 实现配置加载器

### 验证点

- 同一条内容重复写入不会重复落盘
- `replace/remove` 在多命中时明确报错
- 容量超限时返回当前条目与压缩建议
- 备份文件正确生成且旧备份自动清理
- 含敏感信息的条目被拦截或掩码
- 配置文件不存在时 fail-fast

## Phase 3：IDE 证据优先的多源采集、证据落盘与 Session Search ✅ 已完成

### 目标

把 IDE 与运行时产生的历史证据从”文件堆”变成”可检索、可追溯、可增量处理的证据层”。

### 新增文件

- `distill_source_adapters.py`
- `ingest_cursor_store.py`
- `evidence_store.py`
- `source_repo_delta.py`
- `session_search_index.py`
- `config/storage_policy.json`
- `config/session_search_policy.json`

### 数据源与优先级

> 完整数据源矩阵（字段、作用、接入阶段）详见 [架构设计](Hermes-风格记忆蒸馏升级架构设计.md) §3.4。

优先接入顺序：

1. **P0**：Claude / Gemini / OpenClaw / Hermes 会话 + repo delta + 控制面证据
2. **P1**：todo / done / 功能三件套 / ADR
3. **P2**：PR / issue / review / 部署巡检

### 存储分层

> 完整存储分层策略（6 层：Raw Evidence → Normalized Store → Search Index → Hot Memory → Knowledge Layer → Control-Plane Bridge）详见 [架构设计](Hermes-风格记忆蒸馏升级架构设计.md) §6.4。

SQLite schema 草案见 [架构设计](Hermes-风格记忆蒸馏升级架构设计.md) 附录 C。

### 具体步骤

1. 统一 source adapter 输出事件模型
2. 为每类源定义时间戳、角色、工具输出、元数据的归一化规则
3. 给每个数据源落 `IngestCursor`，确保支持增量抓取与失败续跑
4. 原始数据先写入 `Raw Evidence` 证据包，再写归一化事件层
5. 把代码改动、验证结果和控制面记录整理成 `repo delta evidence + bridge evidence`
6. 建立本地检索索引
7. 输出 `session_search` 查询接口
8. 产出 `control-plane-bridge` 报告，补齐 `trace_id / task_id / run_id`
9. 为检索结果生成短摘要与证据片段

### 验证点

- 同一关键词可跨源命中 Claude / Gemini / Hermes 历史
- 同一技能候选可同时关联 transcript 证据和代码变更证据
- 查询结果不会直接返回整段原始 transcript
- 检索结果带 `source + session_id + summary + snippets`
- 连续两次运行不会重复写入相同证据包
- 任一索引项都能回溯到原始证据包
- 任一高价值 artifact 都能回溯到 `task_id / run_id / trace_id`
- 原始数据不会在 Phase 3 直接全量送入宿主内解析 Agent

## Phase 4：Hermes 风格蒸馏、宿主内 Parser Agent 解析与压缩摘要 ✅ 已完成（规则降级模式）

### 目标

把多源会话变成结构化记忆条目，而不是简单摘抄。

### 新增文件

- `distill_cleaner.py`
- `distill_classifier.py`
- `distill_reporter.py`
- `distill_runner.py`
- `config/distill_rules.json`
- `config/parser_schema.json`

### distill_runner.py CLI 参数

```text
python distill_runner.py \
  --hosts openclaw,hermes                # 要探测的宿主列表
  --sources claude,gemini,openclaw       # 数据源列表（repo_delta/control_plane 默认包含）
  --since-hours 48                       # 回溯时间窗口（小时）
  --db-path ~/.openclaw/ops/distill/distill.db  # SQLite 路径
  --evidence-dir ~/.openclaw/ops/distill/evidence/  # 证据包目录
  --report-dir ~/.openclaw/ops/distill/reports/     # 报告输出目录
  --skip-llm                             # 跳过解析 Agent，使用规则降级分类
  --emit-bridge-report                   # 产出控制面桥接报告
  --dry-run                              # 只探测+打分，不写入热记忆
  --log-level INFO                       # 日志级别
  --log-file /tmp/distill.log            # 日志文件（可选）
  --task-id task_xxx                     # 关联 task_center 任务 ID（可选）
  --trace-id trace_xxx                   # 关联 trace_id（可选）
```

### 具体步骤

1. 先裁剪工具原始输出、心跳、模板化噪音
2. 对候选片段做去重、切片与敏感扫描
3. 先用规则打分决定哪些候选值得进入宿主内 Parser Agent
4. 通过 `host_adapter_hermes.py` 或 `host_adapter_openclaw.py` 调用宿主内部 Parser Agent
5. 采用 Hermes 风格结构化摘要模板
6. 生成 `Goal / Constraints / Progress / Decisions / Files / Next Steps / Critical Context`
7. 把摘要结果分类成：
   - `user`
   - `memory`
   - `experience`
   - `adr`
   - `pattern`
8. 对 Parser Agent 输出做 schema 校验、证据引用校验、预算校验与桥接字段校验
9. 通过 `memory_write_gateway` 或对应路由落盘
10. 对 IDE 经验补充 `changed_files / verification_summary / diff_fingerprint`
11. 对控制面桥接补充 `task_id / run_id / trace_id / agent_id / workspace`

### 验证点

- 结构化摘要字段完整率 ≥ 90%
- 摘要结果可直接用于下一轮蒸馏，而不是重新读原始 transcript
- 热记忆与长尾知识不会混写
- IDE 经验不会只剩聊天摘要，必须保留代码 / 验证侧证据
- 低价值候选会被拦在规则层，不会无脑消耗宿主内解析资源
- 任一结构化条目都带 `evidence_refs`
- 解析 Agent 不直接写热记忆，只输出 artifact

## Phase 5：Pattern -> Skill Draft 升级 ✅ 已完成

### 目标

让 Hermes 的“技能是程序性记忆”原则真正落地。

### 新增文件

- `skill_draft_generator.py`

### 具体步骤

1. 统计 pattern 命中频次
2. 读取来源 evidence，确认不是单次偶发
3. 按 `SKILL.md + scripts/ + references/` 模板生成 draft
4. 生成 `origin.json` 记录触发来源与次数
5. 将 draft 放入共享 skill reports，再由宿主 adapter 安装或登记

### 验证点

- draft 不依赖聊天上下文即可被阅读和审核
- 每个 draft 都能追溯到具体 session evidence

## Phase 6：接入 OpenClaw 升级反馈控制面与迁移切流 ✅ 已完成（基础框架）

### 目标

让共享蒸馏技能和 OpenClaw 升级层形成真正闭环。

### 复用文件

- `upgrade_feedback_runner.py`
- `workflow_upgrade_scoring.py`
- `skill_evolution_review.py`
- `cron/jobs.json`

### upgrade_feedback_runner.py 消费接口

`upgrade_feedback_runner.py` 需要能消费蒸馏产物。新增以下输入契约：

```text
upgrade_feedback_runner.py \
  --input-type distill-report \           # 新增：标识输入类型
  --input-path reports/distill/distill-20260416.json \
  --bridge-path reports/bridge/bridge-20260416.json  # 可选
```

**distill-report.json 中 upgrade_feedback 消费的字段**：

```json
{
  "timestamp": "2026-04-16T12:00:00Z",
  "summary": {
    "total_artifacts": 15,
    "by_kind": {"memory": 5, "experience": 6, "adr": 1, "pattern": 3},
    "hot_memory_writes": 4,
    "hot_memory_bytes_delta": 512,
    "duplicates_skipped": 2,
    "needs_review": 1,
    "parse_failures": 0
  },
  "artifacts": [
    {
      "artifact_id": "distill_20260416_0001",
      "kind": "pattern",
      "title": "SSH 端口冲突修复模式",
      "confidence": 0.85,
      "requires_human_review": false
    }
  ],
  "control_plane_bridge_ids": ["bridge_20260416_0001"],
  "skill_candidates": ["staging-ssh-port-fix"]
}
```

**评分维度新增**：

| 维度 | 评分来源 | 低分阈值 | 回流动作 |
|------|---------|---------|---------|
| 蒸馏质量 | artifact confidence 均值 | < 0.5 | 生成 `workflow_upgrade` 任务优化 prompt |
| 热记忆健康 | 热记忆占用率 | > 80% | 生成 `memory_cleanup` 任务 |
| 模式遗漏 | pattern 触发后未生成 skill | 触发 ≥ 5 次仍为 draft | 标记为 `skill_gap` |
| 记忆污染 | needs_review 积压 | > 10 条未审 | 标记为 `memory_pollution` |

### 具体步骤

1. 定义 `distill-report.json + control-plane-bridge.json` 的标准输出契约
2. 在 bridge layer 中接入 `task_center / executor-runs / upgrade-feedback` 的输入适配
3. 在 upgrade feedback 中增加对 `distill report + bridge report` 的消费逻辑
4. 对“弱模式反复出现”“记忆污染”“热记忆超限”建立评分维度
5. 清理旧 `ai-session-distiller / memory-vectorization` 的文档、配置与残留引用
6. 低分场景自动回流成 `skill_upgrade` / `workflow_upgrade` 任务

### 验证点

- 升级控制面不再直接依赖原始 transcript
- 低分根因可被明确归到 `skill_gap` / `workflow_gap` / `runtime_gap`
- 任一 distill artifact 都能回挂到 `task_id / run_id / trace_id`
- 仓库内不再存在旧 `ai-session-distiller` cron 入口与技能目录硬引用

## 3. 文件级任务清单

| 文件 | 责任 | 阶段 |
|------|------|------|
| `SKILL.md` | 共享技能入口 | P1 |
| `runtime_probe.py` | 逐宿主环境探测与路径解析 | P1 |
| `host_adapter_hermes.py` | Hermes 宿主适配 | P1 |
| `host_adapter_openclaw.py` | OpenClaw 宿主适配 | P1 |
| `memory_write_gateway.py` | 结构化写入与预算控制 | P2 |
| `ingest_cursor_store.py` | 增量游标与失败续跑 | P3 |
| `evidence_store.py` | 原始证据包与归一化事件落盘 | P3 |
| `session_search_index.py` | 多源历史检索 | P3 |
| `distill_source_adapters.py` | Claude/Gemini/OpenClaw/Hermes 源适配 | P3 |
| `source_repo_delta.py` | IDE 代码改动与验证证据采集 | P3 |
| `distill_cleaner.py` | 清洗与工具输出裁剪 | P4 |
| `distill_classifier.py` | 结构化摘要与分类 | P4 |
| `distill_reporter.py` | 产出 distill report | P4 |
| `control_plane_bridge.py` | 产出控制面桥接记录 | P6 |
| `skill_draft_generator.py` | Pattern 升级成 Skill draft | P5 |
| `distill_runner.py` | 主入口与编排 | P4-P6 |

## 4. 防重构破坏策略

1. 不直接改现有 `task_executor_runner.py` 主链
2. 不直接改 `.hermes/state.db`
3. 不把共享技能核心逻辑散落进多个宿主脚本
4. 不把热记忆写入逻辑散落在多个脚本里，统一走 `memory_write_gateway.py`
5. 不让 upgrade feedback 直接读取原始多源 transcript
6. 每完成一个 Phase，都要求可在 `dry-run` 下单独运行

## 5. 验证计划

### 自动化测试

```powershell
pytest tests/scripts_openclaw_ops/test_memory_write_gateway.py -v
pytest tests/scripts_openclaw_ops/test_session_search_index.py -v
pytest tests/scripts_openclaw_ops/test_distill_cleaner.py -v
pytest tests/scripts_openclaw_ops/test_skill_draft_generator.py -v
pytest tests/scripts_openclaw_ops/test_parser_agent_contract.py -v
pytest tests/scripts_openclaw_ops/test_control_plane_bridge.py -v
```

### 集成验证

```powershell
python skills/library/cross-runtime-memory-distiller/scripts/distill_runner.py `
  --hosts hermes,openclaw `
  --sources claude,gemini,openclaw,hermes,repo-delta `
  --since-hours 48 `
  --emit-bridge-report `
  --dry-run
```

### 人工验收

1. 验证 `USER.md` 与 `MEMORY.md` 是否按预算写入
2. 验证 session search 是否能跨源命中真实历史
3. 验证蒸馏摘要是否保留目标、约束、进度、决策、文件和下一步
4. 验证 skill draft 是否可独立阅读
5. 验证 upgrade feedback 是否能消费 distill report

## 6. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Hermes 运行态 schema 后续变化 | WSL 源适配失效 | 只依赖会话导出和摘要接口，避免绑定私有表结构 |
| 热记忆写入过量 | prompt 膨胀、缓存失效 | 强制预算 + replace/remove + 80% 预警 |
| 多源会话格式差异过大 | 归一化失败 | 每个源独立 adapter + golden samples |
| 数据量增长过快 | 全量重扫、索引膨胀、成本失控 | 增量游标 + 分区落盘 + 异步解析 + 冷热分层 |
| 宿主内 Parser Agent 积压 | 延迟变高、费用失控 | 候选打分前置 + 限流队列 + 高低价值分级处理 |
| 宿主内 Parser Agent 不稳定 | 解析超时或 schema 漂移 | 固定 parser schema + timeout + retry + 宿主隔离测试 |
| 技能 draft 质量不稳定 | 误生成低质量 skill | 要求来源证据、次数门槛和人工审核 |
| 压缩摘要丢失关键信息 | 升级反馈误判 | 固定结构化模板 + `Critical Context` 字段强制保留 |

## 7. 实施结论

真正“完全仿照 Hermes”的正确含义是：

- **完全仿照它的记忆方法、压缩方法、技能化方法、缓存保护方法**
- **不复制它的运行态目录、数据库实现和插件内核**
- **把这些方法沉淀成跨宿主可复用的共享技能**

这条边界一旦守住，OpenClaw 就会从“只能消费自己运行时的噪音日志”升级成：

`消费 IDE 经验、共享蒸馏证据、会话检索结果和技能候选的正式升级控制面。`
