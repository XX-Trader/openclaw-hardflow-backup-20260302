# 实施计划与微观待办

> 状态：🗃️ 已退役，仅保留历史实现记录；`ai-session-distiller` 旧技能目录已删除。

## 阶段0：体系化技能基建封装 (Skill Wrapper)
- [x] 曾在 `~/.claude/skills/ai-session-distiller` 创建标准规范的 OpenClaw Skill 体系骨架（现已退役删除）。
- [x] 重写 `SKILL.md`，将探针引擎的防撕裂与 WAL 脏读拦截等元规则录入系统记忆能力域。
- [x] 在 `scripts/core/` 建立 `BaseSqliteExtractor.py` 及 `BaseJsonExtractor.py` 基类框架。

## 阶段1：跨端目录嗅探与探针开发
- [x] 编写环境路径读取脚本，分析 Windows 下各助手的默认存储位置。
- [x] 开发 Python 版本的只读抓取探针 (CLI Collectors)。
- [ ] 实现针对 JSON 和 SQLite 等格式的基础提取。
- [ ] **SQLite WAL 防脏读冷备镜像**：读前毫秒级克隆 `sqlite-shm/wal` 的快照读取流以逃逸底层 IDE 的锁竞争。
- [ ] 🔥实现 `.sync_cursor` 增量游标引擎（确保按增量位置截断提取）。

## 【待办挂起区】: 核心工程开发中继管网 (Pending Tasks)

未来接手执行开发的 Agent 必须依序认领并编写以下三个关键缺失模块：

### 待办 1：专有格式解析器阵列 (Format Parsers Sandbox)
**当前背景**：根据对五大引擎底层的实体探测，由于异构特征过大，必须分离派生两套基类提取器：`BaseSqliteExtractor` 与 `BaseJsonExtractor`。
- [x] **Schema 防御性探针门禁**：对 SQLite 表字典打 Hash，应对后续版本更新。发现 IDE 基建结构变动立刻触发断路器 `raise SchemaDriftException`。
- [x] **BaseSqlite - Codex 解析器**：针对 `~/.codex/logs_1.sqlite` 数百MB的大表，必须使用 `LIMIT` 游标搭配时间戳片段抽取，严禁 `SELECT *` 导致 OOM 撑爆物理内存。
- [x] **BaseSqlite - Cursor 解析器**：遍历定位 `workspaceStorage` 的哈希目录，挂载 `state.vscdb` 获取其压缩存放的 JSON 会话结构。
- [x] **BaseJson - Claude Code 解析器**：针对 `~/.claude.json` 编写提取策略，利用特有路径标识尝试推离出原工作区；并实施**全局重嗅探降级 (Global_Fallback)**。
- [x] **BaseJson - OpenClaw / Antigravity 解析器**：直接文件 I/O 序列化读取 `~/.openclaw/sessions` 与 `~/.gemini/antigravity/brain/*/logs` 下的长文本会话，轻量解析复原上下文事实。
- [x] **统一 Schema 抹平层**：将上述各处提取异构数据对准，输出为统一结构 `{ "project_workspace": "...", "git_hash": "...", "raw_conversations": [...] }`。

### 待办 2：防爆增量游标追踪引线 (`.sync_cursor_engine`)
**当前背景**：如果不设截断，每次 Cron 都会致使全量旧日志挤爆大模型缓冲区。
- [x] **断点缓存算法**：每次读入日志前核对本机器上周提取跑到了哪里，防止重放旧数据。
- [x] **防撕裂滑动分窗截断器**：替换呆板的按字切碎，采取带交集融合边距（1K Overlap）的策略或基于 LLM Turn 回合制封包来送入蒸馏层。

### 待办 3：人类仲裁法庭控制台 (Merger Arbitration CLI)
**当前背景**：碰到重大分歧盲目合并覆盖会抹黑系统长期学习积累经验。
- [x] **抗疲劳评分分流引擎 (Confidence Router)**：大模型判定冲突信标时附带提取 `ConfidenceScore(1-100)`。高确信度非阻断逻辑开启静默落盘（Auto-Merge）。
- [x] **构建挂起中枢**：仅针对低信度或根本性架构设计冲突抛出互斥停火断点。
- [x] **终端渲染比照**：像 Git-Merge 命令行一样在 PowerShell 输出差异合并结果。
- [x] **接收人类裁决命令流**：监听输入 `[1]强制覆写(同意AI新观)`, `[2]扔掉本次捕捉`, `[3]两者皆存新提ADR` 进行对应落盘控制。

## 阶段4：本地记忆库向量搜索化 (Local Vector Retrieval Schema)
- [x] 开发适用于检索经验段落集的 `vector_indexer.py` 探针（打通 ChromaDB 轻量持久化）。
- [x] 构建专属索引检索 Skill 操作手册，支撑大模型利用终端命令主动发起 Hybrid 语义查询。
