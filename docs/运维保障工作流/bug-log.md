# NOFX OpenClaw Bug 记录 (2026-03-30)

## 已修复 (本次代码提交)

### BUG-001: SQLite `no such table: benchmark_runs`
- **严重级**: 🔴 P0
- **根因**: `control_plane_summary_runner.py` 和 `control_plane_optimization_advisor.py` 创建 `TaskCenter` 实例后未调用 `init_schema()`，直接查询 `benchmark_runs` 表。如果数据库文件是首次创建或被重建，表结构不存在导致崩溃。
- **修复**: 在两个文件中新增 `task_center.init_schema()` 调用
- **影响文件**:
  - `scripts/openclaw-ops/control_plane_summary_runner.py` (第144行)
  - `scripts/openclaw-ops/control_plane_optimization_advisor.py` (第90行)

### BUG-002: 缺失目录警告刷屏 Telegram
- **严重级**: 🟡 P1
- **根因**: `unified_exception_logger.py` 和 `memtidy_runner.py` 在扫描目录不存在时直接输出到 stderr/stdout，被 cron delivery 转发到 Telegram
- **涉及目录**:
  - `/root/.openclaw/sessions/` — 部分节点无 sessions 顶级目录（正常，session 在 `agents/*/sessions` 下）
  - `/root/.openclaw/memory/` — 部分节点未启用 memory 功能
  - `/root/.openclaw/workspace/memory/` — 同上
- **修复**: 将 `print(⚠️ 目录不存在)` 改为静默 `continue`
- **影响文件**:
  - `scripts/openclaw-ops/unified_exception_logger.py` (第247行)
  - `scripts/openclaw-ops/memtidy_runner.py` (第337行)

### BUG-003: 配置文件 Windows 路径在 Linux 上无效
- **严重级**: 🟡 P1
- **根因**: 部署时 `cron-monitor-config.json` 从 Windows 本地直接复制到 NOFX Linux 服务器，其中所有路径均为 `C:\Users\superma\.openclaw\...`，在 Linux 上无法解析
- **受影响字段**: `task_center_db`, `routing_file`, `scan_dirs`, `log_patterns` 等
- **表现**: 日志中出现 `task_center_db_missing:C:\Users\superma.openclaw\ops\task-center\task_center.db`
- **修复**: Python 脚本批量替换 `C:\Users\superma\` → `/root/`，修复了 `cron-monitor-config.json` 和 `cron-monitor-state.json`
- **防止复发**: 部署脚本应做路径适配（`Path.home()` 动态生成或部署时 sed 替换）

---

## 需人工确认 (无法远程自动修复)

### MANUAL-001: ~~待确认~~已确认 — Gateway 正常运行
- **原现象**: `Gateway call failed: Error: gateway closed (1000)`
- **实际状态**: SSH 确认 Gateway 正常运行 (PID 2483467, 30.8% 内存, 已运行超过 17 小时)
- **结论**: 上次报错可能是瞬时故障，已自行恢复

### MANUAL-002: ~~待确认~~已修复 — Git 同步流程重构
- **原现象**: `本地有未处理改动且落后远端，需人工处理后再 pull`
- **根因**: 旧流程先 pull 再 commit，遇本地改动就死锁
- **修复**: 重构为 commit-first → pull --rebase → push，rebase 冲突时自动 abort + 通知人工

### MANUAL-003: ~~待确认~~已修复 — 派单能力不匹配
- **原现象**: `optimization-agent` 能力绑定不覆盖部分任务类型
- **根因**: `ops-agent` 和 `optimization-agent` 在 `task_capability_binding.py` 中只有 `role_only`，缺少 `task_execution`
- **修复**: 给两个 agent 添加 `task_execution` capability (commit `4286d2dc`)

### MANUAL-004: 🟢 审查上下文门禁阻塞
- **现象**: `project-agent` 无法产出上下文包，日增量审查和周结构审查被跳过
- **依赖**: 修复 MANUAL-001 (Gateway) 后应自动恢复

### MANUAL-005: ~~升级~~已修复 — upgrade_feedback 输出精简
- **严重级**: 🟡 P1
- **修复**: 将 `upgrade_feedback_runner.py` 第777行的默认输出从 raw JSON 改为精简人类可读摘要（状态 + 基线/候选均分 + 晋升决策 + 否决原因），`--emit-json` 模式不受影响
