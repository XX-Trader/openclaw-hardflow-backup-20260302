# Cross Runtime Memory Distiller Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 落地 `cross-runtime-memory-distiller` 的 Phase 1，共享技能骨架、宿主路径探测与 Hermes/OpenClaw 宿主适配器最小实现。

**Architecture:** 先实现纯契约层，不接真实蒸馏与控制面。共享核心只负责 `RuntimeProbeResult`、`ParserCandidatePacket` 与宿主适配请求封装；宿主差异限制在 adapter 层。

**Tech Stack:** Python 3、argparse、unittest、JSON、Markdown references

---

### Task 1: 写 Phase 1 失败测试

**Files:**
- Create: `tests/scripts_openclaw_ops/test_cross_runtime_memory_distiller_phase1.py`

**Step 1: Write the failing test**

- 验证 `runtime_probe.py` 能同时得出 `OpenClaw=windows` 与 `Hermes=wsl`
- 验证 `host_adapter_hermes.py` / `host_adapter_openclaw.py` 会把候选窗口封装成统一的 parser packet
- 验证宿主不匹配时显式报错

**Step 2: Run test to verify it fails**

Run: `pytest tests/scripts_openclaw_ops/test_cross_runtime_memory_distiller_phase1.py -v`

### Task 2: 写共享技能骨架最小实现

**Files:**
- Create: `skills/library/cross-runtime-memory-distiller/SKILL.md`
- Create: `skills/library/cross-runtime-memory-distiller/scripts/runtime_probe.py`
- Create: `skills/library/cross-runtime-memory-distiller/scripts/host_adapter_hermes.py`
- Create: `skills/library/cross-runtime-memory-distiller/scripts/host_adapter_openclaw.py`
- Create: `skills/library/cross-runtime-memory-distiller/references/shared-host-contract.md`
- Create: `skills/library/cross-runtime-memory-distiller/references/parser-agent-contract.md`

**Step 1: Write minimal implementation**

- 先只实现 Phase 1 需要的契约和 CLI
- 不接真实 Agent 调度
- 不接真实文件写入

**Step 2: Run test to verify it passes**

Run: `pytest tests/scripts_openclaw_ops/test_cross_runtime_memory_distiller_phase1.py -v`

### Task 3: 收尾同步任务盘

**Files:**
- Modify: `todo.md`
- Modify: `done.md`

**Step 1: Move task to done**

- 将 Phase 1 实施项从 `todo.md` 移到 `done.md`

**Step 2: Final verification**

Run: `pytest tests/scripts_openclaw_ops/test_cross_runtime_memory_distiller_phase1.py -v`
