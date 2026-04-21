# Hermes 风格记忆蒸馏升级架构设计

> 版本：v1.0 | 2026-04-15
> 需求文档：[README.md](README.md)

## 1. 设计目标

本设计要解决的不是“怎么再写一个蒸馏脚本”，而是：

`怎样把 Hermes 已验证过的记忆与上下文管理方案，重建为一个可同时服务 Hermes / OpenClaw 的通用技能，并能优先吸收 IDE 中产生的真实编码经验。`

目标拆成六条：

1. 让热记忆落点与上下文注入模型稳定下来
2. 让 IDE 主导开发产生的经验可以稳定进入蒸馏主链
3. 让多源会话进入检索层，而不是污染长期记忆
4. 让技能成为程序性记忆的正式出口
5. 让压缩摘要与缓存策略可复用
6. 让 OpenClaw 升级技能只消费结构化证据，并与 `task_center / executor-runs / upgrade-feedback` 对齐

## 2. 证据与冲突裁决

> 裁决结论和背景详见 [README.md](README.md) §2。

### 2.1 Hermes 官方给出的稳定模式

- 持久记忆由 `MEMORY.md` 与 `USER.md` 构成，并有明确字符预算（详见附录 A）
- 会话开始时把记忆作为**冻结快照**注入系统提示词
- 运行中通过 `add / replace / remove` 受控更新记忆，写盘立即生效，但当前会话前缀不变
- 所有历史会话进入 `session_search` 检索层，而不是自动并入长期记忆
- 技能是首选扩展方式，适合承载程序性知识
- 上下文压缩有结构化摘要模板、双层压缩和前缀缓存保护

## 3. 总体架构

```text
Windows/WSL IDE 与运行时证据
├── Claude Code: ~/.claude/transcripts/*.jsonl
├── Gemini: ~/.gemini/antigravity/brain/**
├── OpenClaw: ~/.openclaw/agents/*/sessions/*.jsonl
├── Hermes: /home/ubuntu/.hermes/sessions + state.db
├── Repo Delta Sidecar
│   ├── git diff / changed files
│   ├── 验证命令与测试结果
│   └── 关键产物路径
└── Control Plane Sidecar
    ├── task_center.db
    ├── executor-runs/*.json
    └── upgrade-feedback reports
          │
          ▼
Shared Distillation Skill
├── Source Adapters
│   ├── source_claude.py
│   ├── source_gemini.py
│   ├── source_openclaw.py
│   ├── source_hermes.py
│   └── source_repo_delta.py
├── Normalize + Clean
│   ├── 统一事件模型
│   ├── 工具输出裁剪
│   ├── 冗余片段去重
│   └── 敏感信息扫描
├── Candidate Pack Builder
│   ├── parser-agent contract
│   ├── target schema
│   └── retry / timeout / confidence policy
├── Memory Router
│   ├── USER 路由
│   ├── MEMORY 路由
│   ├── EXPERIENCE 路由
│   ├── ADR 路由
│   └── PATTERN -> Skill Draft 路由
├── Control Plane Bridge
│   ├── trace_id / task_id / run_id linkage
│   └── bridge-report output
└── Session Search Index
    ├── FTS / 向量 / 摘要缓存
    └── 按需召回，不进入热前缀
          │
          ▼
Host Adapters
├── Hermes Adapter
│   ├── Hermes Parser Agent
│   ├── USER.md / MEMORY.md
│   ├── session_search
│   └── skill output
└── OpenClaw Adapter
    ├── OpenClaw Parser Agent
    ├── workspace/USER.md / MEMORY.md
    ├── .workflow/experience/ + docs/adr/
    ├── distill reports
    └── upgrade feedback inputs
```

## 3.1 IDE 第一现场原则

用户已明确日常主要在 IDE 中完成编码，因此“经验”不能只从 OpenClaw 自己的 runtime 里提。

本设计正式采用双证据模型：

1. **会话/工件证据**
   - Claude transcript
   - Gemini artifact
   - Hermes / OpenClaw session
2. **代码/验证证据**
   - 改动文件列表
   - 关键 diff
   - 测试、构建、验证结果
   - 最终输出产物

只有把这两类证据拼起来，才能把“IDE 中形成的真实经验”蒸馏成可复用能力，而不是空泛聊天摘要。

## 3.2 宿主环境探测与路径解析协议

这个问题不能简化成“当前脚本跑在 Windows 还是 Linux”。  
必须改成：

`对 Hermes 和 OpenClaw 分别做 runtime probe，再各自决定使用哪套路径。`

原因很简单：

- 同一台机器上可能是 `OpenClaw = Windows 原生`
- 同时又是 `Hermes = WSL Ubuntu`
- 如果按“当前进程 OS”全局判断，路径一定会串

### 3.2.1 基本原则

1. **逐宿主探测，不做全局假设**
2. **显式配置优先，自动探测兜底**
3. **路径解析结果要结构化输出，不能藏在 adapter 内部黑箱里**
4. **探测到 WSL 时，优先使用该 distro 内的 POSIX 路径，不把 Windows 路径硬翻译成 Linux 路径**
5. **读写动作跟随宿主环境走，禁止跨环境直接写错路径**

### 3.2.2 探测优先级

每个宿主都按以下优先级解析：

1. CLI 参数显式指定
2. 环境变量显式指定
3. 宿主适配器配置文件
4. 自动探测默认路径
5. 探测失败则 fail-fast

### 3.2.3 `RuntimeProbeResult`

建议把探测结果统一成一个对象，供 `host_adapter_hermes.py` 和 `host_adapter_openclaw.py` 共用：

```json
{
  "host": "hermes | openclaw",
  "runtime_kind": "windows | linux | wsl",
  "transport": "native_fs | wsl_exec | unc_readonly",
  "distro": "Ubuntu",
  "home": "/home/ubuntu",
  "session_roots": ["/home/ubuntu/.hermes/sessions"],
  "hot_memory_paths": {
    "user": "/home/ubuntu/.hermes/memories/USER.md",
    "memory": "/home/ubuntu/.hermes/memories/MEMORY.md"
  },
  "workspace_roots": [],
  "state_db": "/home/ubuntu/.hermes/state.db"
}
```

### 3.2.4 默认路径矩阵

| 宿主 | runtime_kind | 默认会话路径 | 默认热记忆路径 | 备注 |
|------|--------------|--------------|----------------|------|
| OpenClaw | `windows` | `%USERPROFILE%\\.openclaw\\agents\\*\\sessions\\*.jsonl` | `%USERPROFILE%\\.openclaw\\workspace*\\USER.md` / `MEMORY.md` | 当前本机主要形态 |
| OpenClaw | `linux/wsl` | `~/.openclaw/agents/*/sessions/*.jsonl` | `~/.openclaw/workspace*/USER.md` / `MEMORY.md` | Linux 或 WSL 内运行 |
| Hermes | `wsl/linux` | `~/.hermes/sessions` | `~/.hermes/memories/USER.md` / `MEMORY.md` | 当前本机主要形态 |
| Hermes | `windows` | `%USERPROFILE%\\.hermes\\sessions` | `%USERPROFILE%\\.hermes\\memories\\USER.md` / `MEMORY.md` | 作为未来兼容兜底，不假设当前存在 |

### 3.2.5 当前推荐实现

当前这台机器最可能出现的混合形态是：

- `Claude / Gemini / OpenClaw` 在 Windows 用户目录
- `Hermes` 在 WSL `Ubuntu`

因此 runtime probe 必须支持这种结果：

```json
{
  "openclaw": {
    "runtime_kind": "windows"
  },
  "hermes": {
    "runtime_kind": "wsl",
    "distro": "Ubuntu"
  }
}
```

### 3.2.6 与宿主适配器的边界

- `runtime_probe.py` 负责判定宿主环境和标准路径
- `host_adapter_hermes.py` 负责在 Hermes 宿主内读写
- `host_adapter_openclaw.py` 负责在 OpenClaw 宿主内读写
- 共享核心逻辑永远只接收 `RuntimeProbeResult`，不直接拼硬编码路径

### 3.2.7 宿主内 Parser Agent 解析协议

本设计正式裁决：

`共享技能不在核心脚本里裸调模型，而是把高价值候选窗口交给宿主内部 Agent 解析。`

执行方式如下：

1. `host_adapter_hermes.py` 负责把候选窗口封装成 `ParserCandidatePacket`，交给 Hermes 内部解析 Agent
2. `host_adapter_openclaw.py` 负责把候选窗口封装成 `ParserCandidatePacket`，交给 OpenClaw 内部解析 Agent
3. 共享技能核心只负责：
   - 候选窗口准备
   - 解析 schema 与 prompt 模板版本
   - 重试 / 超时 / 置信度策略
   - 输出校验与路由落盘
4. 解析 Agent 只允许产出结构化 artifact，**不允许直接写 `USER.md` / `MEMORY.md`**

建议输入对象如下：

```json
{
  "candidate_id": "cand_20260415_001",
  "host": "hermes | openclaw",
  "project": "openclaw-hardflow-backup-20260302",
  "trace_id": "trace_abc123",
  "task_id": "task_xyz789",
  "run_id": "run_456",
  "source": "claude | gemini | openclaw | hermes | repo_delta | control_plane",
  "evidence_refs": ["bundle_claude_001:12-44"],
  "window_text": "候选窗口正文",
  "target_schema_version": "2026-04-15"
}
```

建议输出对象如下：

```json
{
  "artifact_id": "distill_20260415_001",
  "kind": "user | memory | experience | adr | pattern | noise",
  "title": "一句话标题",
  "summary": "结构化摘要",
  "rationale": "为什么值得沉淀",
  "evidence_refs": ["bundle_claude_001:12-44"],
  "confidence": 0.91,
  "target_kind": "knowledge | hot_memory | bridge_only",
  "trace_id": "trace_abc123",
  "task_id": "task_xyz789",
  "run_id": "run_456",
  "requires_human_review": false
}
```

### 3.2.8 WSL 执行协议

当 `runtime_probe` 判定某个宿主运行在 WSL 中时，Windows 侧 Python 需要通过 `wsl.exe` 桥接执行。

**基本原则**：

1. 所有 WSL 命令通过 `subprocess.run(["wsl", "-d", distro, "--", ...])` 执行
2. 文件读写优先使用 UNC 路径 (`\\wsl$\{distro}\...`) 进行只读访问
3. 写入操作必须通过 `wsl` 命令执行，不通过 UNC 路径写（避免编码和原子性问题）
4. 禁止使用 `wslpath` 做路径转换，直接使用 WSL 内的 POSIX 路径

**执行模板**：

```python
import subprocess
from typing import Any

def run_wsl_command(
    distro: str,
    command: list[str],
    timeout: int = 60,
    cwd: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """在指定 WSL 发行版内执行命令。

    Args:
        distro: WSL 发行版名称（如 "Ubuntu"）
        command: 要在 WSL 内执行的命令列表
        timeout: 超时秒数
        cwd: WSL 内的工作目录（POSIX 路径）

    Returns:
        subprocess.CompletedProcess 实例

    Raises:
        subprocess.TimeoutExpired: 命令超时
        subprocess.CalledProcessError: 命令返回非零退出码（check=True 时）
        FileNotFoundError: wsl.exe 不存在
    """
    wsl_args = ["wsl", "-d", distro, "--"]
    if cwd:
        wsl_args.extend(["bash", "-c", f"cd '{cwd}' && {' '.join(command)}"])
    else:
        wsl_args.extend(command)

    return subprocess.run(
        wsl_args,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )
```

**文件读取模板**（只读 UNC）：

```python
from pathlib import Path

def wsl_file_read(distro: str, posix_path: str) -> str | None:
    """通过 UNC 路径只读访问 WSL 文件。

    Returns:
        文件内容字符串，文件不存在时返回 None
    """
    unc_path = Path(f"\\\\wsl$\\{distro}") / posix_path.lstrip("/")
    if not unc_path.exists():
        return None
    return unc_path.read_text(encoding="utf-8", errors="replace")
```

**安全约束**：

- 超时必须设置，默认 60 秒，解析 Agent 调用默认 120 秒
- WSL 命令中禁止拼接未转义的用户输入
- 捕获 stderr 并记录到蒸馏报告
- WSL 不可用时 fail-fast，不静默降级

### 3.3 端到端数据链路

真正可落地的蒸馏链路不应是“抓到 transcript -> 直接丢给解析 Agent -> 写记忆”。  
必须拆成下面 9 层：

```text
Source Pull
  -> Raw Landing
  -> Normalize
  -> Clean / Dedupe / Segment
  -> Candidate Scoring
  -> Host Parser Agent Structured Extraction
  -> Post-Validation
  -> Route + Store + Index
  -> Control-Plane Bridge
  -> Retrieval + Upgrade Feedback
```

每层职责如下：

1. **Source Pull**
   - 按宿主与 source adapter 抓增量数据
   - 为每个数据源维护游标、mtime、水位线、session_id 集合
2. **Raw Landing**
   - 原始数据先以追加式证据包落盘
   - 每个证据包都带 `source / host / project / session_id / collected_at`
3. **Normalize**
   - 转成统一事件模型：消息、工具调用、工件、代码变更、验证结果
4. **Clean / Dedupe / Segment**
   - 先剔除无价值片段，再切成适合检索和提取的窗口
5. **Candidate Scoring**
   - 对候选窗口按“可复用性、稳定性、证据完整度、敏感风险”打分
   - 低分窗口只进入检索层，不进入解析 Agent
6. **Host Parser Agent Structured Extraction**
   - 只处理高分候选窗口
   - 由 Hermes / OpenClaw 宿主内 Agent 输出严格 schema，而不是自由文本总结
7. **Post-Validation**
   - 校验 schema、证据引用、预算、宿主与桥接字段完整性
   - 低置信度或互斥结论进入仲裁队列
8. **Route + Store + Index**
   - 按类型写入热记忆、经验层、ADR、Skill Draft、Session Search Index、报告层
9. **Control-Plane Bridge**
   - 产出给 `task_center / executor-runs / upgrade-feedback` 消费的桥接记录
   - 保证蒸馏证据能按 `trace_id / task_id / run_id` 回挂到既有控制面

### 3.4 必须对接的数据源矩阵

| 类别 | 数据源 | 关键字段 | 作用 | 默认接入阶段 |
|------|--------|----------|------|--------------|
| 会话 | Claude Code transcripts | session_id、role、content、tool_use、timestamp | 主对话证据 | P3 |
| 会话 | Gemini brain/artifacts | artifact_path、summary、logs、timestamp | 分析与工件证据 | P3 |
| 会话 | OpenClaw / Codex sessions | model、agent_id、tool_use、status、timestamp | 执行链与编码模式 | P3 |
| 会话 | Hermes sessions | session_id、summary、memory actions、timestamp | 记忆动作与压缩上下文 | P3 |
| 代码 | repo delta | changed_files、diff_fingerprint、commit_sha | 证明“实际改了什么” | P3 |
| 验证 | test / build / lint logs | command、exit_code、summary、artifacts | 证明“验证结果如何” | P3 |
| 文档 | todo / done / README / ADR | task_id、decision_id、status | 稳定约束与决策来源 | P3 |
| 控制面 | `task_center.db` | task_id、trace_id、assignee、status、task_kind | 对齐任务历史与回流任务 | P3 |
| 控制面 | `executor-runs/*.json` | run_id、trace_id、score、artifacts、finished_at | 对齐 baseline / candidate 执行窗口 | P3 |
| 控制面 | `upgrade-feedback/reports/*.json` | benchmark_run_id、candidate_run_ids、root_cause、promotion_status | 对齐已有升级评分主链 | P3 |
| 协作 | PR / issue / review comment | reviewer、decision、reason | 设计裁决与外部反馈 | P5 |
| 运行 | 巡检报告 / 部署日志 / 异常摘要 | trace_id、service、severity | 运维经验 | P5 |

### 3.5 宿主内 Parser Agent 解析门禁

这里必须做一个明确裁决：

`不是所有数据都应该交给宿主内解析 Agent，只有“经过规则清洗后、具备复用潜力的候选片段”才进入解析。`

原因：

- 原始 transcript 和日志太大，直接解析成本失控
- 冗余输出会污染摘要质量
- 热记忆写入需要高精度，不适合让解析 Agent 面对大量噪音自由发挥

因此解析门禁固定为：

1. **规则层先行**
   - 工具原始输出裁剪
   - 长日志折叠
   - 重复片段 fingerprint 去重
   - 敏感字段掩码
2. **候选层再筛选**
   - 目标、约束、决策、失败教训、可复用流程优先
   - 空聊天、礼貌回复、机械回显直接跳过
3. **宿主内 Parser Agent 只做结构化提取**
   - Hermes 侧调用 Hermes 内部解析 Agent
   - OpenClaw 侧调用 OpenClaw 内部解析 Agent
   - 输出 JSON schema
   - 需要包含 `summary / rationale / evidence_refs / confidence / target_kind`
4. **规则层二次校验**
   - schema 校验
   - 证据引用校验
   - 长度预算校验
   - 敏感信息复扫
   - `trace_id / task_id / run_id / agent_id / workspace` 桥接字段校验

### 3.6 Source Adapter 接口契约

每个数据源适配器必须实现统一接口，保证核心蒸馏逻辑与数据源解耦。

#### 3.6.1 统一接口定义

```python
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class RawEvent:
    """适配器输出的归一化原始事件。"""
    event_id: str          # 格式: {source}:{session_id}:{offset}
    source: str            # claude | gemini | openclaw | hermes | repo_delta | control_plane | docs
    host: str              # hermes | openclaw
    project: str
    session_id: str
    role: str              # user | assistant | tool | system
    content: str           # 清洗后的正文
    timestamp: str         # ISO 8601
    metadata: dict         # 源特有元数据（如 tool_name, exit_code, file_path 等）

class SourceAdapter(Protocol):
    """所有数据源适配器必须满足的接口契约。"""

    def probe(self, probe_result: dict) -> list[str]:
        """探测并返回当前可用的会话/文件路径列表。

        Args:
            probe_result: RuntimeProbeResult.to_dict()

        Returns:
            可用路径列表（POSIX 或 Windows 路径，取决于宿主环境）
        """
        ...

    def extract(self, path: str, cursor: dict | None) -> list[RawEvent]:
        """从指定路径提取增量事件。

        Args:
            path: 会话文件/目录路径
            cursor: 上次游标（IngestCursor.cursor_value），首次为 None

        Returns:
            归一化事件列表
        """
        ...

    def cursor_hint(self, path: str) -> dict:
        """返回当前路径的最新游标值，供下次增量提取使用。"""
        ...
```

#### 3.6.2 适配器注册表

```python
ADAPTER_REGISTRY: dict[str, type[SourceAdapter]] = {
    "claude": ClaudeSourceAdapter,
    "gemini": GeminiSourceAdapter,
    "openclaw": OpenClawSourceAdapter,
    "hermes": HermesSourceAdapter,
    "repo_delta": RepoDeltaSourceAdapter,
    "control_plane": ControlPlaneSourceAdapter,
    "docs": DocsSourceAdapter,
}
```

### 3.7 候选窗口切分策略

原始事件进入解析前，必须切成适合解析 Agent 处理的窗口。

#### 3.7.1 切分规则

| 参数 | 值 | 说明 |
|------|-----|------|
| 最大窗口长度 | 4000 字符 | 控制解析 Agent 输入大小 |
| 最小窗口长度 | 200 字符 | 低于此长度合并到上一窗口 |
| 切分边界 | message turn | 优先在 `role` 变化处切 |
| 硬切阈值 | 6000 字符 | 超过时强制在最近 turn 边界切 |

#### 3.7.2 切分算法

```text
1. 按 session_id 分组
2. 按 timestamp 排序
3. 在每个 session 内按 turn (role 变化) 切分
4. 合并相邻 turn 直到接近 4000 字符
5. 如果单 turn 超 6000 字符，裁剪工具输出，保留前 500 + 后 200 字符
6. 每个窗口记录起止 event_id
```

#### 3.7.3 窗口输出格式

```json
{
  "window_id": "win_claude_ses001_0",
  "session_id": "claude:ses_abc",
  "source": "claude",
  "event_ids": ["claude:ses_abc:0", "claude:ses_abc:1", "claude:ses_abc:2"],
  "text": "合并后的窗口正文",
  "char_count": 3800,
  "turn_count": 5,
  "time_span": ["2026-04-16T10:00:00Z", "2026-04-16T10:15:00Z"]
}
```

### 3.8 候选打分算法

不是所有窗口都值得进入解析 Agent，必须先做规则打分。

#### 3.8.1 评分维度

| 维度 | 权重 | 评分规则 | 分值范围 |
|------|------|---------|---------|
| 信息密度 | 0.3 | 代码片段/命令/路径/配置值占比越高分越高 | 0-1 |
| 决策含量 | 0.25 | 包含"决定/选择/因为/改为/修复/升级"等关键词 | 0-1 |
| 失败证据 | 0.2 | 包含 error/失败/超时/异常/回滚等关键词 | 0-1 |
| 操作可复用 | 0.15 | 包含完整的操作序列（3步以上） | 0-1 |
| 敏感风险 | -0.1 | 命中敏感扫描规则的条数越多扣分越多 | 0-(-1) |

#### 3.8.2 评分公式

```
score = (density * 0.3) + (decision * 0.25) + (failure * 0.2) + (reusability * 0.15) + (sensitive_risk * -0.1)
最终分数 = max(0, score)  // 不允许负分
```

#### 3.8.3 分数路由

| 分数区间 | 处理方式 |
|---------|---------|
| ≥ 0.7 | 进入解析 Agent（高价值候选） |
| 0.4 ~ 0.7 | 仅进入检索索引，不进解析 Agent |
| < 0.4 | 仅保留原始证据，不入索引 |

#### 3.8.4 关键词匹配规则

```python
# 信息密度：代码/命令/路径/配置值的特征
DENSITY_PATTERNS = [
    r"```[\s\S]*?```",       # 代码块
    r"`[^`]+`",              # 行内代码
    r"[A-Z_]{2,}=\S+",       # 环境变量/配置
    r"/[\w./\-]+",            # Unix 路径
    r"[A-Z]:\\[\w\\.\-]+",   # Windows 路径
    r"(?:pip|npm|git|ssh|docker|kubectl)\s+\w+",  # 命令
]

# 决策含量
DECISION_KEYWORDS = ["决定", "选择", "改为", "采用", "切换到", "修复", "升级", "因为", "原因", "权衡"]

# 失败证据
FAILURE_KEYWORDS = ["error", "失败", "超时", "异常", "回滚", "traceback", "failed", "crash", "OOM", "死锁"]

# 操作可复用：连续步骤
STEP_PATTERNS = [r"步骤\s*\d", r"Step\s*\d", r"\d+\.\s+\w+", r"首先.*然后.*最后"]
```

## 4. 领域对象设计

### 4.1 `MemoryEntry`

统一的记忆基础对象：

```json
{
  "id": "mem_abc123",
  "kind": "user | memory | experience | adr | pattern",
  "source": "claude | gemini | codex | openclaw | hermes",
  "title": "一句话摘要",
  "content": "精炼后的正文",
  "tags": ["python", "部署", "偏好"],
  "confidence": 0.91,
  "evidence_refs": ["claude:ses_xxx:12-34"],
  "updated_at": "2026-04-15T09:30:00Z"
}
```

### 4.2 `MemoryAction`

仿照 Hermes 记忆工具的受控动作：

```json
{
  "action": "add | replace | remove",
  "target": "user | memory | experience | adr | pattern",
  "old_text": "仅 replace/remove 需要，允许唯一子串匹配",
  "content": "新内容",
  "reason": "为什么要写/替换/删除",
  "source_report": "distill-20260415.json"
}
```

### 4.3 `SessionSearchHit`

检索层返回对象：

```json
{
  "session_id": "hermes:dm:xxx",
  "source": "hermes",
  "score": 0.83,
  "summary": "三周前讨论过 staging SSH 端口从 22 改为 2222",
  "evidence_snippets": ["..."],
  "resolved_entities": ["staging", "ssh", "2222"]
}
```

### 4.4 `RepoDeltaEvidence`

IDE 经验侧证据对象：

```json
{
  "workspace": "H:/GitHub/openclaw-hardflow-backup-20260302",
  "changed_files": [
    "skills/library/openclaw-evolution-upgrader/scripts/upgrade_feedback_runner.py"
  ],
  "verification_commands": [
    "pytest tests/scripts_openclaw_ops/test_memory_write_gateway.py -v"
  ],
  "verification_summary": "1 passed",
  "diff_fingerprint": "git:abc123",
  "updated_at": "2026-04-15T10:20:00Z"
}
```

### 4.5 `IngestCursor`

每个数据源都必须有增量游标，否则数据量变大后只能全量重扫：

```json
{
  "source": "claude",
  "host": "windows-user",
  "project": "openclaw-hardflow-backup-20260302",
  "cursor_type": "mtime+offset",
  "cursor_value": {
    "last_mtime": "2026-04-15T10:00:00Z",
    "last_file": "C:/Users/Administrator/.claude/transcripts/abc.jsonl",
    "last_offset": 182331
  },
  "updated_at": "2026-04-15T10:20:00Z"
}
```

### 4.6 `DistillArtifact`

宿主内 Parser Agent 提取后的结构化产物，必须和原始证据、路由结果绑定：

```json
{
  "artifact_id": "distill_20260415_001",
  "kind": "experience",
  "title": "PowerShell 中先切 UTF-8 再读中文文件",
  "summary": "针对中文文件读取乱码问题，先 chcp 65001，再用 UTF-8 显式读取。",
  "evidence_bundle_ids": ["bundle_claude_001", "bundle_repo_delta_004"],
  "trace_id": "trace_abc123",
  "task_id": "task_xyz789",
  "run_id": "run_456",
  "agent_id": "optimization-agent",
  "workspace": "H:/GitHub/openclaw-hardflow-backup-20260302",
  "storage_targets": [
    ".workflow/experience/powershell-utf8.md",
    "session_search_index"
  ],
  "confidence": 0.93,
  "created_at": "2026-04-15T10:30:00Z"
}
```

### 4.7 `ControlPlaneBridgeRecord`

为了把蒸馏结果真正接回 OpenClaw 控制面，需要额外产出桥接记录：

```json
{
  "bridge_id": "bridge_20260415_001",
  "artifact_id": "distill_20260415_001",
  "trace_id": "trace_abc123",
  "task_id": "task_xyz789",
  "run_id": "run_456",
  "benchmark_run_id": "benchmark_run_123",
  "candidate_run_ids": ["cand_run_1", "cand_run_2"],
  "workspace": "H:/GitHub/openclaw-hardflow-backup-20260302",
  "root_cause_hints": ["skill_gap", "memory_pollution"],
  "source_report_paths": [
    "reports/distill/distill-20260415.json",
    "reports/bridge/bridge-20260415.json"
  ],
  "created_at": "2026-04-15T10:35:00Z"
}
```

### 4.8 `NormalizedEvent`

所有数据源适配器输出统一为此结构，是蒸馏流水线的标准中间格式。

```json
{
  "event_id": "claude:ses_abc123:42",
  "source": "claude",
  "host": "openclaw",
  "project": "openclaw-hardflow-backup-20260302",
  "session_id": "claude:ses_abc123",
  "role": "assistant",
  "content": "我把 SSH 端口从 22 改成了 2222，因为 staging 环境有端口冲突...",
  "timestamp": "2026-04-16T10:05:00Z",
  "metadata": {
    "tool_name": "Bash",
    "tool_input_summary": "ssh -p 2222 staging",
    "exit_code": 0,
    "file_paths": ["config/sshd_config"],
    "commit_sha": null
  }
}
```

**必填字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `event_id` | string | `{source}:{session_id}:{offset}` 格式 | 全局唯一，用于去重和追溯 |
| `source` | enum | `claude \| gemini \| openclaw \| hermes \| repo_delta \| control_plane \| docs` | 数据来源 |
| `host` | enum | `hermes \| openclaw` | 宿主标识 |
| `project` | string | 非空 | 项目标识 |
| `session_id` | string | 非空 | 会话标识（可含 source 前缀） |
| `role` | enum | `user \| assistant \| tool \| system` | 消息角色 |
| `content` | string | 非空，已清洗 | 正文（工具输出已裁剪） |
| `timestamp` | string | ISO 8601 | 事件时间 |
| `metadata` | object | 可为空 dict | 源特有字段，不同 source 的 metadata 字段不同 |

**各 source 的 metadata 扩展字段**：

| source | 典型 metadata 字段 |
|--------|-------------------|
| claude | `tool_name`, `tool_input_summary`, `file_paths`, `commit_sha` |
| gemini | `artifact_path`, `model`, `artifact_type` |
| openclaw | `agent_id`, `task_id`, `trace_id`, `tool_name` |
| hermes | `memory_action`, `summary_version`, `compression_round` |
| repo_delta | `changed_files`, `diff_fingerprint`, `verification_commands`, `exit_code` |
| control_plane | `task_id`, `run_id`, `trace_id`, `benchmark_run_id`, `score` |
| docs | `doc_type`, `section_path`, `decision_id` |

### 4.9 ID 生成策略

所有蒸馏流水线产出的 ID 必须全局唯一、可排序、可人工辨识来源。

| ID 类型 | 格式 | 示例 | 说明 |
|---------|------|------|------|
| event_id | `{source}:{session_id}:{offset}` | `claude:ses_abc:42` | 直接由适配器生成 |
| window_id | `win_{source}_{session_short}_{seq}` | `win_claude_abc_0` | 切分阶段生成 |
| candidate_id | `cand_{yyyymmdd}_{seq:04d}` | `cand_20260416_0001` | 打分阶段生成 |
| artifact_id | `distill_{yyyymmdd}_{seq:04d}` | `distill_20260416_0001` | 解析阶段生成 |
| bridge_id | `bridge_{yyyymmdd}_{seq:04d}` | `bridge_20260416_0001` | 桥接阶段生成 |
| bundle_id | `bundle_{source}_{yyyymmdd}_{seq:03d}` | `bundle_claude_20260416_001` | 证据包 ID |

**seq 计数器**：每天从 1 开始，存储在 `distill.db` 的 `counters` 表中。

```sql
CREATE TABLE IF NOT EXISTS id_counters (
    counter_type TEXT NOT NULL,  -- cand | artifact | bridge | bundle
    date_key     TEXT NOT NULL,  -- YYYYMMDD
    seq          INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (counter_type, date_key)
);
```

| Hermes 概念 | Hermes 做法 | 通用技能 + 宿主适配 |
|------------|-------------|-------------------|
| `USER.md` | 用户画像、偏好、沟通风格 | Hermes / OpenClaw 各自落到宿主热记忆文件 |
| `MEMORY.md` | 环境事实、项目事实、经验摘要 | Hermes / OpenClaw 各自落到宿主热记忆文件 |
| `session_search` | 搜索全部历史会话，按需摘要返回 | 共享 `session_search_index`，宿主只接查询接口 |
| `memory add/replace/remove` | 受控更新 | 共享 `memory_write_gateway`，宿主只接落盘适配 |
| Skills | 程序性知识首选扩展方式 | 输出通用 Skill draft，按宿主规范安装 |
| Context Compressor | 结构化摘要 + 双层压缩 | 共享 `distill_summary_template + cache-safe injection` |
| External Memory Provider | 可插拔增强层 | 预留 `host_adapter/` 与 `provider_adapter/` |

## 6. 热记忆与检索层分工

### 6.1 热记忆层

只保留满足以下条件的信息：

- 下次会话一开始就必须知道
- 体积小，稳定，半年内大概率仍有效
- 对行为有直接影响

具体包括：

- 用户偏好、禁忌、沟通风格
- 项目级长期约束
- 环境级关键事实
- 已被证明有效的长期 workaround

### 6.2 检索层

以下内容全部进入 session search，不进入热记忆：

- 临时调试上下文
- 某次单独排障过程的完整对话
- 大量工具原始输出
- 可以按关键词重新找到的历史细节

### 6.3 长尾知识层

从检索层蒸馏出的高价值内容，再按性质落到：

- `.workflow/experience/`：经验卡片
- `docs/adr/`：架构决策
- `skill drafts/`：流程模式
- `repo-delta evidence`：代码变更与验证证据索引

### 6.4 分层存储设计

为防止“热记忆、原始证据、检索索引和控制面桥接记录混成一锅”，存储必须固定成 6 层：

| 层级 | 内容 | 推荐存储 | 写入方式 | 生命周期 |
|------|------|----------|----------|----------|
| Raw Evidence | 原始 transcript、artifact、日志片段、diff、验证输出 | 本地文件包 / 对象存储目录 | 追加写 | 长期保留，可压缩 |
| Normalized Event Store | 统一事件模型、候选窗口、cursor 状态 | SQLite / Postgres | 幂等 upsert | 中长期保留 |
| Search Index | FTS、embedding、摘要缓存 | SQLite FTS / 向量库 | 重建或增量写 | 可重建 |
| Hot Memory | `USER.md` + `MEMORY.md` | 宿主文件 | 受控 replace/add/remove | 严格预算，长期有效 |
| Knowledge Layer | 经验卡、ADR、Skill Draft、报告 | Markdown + JSON | 路由写入 | 长期保留 |
| Control-Plane Bridge | `trace_id/task_id/run_id` 桥接记录、bridge report | SQLite + JSON | 幂等 upsert + 报告写入 | 中长期保留，可重建 |

裁决如下：

- **默认单机方案**：`Raw Evidence + SQLite(事件/游标/FTS/bridge metadata) + Markdown 知识层`
- **数据放大后的升级方案**：原始证据继续保文件或对象目录，元数据与检索索引迁移到 `Postgres + pgvector` 或等价后端
- **向量化范围**：只向量化清洗后的候选窗口或结构化摘要，不向量化整段原始 transcript

### 6.5 数据量越来越大时怎么办

这部分必须提前定策略，否则上线后一定炸：

1. **增量而非全量**
   - 所有 source adapter 都使用 `IngestCursor`
   - 每次只扫新增或变化部分
2. **分区而非单文件堆积**
   - 证据目录按 `source / yyyy-mm / project / session_id` 分区
   - SQLite / Postgres 表按日期与 source 建索引
3. **异步而非同步阻塞**
   - 接入和清洗可以同步批处理
   - 宿主内 Parser Agent 解析必须进入异步队列，允许限流与重试
4. **冷热分层**
   - 最近 7-30 天候选保留在热检索层
   - 更旧证据转温层，仅保摘要和定位指针
   - 再老的数据压缩归档，需要时再回放
5. **小模型/规则前置降本**
   - 先用规则与低成本模型做候选筛选
   - 只有高价值片段进入高成本解析 Agent / 模型档位
6. **幂等与可重放**
   - 任一批次失败后可从 cursor 继续
   - 任一 artifact 都能追溯到原始证据包重新计算
7. **桥接元数据单独建索引**
   - `trace_id / task_id / run_id / benchmark_run_id` 单独建索引
   - bridge record 可以重建，但不能和热记忆混存

### 6.6 热记忆文件格式规范

`USER.md` 和 `MEMORY.md` 是蒸馏流水线的最终写入目标，必须有稳定格式才能支持 `add/replace/remove` 操作。

#### 6.6.1 文件结构

```markdown
# {USER | MEMORY}

<!-- memory-meta
version: 1
last_updated: 2026-04-16T10:30:00Z
entry_count: 5
total_bytes: 1234
-->

## 用户偏好

- 偏好中文回复
- 代码注释使用中文
- ...

## 项目约束

- SSH 凭证目录: D:/ssh_keys/
- 默认编码: UTF-8 (无 BOM)
- ...
```

#### 6.6.2 格式规则

| 规则 | 说明 |
|------|------|
| 编码 | UTF-8 无 BOM |
| 标题 | 一级标题固定为 `# USER` 或 `# MEMORY` |
| 元数据 | HTML 注释块 `<!-- memory-meta ... -->`，解析时跳过不注入 |
| 条目组织 | 二级标题 `##` 按主题分 section，每个 section 下用无序列表 |
| 条目格式 | `- {内容}`（单行）或 `- {标题}: {详情}`（一行概述 + 缩进详情） |
| 分隔 | section 之间空一行 |
| 不允许 | 自由段落、嵌套列表超过 2 层、HTML 标签（meta 除外） |

#### 6.6.3 唯一子串匹配算法

`replace` 和 `remove` 操作需要定位旧内容，使用以下策略：

```python
def find_unique_substring(file_content: str, old_text: str) -> tuple[int, int] | None:
    """在文件中查找唯一匹配的子串位置。

    Returns:
        (start, end) 偏移量，未找到返回 None，多处匹配抛 ValueError。
    """
    # 1. 精确匹配
    count = file_content.count(old_text)
    if count == 1:
        start = file_content.index(old_text)
        return (start, start + len(old_text))
    if count > 1:
        raise ValueError(f"ambiguous_match:found={count}")

    # 2. 按行匹配（去除首尾空白后比较）
    old_lines = [l.strip() for l in old_text.strip().splitlines() if l.strip()]
    matches = []
    file_lines = file_content.splitlines(keepends=True)
    for i in range(len(file_lines) - len(old_lines) + 1):
        window = [l.strip() for l in file_lines[i:i+len(old_lines)] if l.strip()]
        if window == old_lines:
            matches.append(i)
    if len(matches) == 1:
        start = sum(len(l) for l in file_lines[:matches[0]])
        end = start + sum(len(l) for l in file_lines[matches[0]:matches[0]+len(old_lines)])
        return (start, end)
    if len(matches) > 1:
        raise ValueError(f"ambiguous_line_match:found={len(matches)}")

    return None
```

### 6.7 UTF-8 与中文处理策略

本仓库涉及大量中文内容，跨平台编码是必踩坑点。

| 场景 | 策略 |
|------|------|
| 文件读取 | 始终 `encoding="utf-8"`，加 `errors="replace"` 防崩溃 |
| 文件写入 | 始终 `encoding="utf-8"`，无 BOM |
| subprocess 输出 | 设置 `encoding="utf-8", errors="replace"` |
| WSL 命令输出 | WSL 默认 UTF-8，但仍加 `errors="replace"` 兜底 |
| SQLite | 连接后执行 `PRAGMA encoding = "UTF-8"` |
| JSON 读写 | `ensure_ascii=False` |
| 去重指纹 | normalize 时 `.lower()` 不做中文折叠，只去空白和标点 |

### 6.8 日志格式与级别规范

```python
import logging

# 标准日志格式
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
```

| 级别 | 使用场景 |
|------|---------|
| DEBUG | 候选窗口内容、打分详情、解析 Agent 原始输出 |
| INFO | 阶段开始/完成、写入条目数、跳过条目数 |
| WARNING | 容量接近上限、敏感扫描命中、低置信度结果 |
| ERROR | 文件读写失败、解析 Agent 超时、schema 校验失败 |
| CRITICAL | 热记忆写入后校验不一致、SQLite 损坏 |

**日志输出目标**：

- 默认 stderr（供 Cron 捕获）
- `--log-file` 参数指定时同时写文件（追加模式，UTF-8）

### 6.9 并发安全

| 场景 | 策略 |
|------|------|
| 同一 distill.db | SQLite 自带文件锁，`BEGIN IMMEDIATE` 事务保证写安全 |
| 同一热记忆文件 | 写入前获取 `fcntl.flock`（Linux）或 `msvcrt.locking`（Windows），超时 30 秒 |
| 同一 evidence 目录 | 追加写天然安全（文件名含时间戳，不冲突） |
| 防重复启动 | PID 文件 `distill.db` 同目录下 `distiller.pid`，启动时检查并清理 stale lock |

## 7. 上下文压缩对齐方案

Hermes 的上下文压缩设计不应只看成“聊天优化”，它对我们的蒸馏层也有直接价值。

### 7.1 必须照搬的点

1. 双层压缩
   - 前置安全网：消息进入前检查上下文压力
   - 主压缩器：在 agent loop 内基于真实 token 做压缩
2. 结构化摘要模板
   - `Goal`
   - `Constraints & Preferences`
   - `Progress`
   - `Key Decisions`
   - `Relevant Files`
   - `Next Steps`
   - `Critical Context`
3. 先清工具输出，再做宿主内 Parser Agent 摘要
4. 多轮压缩时更新旧摘要，而不是每次从零总结
5. 保护前缀缓存，避免会话中途频繁改系统前缀

### 7.2 OpenClaw 落地

- `distill_runner.py` 通过宿主 adapter 调用内部 Parser Agent，并要求其输出复用该结构化模板
- 后续若实现 `context_engine`，优先做成可替换插件接口
- `USER.md` / `MEMORY.md` 注入遵守“会话冻结快照”

## 8. 技能化设计

Hermes 明确把 Skill 作为首选扩展方式，这一点应直接成为本仓记忆升级的规则。

### 8.1 升级判定

以下任一条件满足，即从经验层升格为 Skill draft：

- 同一流程 3 次以上重复成功
- 同一错误 2 次以上被同一种方法修复
- 同一外部 CLI / API 被稳定地以相同步骤调用
- 同一约束与验证模式重复出现

### 8.2 Skill 结构

输出目录继续沿用：

```text
skills/library/<skill-name>/
├── SKILL.md
├── scripts/
└── references/
```

并增加一份来源证据：

```text
reports/skill-candidates/<skill-name>/origin.json
```

用于记录：

- 来源会话
- 提炼日期
- 触发次数
- 人工审核结论

### 8.3 Skill Draft SKILL.md 模板

自动生成的 Skill draft 必须使用以下模板，保证不依赖聊天上下文即可被阅读和审核。

```markdown
---
name: {skill-name}
description: >
  {一句话描述本技能解决什么问题，不超过 100 字}
status: draft
generated_by: cross-runtime-memory-distiller
generated_at: "{ISO 8601 时间戳}"
trigger_count: {触发次数}
---

# {技能名称}

> 状态：🟡 Draft（待人工审核激活）
> 来源：由记忆蒸馏引擎自动从 {N} 次重复操作中提炼

## 适用场景

- {场景 1：什么时候应该使用本技能}
- {场景 2}

## 操作步骤

1. {步骤 1：具体命令或操作}
2. {步骤 2}
3. {步骤 3}
...

## 验证方法

- {如何确认操作成功}
- {常见失败点及排查}

## 注意事项

- {约束条件}
- {已知限制}

## 来源证据

- 首次发现: {date}，来源: {source}:{session_id}
- 重复次数: {N}
- 触发模式: {描述重复出现的操作模式}
- 详细证据: `reports/skill-candidates/{skill-name}/origin.json`
```

### 8.4 origin.json 格式

```json
{
  "skill_name": "staging-ssh-port-fix",
  "status": "draft",
  "trigger_count": 4,
  "first_seen": "2026-03-20T08:00:00Z",
  "last_seen": "2026-04-15T14:30:00Z",
  "pattern_description": "SSH 端口冲突时需要改为 2222",
  "evidence_sessions": [
    {
      "source": "claude",
      "session_id": "claude:ses_abc",
      "timestamp": "2026-03-20T08:00:00Z",
      "snippet": "staging SSH 连接失败，端口 22 被占用，改为 2222 后恢复"
    },
    {
      "source": "hermes",
      "session_id": "hermes:dm_xyz",
      "timestamp": "2026-04-10T09:00:00Z",
      "snippet": "用户问 staging SSH 端口，回答 2222"
    }
  ],
  "generated_at": "2026-04-16T12:00:00Z",
  "human_review": {
    "reviewed": false,
    "reviewer": null,
    "decision": null,
    "reviewed_at": null
  }
}
```

## 9. 与升级控制面的边界

`openclaw-evolution-upgrader` 不直接读取原始 Hermes/Claude/Gemini transcript。  
它只是共享蒸馏技能的一个下游消费者，只消费以下结构化产物：

- `distill-report.json`
- `memory-write-log.json`
- `skill-candidate-origin.json`
- `session-search-benchmark.json`
- `repo-delta-evidence.json`
- `control-plane-bridge.json`

这样可以保证：

- 蒸馏层负责“把杂音变成证据”
- 升级层负责“把证据变成评分与改动决策”
- 控制面桥接层负责“把蒸馏证据挂回既有 `task_center / executor-runs / upgrade-feedback` 主链”

## 10. 最小文件面设计

建议新增文件：

```text
skills/library/cross-runtime-memory-distiller/
├── SKILL.md
├── scripts/
│   ├── runtime_probe.py
│   ├── distill_source_adapters.py
│   ├── ingest_cursor_store.py
│   ├── evidence_store.py
│   ├── distill_cleaner.py
│   ├── distill_classifier.py
│   ├── memory_write_gateway.py
│   ├── session_search_index.py
│   ├── skill_draft_generator.py
│   ├── control_plane_bridge.py
│   ├── distill_reporter.py
│   ├── distill_runner.py
│   ├── host_adapter_hermes.py
│   ├── host_adapter_openclaw.py
│   └── source_repo_delta.py
├── config/
│   ├── distill_rules.json
│   ├── memory_limits.json
│   ├── parser_schema.json
│   ├── storage_policy.json
│   └── session_search_policy.json
└── references/
    ├── shared-host-contract.md
    └── parser-agent-contract.md
```

## 11. 验证指标

| 指标 | 目标 |
|------|------|
| 热记忆总长度 | `USER + MEMORY` 不超过预算上限 |
| 会话清洗率 | ≥ 70% |
| 结构化摘要完整率 | ≥ 90% |
| 重复记忆拒写率 | 100% |
| 增量重跑重复入库率 | 0 |
| 原始证据回放成功率 | 100% |
| pattern -> skill 提议准确率 | 人工抽检 ≥ 80% |
| 升级反馈消费成功率 | 所有 distill report 都可被 upgrade 层引用 |
| 控制面桥接成功率 | 所有 artifact 都可按 `trace_id / task_id / run_id` 回挂到控制面 |

## 12. 架构结论

这次不是要“兼容 Hermes”，而是：

`把 Hermes 证明有效的抽象作为跨宿主通用技能的正式蓝图，再分别接到 Hermes 与 OpenClaw。`

但真正被完全仿照的是：

- 记忆分层
- 受控写入
- 会话检索
- 技能化
- 结构化压缩
- 前缀缓存保护

不直接照搬的是：

- `.hermes/` 目录布局
- `state.db` 内部 schema
- provider 插件运行时实现
- `openclaw-evolution-upgrader` 现有脚本布局

---

## 附录 A：热记忆容量预算初始值

> 以下为 `config/memory_limits.json` 的初始建议值，运行后根据实际使用情况调整。

```json
{
  "version": 1,
  "hot_memory": {
    "user_md": {
      "max_bytes": 2048,
      "warn_threshold_pct": 80,
      "description": "用户偏好、沟通风格、角色画像。精炼短小，半年有效。"
    },
    "memory_md": {
      "max_bytes": 8192,
      "warn_threshold_pct": 80,
      "description": "环境事实、项目约束、长期 workaround。稳定事实为主。"
    }
  },
  "experience": {
    "max_file_bytes": 65536,
    "max_files_per_topic": 1,
    "description": "经验卡片按主题文件聚合，单文件不超过 64KB。"
  },
  "knowledge_layer": {
    "adr_max_bytes": 32768,
    "skill_draft_max_bytes": 131072
  }
}
```

**容量超限策略**：

1. 写入时检查当前文件大小
2. 超过 `warn_threshold_pct` → 日志预警 + 报告中标注
3. 超过 `max_bytes` → **拒绝写入** + 返回当前条目数与压缩建议
4. 压缩建议由 `memory_write_gateway` 生成，列出"可合并/可降级/可归档"的候选条目

## 附录 B：Parser Agent 调度协议草案

### B.1 调度方式

| 方式 | 适用场景 | 实现复杂度 | 当前推荐 |
|------|---------|-----------|---------|
| CLI 子进程 | 宿主有独立可执行 Agent | 低 | **Phase 2-4 默认方案** |
| HTTP API | 宿主暴露本地服务 | 中 | Phase 5+ 升级方案 |
| stdin/stdout pipe | 紧耦合场景 | 中 | 不推荐 |

### B.2 CLI 调度协议

共享技能通过宿主 adapter 构造命令行调用：

```bash
# Hermes 侧（通过 WSL）
wsl -d Ubuntu -- hermes parser-agent \
  --input-json /tmp/candidate_001.json \
  --output-json /tmp/artifact_001.json \
  --schema-version 2026-04-15 \
  --timeout 60

# OpenClaw 侧（Windows 原生）
python -m openclaw.parser_agent \
  --input-json C:/tmp/candidate_001.json \
  --output-json C:/tmp/artifact_001.json \
  --schema-version 2026-04-15 \
  --timeout 60
```

### B.3 输入输出契约

**输入**（`ParserCandidatePacket`，已定义于 `runtime_probe.py`）：

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `candidate_id` | string | 是 | 候选唯一标识 |
| `host` | string | 是 | `hermes \| openclaw` |
| `project` | string | 是 | 项目标识 |
| `trace_id` | string | 是 | 追溯 ID |
| `task_id` | string | 否 | 任务 ID |
| `run_id` | string | 否 | 执行 ID |
| `source` | string | 是 | `claude \| gemini \| openclaw \| hermes \| repo_delta \| control_plane` |
| `evidence_refs` | string[] | 是 | 证据引用列表 |
| `window_text` | string | 是 | 候选窗口正文 |
| `target_schema_version` | string | 是 | 解析 schema 版本 |

**输出**（`DistillArtifact`）：

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `artifact_id` | string | 是 | 产物唯一标识 |
| `kind` | enum | 是 | `user \| memory \| experience \| adr \| pattern \| noise` |
| `title` | string | 是 | 一句话标题 |
| `summary` | string | 是 | 结构化摘要 |
| `rationale` | string | 是 | 为什么值得沉淀 |
| `evidence_refs` | string[] | 是 | 证据引用（必须与输入对应） |
| `confidence` | float | 是 | 0.0 ~ 1.0 |
| `target_kind` | enum | 是 | `knowledge \| hot_memory \| bridge_only` |
| `trace_id` | string | 是 | 透传输入的 trace_id |
| `task_id` | string | 否 | 透传 |
| `run_id` | string | 否 | 透传 |
| `requires_human_review` | bool | 是 | confidence < 0.6 时强制为 true |

### B.4 错误处理

| 错误场景 | 处理策略 |
|---------|---------|
| 超时（>60s） | 重试 1 次，仍超时则标记 `parse_timeout`，候选降级为仅检索 |
| 输出非 JSON | 重试 1 次，仍失败则标记 `parse_format_error` |
| schema 校验失败 | 记录具体字段错误，标记 `parse_schema_error` |
| confidence < 0.6 | 强制 `requires_human_review = true`，不自动写入热记忆 |
| 连续 3 次失败 | 暂停当前批次解析，降级为全标 FACT（纯脚本模式） |

## 附录 C：归一化事件存储 Schema 草案

> 单机默认方案：SQLite。数据放大后可迁移到 Postgres。

### C.1 核心表结构

```sql
-- 归一化事件表：存储清洗后的统一事件
CREATE TABLE IF NOT EXISTS normalized_events (
    event_id      TEXT PRIMARY KEY,       -- 格式: {source}:{session_id}:{offset}
    source        TEXT NOT NULL,          -- claude | gemini | openclaw | hermes | repo_delta | control_plane
    host          TEXT NOT NULL,          -- hermes | openclaw
    project       TEXT NOT NULL,
    session_id    TEXT NOT NULL,
    role          TEXT NOT NULL,          -- user | assistant | tool | system
    content       TEXT NOT NULL,          -- 清洗后的正文
    timestamp     TEXT NOT NULL,          -- ISO 8601
    metadata_json TEXT DEFAULT '{}',      -- 源特有元数据
    created_at    TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_source ON normalized_events(source, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_session ON normalized_events(session_id);

-- 增量游标表：每个数据源维护一个游标
CREATE TABLE IF NOT EXISTS ingest_cursors (
    source       TEXT NOT NULL,
    host         TEXT NOT NULL,
    project      TEXT NOT NULL,
    cursor_type  TEXT NOT NULL DEFAULT 'mtime+offset',  -- mtime+offset | session_id_set
    cursor_value TEXT NOT NULL,           -- JSON: {last_mtime, last_file, last_offset}
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (source, host, project)
);

-- 候选窗口表：经过规则打分后值得进入解析的片段
CREATE TABLE IF NOT EXISTS candidate_windows (
    candidate_id  TEXT PRIMARY KEY,
    event_ids     TEXT NOT NULL,           -- JSON array of event_id
    source        TEXT NOT NULL,
    host          TEXT NOT NULL,
    window_text   TEXT NOT NULL,
    score         REAL NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending | parsed | skipped | failed
    artifact_id   TEXT,                    -- 解析成功后关联的 artifact
    created_at    TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidate_windows(status, score);

-- 控制面桥接表：蒸馏产物与既有控制面的关联
CREATE TABLE IF NOT EXISTS control_plane_bridge (
    bridge_id         TEXT PRIMARY KEY,
    artifact_id       TEXT NOT NULL,
    trace_id          TEXT,
    task_id           TEXT,
    run_id            TEXT,
    benchmark_run_id  TEXT,
    workspace         TEXT,
    root_cause_hints  TEXT DEFAULT '[]',   -- JSON array
    source_report_paths TEXT DEFAULT '[]', -- JSON array
    created_at        TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_bridge_trace ON control_plane_bridge(trace_id);
CREATE INDEX IF NOT EXISTS idx_bridge_task ON control_plane_bridge(task_id, run_id);

-- 去重指纹表
CREATE TABLE IF NOT EXISTS dedup_fingerprints (
    fingerprint   TEXT PRIMARY KEY,       -- MD5(normalize(title + body))
    artifact_id   TEXT NOT NULL,
    created_at    TEXT DEFAULT (datetime('now'))
);
```

### C.2 FTS 检索索引

```sql
-- 全文检索虚拟表（SQLite FTS5）
CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
    content,
    source,
    session_id,
    project,
    content='normalized_events',
    content_rowid='rowid'
);

-- 触发器：自动同步
CREATE TRIGGER IF NOT EXISTS events_fts_insert AFTER INSERT ON normalized_events BEGIN
    INSERT INTO events_fts(rowid, content, source, session_id, project)
    VALUES (new.rowid, new.content, new.source, new.session_id, new.project);
END;
```

### C.3 存储路径约定

```text
~/.openclaw/ops/distill/
├── distill.db                          -- SQLite 主库（事件/游标/候选/桥接/指纹）
├── evidence/                           -- 原始证据包（按 source/yyyy-mm/project/ 分区）
│   ├── claude/2026-04/openclaw-hardflow/
│   │   └── bundle_001.jsonl
│   └── hermes/2026-04/openclaw-hardflow/
│       └── bundle_002.jsonl
├── reports/                            -- 蒸馏报告
│   ├── distill-20260416.json
│   └── bridge-20260416.json
└── skill-candidates/                   -- Skill 候选草稿
    └── <skill-name>/
        ├── SKILL.md
        └── origin.json
```

## 附录 D：敏感信息扫描规则

> 用于 `memory_write_gateway.py` 写前扫描和 `distill_cleaner.py` 清洗阶段。

| 规则 | 匹配模式 | 处理方式 |
|------|---------|---------|
| API Key | `(sk-\|ghp_\|gho_\|xoxb-\|xoxp-)[a-zA-Z0-9]{20,}` | 掩码替换，仅保留前 6 字符 |
| AWS Credential | `AKIA[0-9A-Z]{16}` | 掩码替换 |
| 私钥标记 | `-----BEGIN (RSA \|EC \|DSA )?PRIVATE KEY` | 整行替换为 `[REDACTED_KEY]` |
| 数据库连接串 | `mongodb://.*:.*@\|postgres://.*:.*@\|mysql://.*:.*@` | 凭证部分掩码 |
| JWT Token | `eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}` | 掩码替换 |
| IP + 端口 | `\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5}`（仅私有网段） | 保留，但标记为 `SENSITIVE:internal_ip` |
| 邮箱地址 | `[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}` | 掩码替换 |
| Prompt 注入 | `(ignore previous\|disregard above\|system:\|<system>)` | 标记为 `INJECTION_RISK`，拒绝写入热记忆 |

## 附录 E：各数据源原始格式与提取规则

每个 Source Adapter 需要理解其数据源的原始格式。以下是已知格式的字段映射。

### E.1 Claude Code Transcript

**路径**：`~/.claude/transcripts/*.jsonl`（Windows: `C:\Users\{user}\.claude\transcripts\`）

**格式**：JSONL，每行一条消息。

```jsonl
{"type":"user","message":{"role":"user","content":"把 SSH 端口改成 2222"},"timestamp":"2026-04-16T10:00:00Z","sessionId":"ses_abc123"}
{"type":"assistant","message":{"role":"assistant","content":[],"tool_use":[{"name":"Bash","input":{"command":"ssh -p 2222 staging"}}]},"timestamp":"2026-04-16T10:00:05Z","sessionId":"ses_abc123"}
{"type":"tool_result","tool_use_id":"toolu_xxx","content":"Connection refused","is_error":true,"timestamp":"2026-04-16T10:00:06Z","sessionId":"ses_abc123"}
```

**提取规则**：

| 原始字段 | → NormalizedEvent 字段 | 备注 |
|---------|----------------------|------|
| `type` | `role`：user→user, assistant→assistant, tool_result→tool | |
| `message.content` | `content` | 数组时取第一个 text block |
| `message.tool_use` | `metadata.tool_name`, `metadata.tool_input_summary` | 只取 name + input 摘要 |
| `tool_result.content` | `content`（工具输出） | 超 200 字符裁剪为前 500 + 后 200 |
| `timestamp` | `timestamp` | |
| `sessionId` | `session_id` | 加前缀 `claude:` |

**游标策略**：`mtime + file_offset`（JSONL 可按行偏移增量读取）

### E.2 Gemini Brain / Artifact

**路径**：`~/.gemini/antigravity/brain/**`（结构可能随版本变化，adapter 需做格式探测）

**已知格式变体**：

1. **Markdown 文件**（`.md`）：直接作为 content，role 推断为 `assistant`
2. **JSON 文件**（`.json`）：含 `summary`, `logs`, `artifacts` 字段
3. **目录结构**：`brain/{session_id}/` 下多个文件

**提取规则**（保守策略）：

| 检测到的格式 | 提取方式 |
|-------------|---------|
| `.md` 文件 | 整个文件作为一条 `assistant` 事件 |
| `.json` 含 `summary` | `summary` 作为 content，`logs` 作为 metadata |
| 其他 | 跳过并 warn |

**游标策略**：`mtime`（按文件修改时间增量）

### E.3 OpenClaw / Codex Session

**路径**：`~/.openclaw/agents/*/sessions/*.jsonl`（Windows: `%USERPROFILE%\.openclaw\agents\...\`）

**格式**：JSONL，结构与 Claude 类似但增加 agent/task 元数据。

```jsonl
{"role":"user","content":"执行巡检任务","timestamp":"2026-04-16T03:00:00Z","agent_id":"ops-agent","task_id":"task_patrol_001","trace_id":"trace_xyz"}
{"role":"assistant","content":"发现磁盘使用超 80%，执行日志轮转","tool_calls":[{"name":"Bash","arguments":{"command":"logrotate -f /etc/logrotate.d/trader"}}],"timestamp":"2026-04-16T03:00:30Z"}
{"role":"tool","content":"rotated: trader.log.1 (saved 2.1GB)","tool_name":"Bash","exit_code":0,"timestamp":"2026-04-16T03:00:35Z"}
```

**提取规则**：

| 原始字段 | → NormalizedEvent 字段 |
|---------|----------------------|
| `role` | `role`（直接映射） |
| `content` | `content` |
| `tool_calls[].name` | `metadata.tool_name` |
| `tool_calls[].arguments` | `metadata.tool_input_summary`（序列化为短字符串） |
| `tool_name` / `exit_code` | `metadata.tool_name`, `metadata.exit_code` |
| `agent_id` | `metadata.agent_id` |
| `task_id` | `metadata.task_id` |
| `trace_id` | 可作为 `event_id` 前缀的一部分 |

**游标策略**：`mtime + file_offset`

### E.4 Hermes Session

**路径**：`~/.hermes/sessions`（WSL: `/home/ubuntu/.hermes/sessions/`）

**格式**：可能是 JSONL 或 SQLite `state.db` 中的 session 记录。Adapter 需优先读文件，fallback 读 DB。

```jsonl
{"role":"user","content":"staging SSH 端口是多少","timestamp":"2026-04-10T08:00:00Z","session_id":"dm_xxx"}
{"role":"assistant","content":"staging SSH 端口是 2222","memory_actions":[{"action":"add","target":"memory","content":"staging SSH 端口: 2222"}],"timestamp":"2026-04-10T08:00:10Z"}
```

**提取规则**：

| 原始字段 | → NormalizedEvent 字段 |
|---------|----------------------|
| `role` | `role` |
| `content` | `content` |
| `memory_actions` | `metadata.memory_action`（序列化） |
| `session_id` | `session_id`，加前缀 `hermes:` |

**特殊处理**：Hermes session 可能含 `summary_version` 和 `compression_round`，这些是压缩上下文的元信息，应保留到 metadata 中。

**游标策略**：`mtime`（文件级）或 `session_id_set`（DB 查询级）

### E.5 Repo Delta（代码变更证据）

**路径**：工作区 `.git/` 侧信息，不是固定文件路径。

**采集方式**：在 `distill_runner.py` 中通过 `git` 命令采集。

```bash
# 获取最近 N 小时内的变更文件列表
git diff --name-only --since="{N hours ago}"

# 获取关键 diff（仅 .py/.js/.ts/.md，排除 lock 文件）
git diff --since="{N hours ago}" -- "*.py" "*.js" "*.ts" "*.md"

# 获取 commit 元数据
git log --since="{N hours ago}" --oneline --format="%H %s"
```

**提取规则**：

| 采集结果 | → NormalizedEvent 字段 |
|---------|----------------------|
| 变更文件列表 | `metadata.changed_files` (list) |
| diff 内容 | `content`（裁剪到前 2000 字符） |
| commit SHA + message | `metadata.commit_sha`, `content` 标题部分 |
| 验证命令与结果 | `metadata.verification_commands`, `metadata.exit_code` |

**游标策略**：`commit SHA` 或 `mtime`

### E.6 控制面证据

**路径**：

- `task_center.db`（SQLite）
- `executor-runs/*.json`
- `upgrade-feedback/reports/*.json`

**提取规则**：

| 数据源 | 采集方式 | → NormalizedEvent |
|-------|---------|-------------------|
| `task_center.db` | `SELECT` 只读查询 | `role=system`, `metadata.task_id/trace_id/status/assignee` |
| `executor-runs/*.json` | 文件读取 | `role=system`, `metadata.run_id/trace_id/score` |
| `upgrade-feedback/reports/*.json` | 文件读取 | `role=system`, `metadata.benchmark_run_id/root_cause/promotion_status` |

**游标策略**：`mtime`（文件级）或 `rowid > last_max_rowid`（DB 级）

### E.7 文档证据

**路径**：仓库内 `todo.md`, `done.md`, `docs/adr/`, `docs/*/README.md`

**提取规则**：

| 数据源 | 采集方式 | → NormalizedEvent |
|-------|---------|---------|
| `todo.md` | 文件读取 | `role=system`, `metadata.doc_type="todo"` |
| `done.md` | 文件读取 | `role=system`, `metadata.doc_type="done"` |
| `docs/adr/*.md` | 文件读取 | `role=system`, `metadata.doc_type="adr"`, `metadata.decision_id=文件名` |
| 功能三件套 README | 文件读取 | `role=system`, `metadata.doc_type="feature_readme"`, `metadata.section_path` |

**游标策略**：`mtime + file_hash`（文件内容 hash 变化时重新提取）

## 附录 F：结构化摘要 Prompt 模板

以下为宿主内 Parser Agent 的完整 prompt 模板。Adapter 负责填充占位符后交给解析 Agent。

### F.1 解析 Prompt

```
你是一个知识蒸馏解析器。你的任务是从以下候选窗口中提取结构化知识。

## 候选窗口

来源: {source}
项目: {project}
时间范围: {time_span}
会话 ID: {session_id}

---
{window_text}
---

## 输出要求

请严格按照以下 JSON schema 输出，不要输出任何其他内容：

{
  "artifact_id": "由系统分配，留空",
  "kind": "user | memory | experience | adr | pattern | noise",
  "title": "一句话标题（不超过 50 字）",
  "summary": "结构化摘要（使用下方模板）",
  "rationale": "为什么这条知识值得沉淀（不超过 100 字）",
  "evidence_refs": ["证据引用，格式: {source}:{session_id}:{offset}"],
  "confidence": 0.0-1.0,
  "target_kind": "hot_memory | knowledge | bridge_only",
  "requires_human_review": false
}

## 分类标准

- **user**: 用户偏好、沟通风格、角色画像 → target_kind=hot_memory
- **memory**: 环境事实、项目路径、配置值、长期约束 → target_kind=hot_memory
- **experience**: 排障方法、最佳实践、踩坑记录、可复用流程 → target_kind=knowledge
- **adr**: 架构决策、技术选型、方案权衡 → target_kind=knowledge
- **pattern**: 重复出现的操作模式（同一流程出现 ≥ 2 次） → target_kind=knowledge
- **noise**: 无价值内容（空聊天、礼貌回复、机械回显） → 跳过

## 结构化摘要模板

如果 kind 不是 noise，summary 必须按以下模板输出：

### 目标 (Goal)
本次操作/讨论的核心目标是什么？

### 约束与偏好 (Constraints & Preferences)
有哪些限制条件、偏好或已有决策影响了方案选择？

### 进展 (Progress)
具体做了什么？改了哪些文件？执行了什么命令？结果如何？

### 关键决策 (Key Decisions)
做了哪些重要选择？为什么？

### 相关文件 (Relevant Files)
涉及的文件路径列表。

### 下一步 (Next Steps)
如果任务未完成，还需要做什么？

### 关键上下文 (Critical Context)
任何在 3 个月后回看时必须知道的背景信息。

## 安全约束

- confidence < 0.6 时必须设置 requires_human_review = true
- 不允许在 summary 中包含 API key、密码、私钥等敏感信息
- 如果候选窗口中包含敏感信息，在 evidence_refs 中标注并在 rationale 中说明
```

### F.2 降级 Prompt（规则模式，不调用解析 Agent）

当解析 Agent 不可用时，使用以下规则做降级分类：

```python
def fallback_classify(window_text: str) -> dict:
    """纯规则降级分类，不依赖 LLM。"""
    text = window_text.lower()

    # 检测路径/端口/配置值 → memory
    if re.search(r"(/[\w./\-]+|[A-Z]:\\[\w\\.\-]+|:\d{2,5}|=\S+)", text):
        return {"kind": "memory", "confidence": 0.5, "requires_human_review": True}

    # 检测错误/失败/修复 → experience
    if any(kw in text for kw in ["error", "失败", "修复", "traceback", "crash"]):
        return {"kind": "experience", "confidence": 0.5, "requires_human_review": True}

    # 检测决策/选择/决定 → adr
    if any(kw in text for kw in ["决定", "选择", "方案", "权衡"]):
        return {"kind": "adr", "confidence": 0.5, "requires_human_review": True}

    # 默认 → memory（低置信度）
    return {"kind": "memory", "confidence": 0.3, "requires_human_review": True}
```
