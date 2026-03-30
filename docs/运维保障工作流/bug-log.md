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

---

## 需人工确认 (无法远程自动修复)

### MANUAL-001: 🔴 Gateway 连接失败
- **现象**: `Gateway call failed: Error: gateway closed (1000)`，出现 5+ 次
- **影响**: `optimization-agent` 和 `project-agent` 全部执行失败，整个任务执行链瘫痪
- **待确认**:
  1. SSH 到 NOFX 服务器检查 Gateway 进程是否存活
  2. 查看 Gateway 异常日志
  3. 必要时重启 Gateway
- **备注**: 本次 SSH 连接也超时，可能服务器本身有问题

### MANUAL-002: 🟡 Git 同步冲突
- **现象**: `本地有未处理改动且落后远端，需人工处理后再 pull`
- **待确认**:
  ```bash
  cd ~/openclaw-hardflow-backup-20260302
  git status
  git stash
  git pull --ff-only origin main
  git stash pop  # 按需
  ```

### MANUAL-003: 🟡 派单能力不匹配（3个任务）
- **现象**: `optimization-agent` 能力绑定不覆盖部分任务类型（周度复盘/reviewer context）
- **待确认**: 检查 `task_capability_binding.py` 或 `runtime-binding.json` 中的 agent 能力映射

### MANUAL-004: 🟢 审查上下文门禁阻塞
- **现象**: `project-agent` 无法产出上下文包，日增量审查和周结构审查被跳过
- **依赖**: 修复 MANUAL-001 (Gateway) 后应自动恢复

### MANUAL-005: ~~升级~~已修复 — upgrade_feedback 输出精简
- **严重级**: 🟡 P1
- **修复**: 将 `upgrade_feedback_runner.py` 第777行的默认输出从 raw JSON 改为精简人类可读摘要（状态 + 基线/候选均分 + 晋升决策 + 否决原因），`--emit-json` 模式不受影响
