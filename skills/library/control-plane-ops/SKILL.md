---
name: control-plane-ops
description: >
  OpenClaw 控制面运维技能。用于系统状态巡检、Agent manifest 审查、
  调度注册表导出、Cron 卡住恢复、运行时绑定检查、配置快照对比。
  当需要查看系统健康状态、诊断 Agent/Cron 问题时使用。
metadata: {"openclaw": {"requires": {"bins": ["python3"]}, "os": ["linux"]}}
---

# 控制面运维操作手册

## 适用场景

- 查看 OpenClaw 系统整体健康状态
- 诊断 Agent 能力绑定问题（Skill 缺失、manifest 不一致）
- 检查 Cron Job 状态（卡住、失败、漂移）
- 导出或对比调度注册表
- 恢复卡住的 Cron running 状态

## 操作流程

### 1. 系统状态概览

```bash
# 检查 Gateway 进程
ps aux | grep openclaw-gateway | grep -v grep

# 检查 OpenClaw 状态
openclaw status 2>/dev/null || echo "openclaw CLI not available"

# 查看 Agent 列表
cat ~/.openclaw/agents/*/agent.json 2>/dev/null | head -n 50
```

### 2. Agent 能力审查

```bash
# 运行时绑定检查（仓库 vs 运行态差异）
python3 ~/scripts/openclaw-ops/inspect_runtime_bindings.py
```

审查要点：
- 每个 Agent 的 `declared_skills` 是否与实际 Skill 目录匹配
- `missing_skills` 是否为空
- `capability_mode` 是否正确（`skill_backed` vs `role_only`）

### 3. Cron 调度巡检

```bash
# 导出调度注册表
python3 ~/scripts/openclaw-ops/export_schedule_registry.py

# 查看 jobs.json 状态
cat ~/.openclaw/cron/jobs.json | python3 -m json.tool | head -n 100
```

异常检查：
- `runningAtMs` 非空但超过 1 小时 → 任务卡住
- `lastError` 非空 → 最近执行失败
- `enabled: false` → 被禁用的任务

### 4. 卡住恢复

```bash
# 恢复 stale running 状态（安全操作，只清理超时标记）
python3 ~/scripts/openclaw-ops/recover_stale_cron_running_state.py
```

### 5. 配置快照对比

```bash
# 配置看门狗状态
python3 ~/scripts/openclaw-ops/config_watchdog.py --status
```

## 核心脚本

| 脚本 | 用途 |
|------|------|
| `inspect_runtime_bindings.py` | 仓库 vs 运行态绑定差异 |
| `export_schedule_registry.py` | 调度注册表导出 |
| `recover_stale_cron_running_state.py` | Cron 卡住恢复 |
| `config_watchdog.py` | 配置变更检测 |
| `policy_enforcer.py` | 策略执行引擎 |

## 约束

- 巡检操作只读，不修改运行态配置
- 恢复操作仅清理 stale 标记，不重新触发任务
- 发现异常必须输出结构化报告（JSON 或 Markdown）
