# OpenClaw Upstream Migration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将当前仓库从“自管运行时 + 本地增强脚本”收敛为“官方 OpenClaw 核心 + 本地 workflow overlay”，复用官方稳定能力，同时保留任务治理、巡检、自进化等业务层能力。

**Architecture:** `vendor/openclaw-official/` 作为唯一官方核心运行时，负责 gateway、agents、channels、cron、hooks、plugins、skills 的加载与执行。本仓只保留 overlay：`scripts/openclaw-ops/` 负责治理和自动化，`hooks/` 负责本地增强钩子，`cron/jobs.json` 负责业务任务定义，`integration/openclaw-bridge/` 负责边界与桥接。

**Tech Stack:** OpenClaw official core (TypeScript/Node), local ops layer (Python), Git submodule, official cron/hooks/plugins/skills surfaces, Telegram channel.

---

## Assumptions

- 目标不是把本仓重写成官方仓库，而是让本仓变成官方仓库的“稳定增强层”。
- 近期不把 `scripts/openclaw-ops/` 的 Python 治理逻辑迁移到官方 TypeScript 内核。
- 近期不删除旧脚本，只做收口、桥接、降耦合。

## Option Comparison

### Option A: 继续深改官方核心

- 做法：直接改 `vendor/openclaw-official/src/*`，把本地 cron、hooks、task-center 逻辑塞进官方代码。
- 优点：运行时入口最少，看起来“一体化”。
- 缺点：每次升级都要手工处理冲突，风险最高。

### Option B: 官方核心 + 本地 Overlay（推荐）

- 做法：官方核心只做运行时和扩展装载，本地仓库存放治理、审计、巡检和业务规则，通过 cron/hooks/plugins/skills 接入。
- 优点：升级边界清晰，复用官方能力最多。
- 缺点：短期内会同时存在 Node 核心和 Python overlay。

### Option C: 保持现状，仅定期同步上游

- 做法：继续以本地脚本为中心，只把官方仓库当参考源码。
- 优点：改动最少。
- 缺点：后续仍然重复造轮子，无法真正降低维护成本。

**Recommendation:** 采用 Option B。你当前仓库的核心价值在治理逻辑，不在重写 OpenClaw 运行时；把运行时收敛到官方，把治理留在 overlay，成本最低，升级最稳。

## Ownership Mapping

- 官方核心负责：
  - `vendor/openclaw-official/src/cron`
  - `vendor/openclaw-official/src/hooks`
  - `vendor/openclaw-official/src/plugins`
  - `vendor/openclaw-official/extensions`
  - `vendor/openclaw-official/skills`
- 本地 overlay 负责：
  - `scripts/openclaw-ops/`
  - `scripts/openclaw-ops/policy/`
  - `cron/jobs.json`
  - `hooks/`
  - `openclaw/openclaw.json`
  - `integration/openclaw-bridge/`

## Migration Rules

- 禁止直接修改 `vendor/openclaw-official/`。
- 任何官方行为覆盖，优先走：
  - `openclaw/openclaw.json`
  - `cron/jobs.json`
  - `hooks/`
  - `plugins` / `skills`
  - `integration/openclaw-bridge/`
- 只有无法通过扩展面实现时，才记录到 `patches/openclaw/`。

### Task 1: Freeze the Runtime Boundary

**Files:**
- Modify: `docs/2026-03-06-openclaw官方上游接入最小方案.md`
- Modify: `openclaw/openclaw.json`
- Modify: `scripts/openclaw-ops/install_workflow_profile.py`
- Create: `integration/openclaw-bridge/runtime-boundary.md`

**Step 1: 明确单一运行时入口**

- 规定官方运行时根为 `vendor/openclaw-official/`。
- 规定本仓不再假定自己是 OpenClaw 主程序仓库。

**Step 2: 收口配置源**

- 让 `openclaw/openclaw.json` 成为 overlay 配置源。
- `install_workflow_profile.py` 只写配置、安装任务、注册 hooks/plugins，不再复制官方核心代码。

**Step 3: 验证边界**

Run: `python skills/library/openclaw-workflow-manager/scripts/openclaw_upstream_binding.py status`
Expected: `vendor_exists=true`, `is_submodule=true`, `vendor_ref_exact_tag=v2026.3.2`

### Task 2: Converge Cron onto Official Scheduler Surface

**Files:**
- Modify: `cron/jobs.json`
- Modify: `scripts/openclaw-ops/cron_setup.py`
- Modify: `scripts/openclaw-ops/install_project_index_job.py`
- Modify: `scripts/openclaw-ops/install_reviewer_scan_jobs.py`
- Modify: `scripts/openclaw-ops/install_task_executor_job.py`

**Step 1: 保留业务 job，停止自造调度语义**

- 继续使用 `cron/jobs.json` 作为业务任务定义。
- 以后所有 job 的安装、启停、查看都优先对齐官方 cron 表面。

**Step 2: 将安装脚本改成“生成兼容 job + 调用官方 cron 管理”**

- 本地 `install_*` 脚本只负责生成 payload。
- 运行时状态查询统一走官方入口。

**Step 3: 清理双轨任务**

- 标记 `optimize_*` 外部链路为 legacy。
- 官方 cron 主链只保留一条生产路径。

**Step 4: 验证**

Run: `openclaw cron status --json`
Expected: 能看到已安装任务和启用状态

Run: `openclaw cron run <id> --force`
Expected: 指定任务可被官方调度入口触发

### Task 3: Repackage Local Hooks as Officially Managed Hooks

**Files:**
- Modify: `openclaw/openclaw.json`
- Modify: `scripts/openclaw-ops/install_workflow_profile.py`
- Modify: `skills/library/fleet-sync/scripts/sync_openclaw_ops_files.py`
- Create: `integration/openclaw-bridge/hooks-install.md`

**Step 1: 停止“手工散落同步 hook 文件”**

- 不再依赖把 hook 目录散落复制到 `~/.openclaw`。
- 优先使用官方 hooks loader 和 install/link 机制。

**Step 2: 统一 hook 装载策略**

- 本地开发环境优先 `openclaw hooks install -l <path>`。
- 部署环境优先显式配置 `hooks.internal.load.extraDirs`。

**Step 3: 让本地 hook 只关心增强逻辑**

- `hardflow-audit`
- `hardflow-command-guard`
- `hardflow-policy-enforcer`
- `hardflow-stop-gate-reminder`

这些 hook 继续存在，但不再承担“运行时装配”职责。

**Step 4: 验证**

Run: `openclaw hooks list --json`
Expected: 能看到本地 hook 和内置 hook

Run: `openclaw hooks check`
Expected: 装载状态正常，无缺失 handler

### Task 4: Keep Governance in Python, Expose It Through Stable Bridge Points

**Files:**
- Modify: `skills/library/control-plane-ops/scripts/policy/policy_enforcer.py`
- Modify: `skills/library/control-plane-ops/scripts/policy/task_center.py`
- Modify: `skills/library/control-plane-ops/scripts/policy/project_index_maintainer.py`
- Modify: `skills/library/control-plane-ops/scripts/policy/task_executor_runner.py`
- Create: `integration/openclaw-bridge/governance-bridge.md`

**Step 1: 明确哪些逻辑不进官方核心**

- `task_center`
- `next-todo`
- `report-agent-result`
- `project_index_maintainer`
- reviewer / evolution / patrol 系列 runner

这些属于你的业务治理层，不应强行迁到官方 `src/*`。

**Step 2: 统一桥接入口**

- 所有治理命令通过 cron、hooks 或 webhook 进入。
- 不允许 Python 脚本直接修改官方内部状态文件格式。

**Step 3: 稳定输出契约**

- 统一用 `NO_REPLY`、结构化 JSON、task-center 记录做返回面。
- 官方运行时只负责触发，不感知治理内部实现。

**Step 4: 验证**

Run: `python skills/library/control-plane-ops/scripts/policy/policy_enforcer.py next-todo --limit 3`
Expected: 仍可独立返回任务

Run: `python skills/library/control-plane-ops/scripts/policy/policy_enforcer.py report-agent-result --help`
Expected: CLI 契约保持稳定

### Task 5: Move Channel and Plugin Capability Back to Official Surfaces

**Files:**
- Modify: `openclaw/openclaw.json`
- Modify: `scripts/openclaw-ops/install_workflow_profile.py`
- Modify: `docs/2026-03-04-项目规划对照与优化建议.md`
- Create: `integration/openclaw-bridge/plugin-policy.md`

**Step 1: 渠道能力以官方 channels/plugins 为准**

- Telegram 使用官方 channel/plugin 能力。
- 本仓不再维护私有渠道实现分支。

**Step 2: 业务增强只做配置和包装**

- 比如 agent routing、allowFrom、workspace、agentDir 继续由本地配置维护。
- 但具体渠道协议、消息收发、plugin 生命周期交给官方。

**Step 3: 验证**

Run: `openclaw plugins list`
Expected: 已启用插件清单可见

Run: `openclaw config get channels.telegram`
Expected: Telegram 配置从统一入口可读

### Task 6: Remove Dual-Track Delivery and Add Acceptance Checks

**Files:**
- Modify: `scripts/openclaw-ops/README.md`
- Modify: `docs/2026-03-06-openclaw官方上游接入最小方案.md`
- Create: `integration/openclaw-bridge/acceptance-checklist.md`

**Step 1: 标记 legacy 路径**

- 任何仍依赖“手工复制官方文件”或“外部 optimize_* 独立链路”的流程标为 legacy。

**Step 2: 增加验收清单**

- 上游版本是否固定
- cron 是否由官方入口可见
- hooks 是否由官方 loader 可见
- 本地治理脚本是否仍可独立运行
- Telegram 是否仍可收发

**Step 3: 验证**

Run: `python skills/library/openclaw-workflow-manager/scripts/openclaw_upstream_binding.py status`
Expected: 上游绑定正常

Run: `openclaw cron status`
Expected: 调度入口正常

Run: `openclaw hooks list`
Expected: hook 可见

Run: `git diff -- vendor/openclaw-official`
Expected: 无本地业务改动直接写入官方源码

## Execution Order

1. 先做 Task 1，冻结边界和配置源。
2. 再做 Task 2，把 cron 收敛到官方调度面。
3. 然后做 Task 3，把 hooks 改成官方可管理安装。
4. 再做 Task 4，稳定 Python 治理桥接层。
5. 接着做 Task 5，把 channels/plugins 彻底收口到官方表面。
6. 最后做 Task 6，清 legacy 和补验收。

## Success Criteria

- 你可以升级 `vendor/openclaw-official` 而不必回改本地治理逻辑。
- 本地仓库不再承担 OpenClaw 核心运行时职责。
- 官方 cron/hooks/plugins/skills 都成为正式入口。
- `scripts/openclaw-ops/` 只保留业务治理和自动化，不再兼任运行时补丁层。
