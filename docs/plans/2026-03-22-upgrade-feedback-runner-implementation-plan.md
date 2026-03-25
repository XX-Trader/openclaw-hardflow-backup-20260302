# Upgrade Feedback Runner Implementation Plan

## 2026-03-22 第四批 install/cron registry promotion 接线记录

- 已把 `workflow_profile_registry`、`auto_apply_workflow_promotion`、`promotion_operator` 接入 `cron_setup.py`
  - `build_upgrade_feedback_job(...)` 现在会把这三项参数传给 `upgrade_feedback_runner.py`
  - `cron_setup` 参数解析与 install-time 校验也已同步补齐
- 已把默认安装命令接到 runtime workflow registry
  - `install_workflow_profile.py` 生成的 cron setup 命令会默认注入 `--upgrade-feedback-workflow-profile-registry`
  - 默认会开启 `--upgrade-feedback-auto-apply-workflow-promotion`
  - 默认 operator 为 `cron-upgrade-feedback`
- 已补齐专项验证
  - `test_upgrade_feedback_runner.py` 新增断言覆盖 cron job message 与 install 命令渲染
  - 确认 upgrade feedback runner 安装链路已具备 registry 自动晋升的运行时参数

## 2026-03-22 第三批 promotion / rollback control plane 落地记录

- 已新增 `scripts/openclaw-ops/workflow_promotion_controller.py`
  - 提供 `promote` / `rollback` CLI
  - 读取 workflow upgrade summary 与 runtime registry
  - 仅在 `workflow_scorecard.decision.promote_to_new_baseline = true` 时允许晋升
  - 持久化 `promotion_history`、`last_promotion`、`rollback_history`、`last_rollback`
- 已把 `upgrade_feedback_runner.py` 接入 workflow registry promotion
  - 新增 `workflow_profile_registry`、`auto_apply_workflow_promotion`、`promotion_operator` 参数
  - runner summary 会输出 `workflow_registry_promotion`
  - state file 会记录最近一次 registry promotion 状态
- 已补齐专项验证
  - `test_workflow_promotion_controller.py` 覆盖 promote / rollback
  - `test_upgrade_feedback_promotion.py` 覆盖 runner 自动晋升 registry
  - 与既有 `test_upgrade_feedback_runner.py` 一起回归通过

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把 baseline/candidate 升级评分从孤立脚本接入 OpenClaw 主链，形成可调度、可回写、可验收的升级反馈 runner。

**Architecture:** 先新增一个只读现有 executor reports 的 `upgrade_feedback_runner.py`，输出 workflow scorecard 与 skill review；再把它接入 `cron_setup.py` 与 `install_workflow_profile.py`，让安装流程能自动装配这条低风险反馈链路。整个过程坚持 TDD，每个阶段都先写失败测试，再写最小实现，再跑验证。

**Tech Stack:** Python 3、unittest、现有 `workflow_upgrade_scoring.py` / `skill_evolution_review.py`、OpenClaw cron 安装器。

---

### Task 1: Upgrade Feedback Runner

**Files:**
- Create: `tests/scripts_openclaw_ops/test_upgrade_feedback_runner.py`
- Create: `scripts/openclaw-ops/upgrade_feedback_runner.py`

**Step 1: Write the failing test**

- 断言 runner 能从 executor reports 自动切 baseline/candidate 窗口
- 断言会产出 workflow scorecard、skill review、summary JSON
- 断言 state file 能阻止相同 candidate runs 重复产出

**Step 2: Run test to verify it fails**

Run: `python tests/scripts_openclaw_ops/test_upgrade_feedback_runner.py`
Expected: FAIL with module/file missing or missing function

**Step 3: Write minimal implementation**

- 读取 executor run 目录
- 选择 baseline/candidate 窗口
- 调用 `workflow_upgrade_scoring.py` 与 `skill_evolution_review.py`
- 落盘 `summary.json`、`workflow-scorecard.json`、`skill-review.md`
- 维护 `state.json`

**Step 4: Run test to verify it passes**

Run: `python tests/scripts_openclaw_ops/test_upgrade_feedback_runner.py`
Expected: PASS

### Task 2: Install Entry And Cron Wiring

**Files:**
- Modify: `scripts/openclaw-ops/cron_setup.py`
- Modify: `scripts/openclaw-ops/install_workflow_profile.py`
- Modify: `scripts/openclaw-ops/README.md`
- Modify: `skills/library/openclaw-workflow-manager/references/workflow-map.md`

**Step 1: Write the failing test**

- 断言 `cron_setup.py` 新增 `build_upgrade_feedback_job`
- 断言 `install_workflow_profile.py --dry-run --emit-json` 会包含升级反馈安装步骤

**Step 2: Run test to verify it fails**

Run: `python tests/scripts_openclaw_ops/test_upgrade_feedback_runner.py`
Expected: FAIL with missing cron/install wiring assertions

**Step 3: Write minimal implementation**

- 增加 `--install-upgrade-feedback-job` 及相关参数
- 默认把升级反馈 job 作为 maintenance job 接入
- 在安装流程 dry-run 输出中暴露该步骤
- 文档和地图补入口

**Step 4: Run test to verify it passes**

Run: `python tests/scripts_openclaw_ops/test_upgrade_feedback_runner.py`
Expected: PASS

### Task 3: End-To-End Verification

**Files:**
- Reuse: `tests/scripts_openclaw_ops/test_workflow_upgrade_scoring.py`
- Reuse: `tests/scripts_openclaw_ops/test_skill_evolution_review.py`
- Reuse: `tests/scripts_openclaw_ops/test_upgrade_feedback_runner.py`

**Step 1: Run verification commands**

- `python -m py_compile scripts/openclaw-ops/upgrade_analysis.py scripts/openclaw-ops/workflow_upgrade_scoring.py scripts/openclaw-ops/skill_evolution_review.py scripts/openclaw-ops/upgrade_feedback_runner.py`
- `python tests/scripts_openclaw_ops/test_workflow_upgrade_scoring.py`
- `python tests/scripts_openclaw_ops/test_skill_evolution_review.py`
- `python tests/scripts_openclaw_ops/test_upgrade_feedback_runner.py`

**Step 2: Confirm output**

- 新 runner 可以稳定产出报告
- 安装入口能声明式装配这条链路
- 旧评分脚本不回归
