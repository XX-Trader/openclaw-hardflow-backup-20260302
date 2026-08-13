---
name: engineering-cybernetics-experience-loop
description: "Use when any runtime-host Hermes agent consolidates work experience under Qian Xuesen's Engineering Cybernetics standard: store only bottom-level logic in memory, put reusable procedures in skills, and run an end-of-day skill curation loop."
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [cybernetics, memory, skills, runtime-host, writeback, operations]
    related_skills: [hermes-agent, hermes-agent-skill-authoring, project-delivery-runtime-host-hermes-ops]
---

# Engineering Cybernetics Experience Loop

## Overview

This skill is the shared experience-writeback rule for runtime-host Hermes agents. Use Qian Xuesen's 《工程控制论》 as the first standard for learning from TARGET_PROJECT, hardflow workflow/runtime/profile, and multi-agent operations.

Treat every task as a controlled engineering system with goals, boundaries, observations, feedback, control actions, disturbances, safety constraints, verification, and adaptive correction.

The storage split is strict:

- **Memory:** bottom-level logic, stable facts, user preferences, durable environment conventions, and long-lived safety invariants only.
- **Skills:** procedures, commands, workflows, examples, pitfalls, verification recipes, review/deploy checklists, runbooks, and daily curation routines.

## When to Use

Use this after:

- completing a complex runtime-host / SmartMulti / hardflow / Hermes profile task;
- receiving a user correction about workflow, memory, skills, review gates, routing, or operating standards;
- discovering a repeatable failure mode or recovery pattern;
- deciding whether knowledge belongs in memory or skills;
- doing end-of-day cleanup of agent-created or agent-maintained skills.

Do **not** use it to bypass Discord route selection. For new Discord tasks, first obtain the user's explicit route choice, then apply this skill inside the chosen route.

## Primary Standard: Engineering Cybernetics

For every lesson, express the control loop before writing it back:

1. **Control objective / target state** — what stable state the system should reach.
2. **Controlled object and boundary** — business repo, workflow runtime, profile, API, service, Feishu table, Task Center, agent handoff, or human approval path; also what is outside scope.
3. **Observable signals** — status cards, tests, logs, API smoke, git state, Task Center artifacts, reviewer verdicts, user acceptance, gateway state, or runtime health.
4. **Feedback path** — how observations are compared against the target; include delay, noise, stale artifacts, false positives, and missing evidence.
5. **Controller / decision rule** — which agent/operator/stage decides the next action and under what rule.
6. **Actuator / action** — code change, config change, runtime install, restart, documentation writeback, skill patch, memory update, pipeline rerun, or manual escalation.
7. **Disturbance / uncertainty** — dirty worktrees, stale runtime copies, credential boundaries, vague requirements, reviewer drift, artifact mismatch, permission errors, or channel routing ambiguity.
8. **Safety and stability constraints** — no secret printing, no unsafe reset/force push, no production data deletion, no destructive production actions without an explicit target, verified backup, audit record, and rollback command.
9. **Verification and acceptance** — targeted tests, `git diff --check`, compileall, smoke, remote containment, status-card evidence, gateway state, or explicit manual acceptance.
10. **Adaptive correction** — if feedback fails, patch the controller/skill/workflow rather than repeating the same open-loop action.

## Memory vs Skill Decision Gate

### Put in memory only when it is bottom-level logic

Good memory candidates:

- stable user preference or correction;
- canonical project identity, live host, durable path, or environment convention;
- invariant safety principle;
- high-level control logic that should shape future behavior.

Memory format:

- declarative fact, not imperative instruction;
- compact, no raw logs or command transcripts;
- no temporary task state or completed-work diary;
- no secrets, tokens, credentials, cookies, auth JSON, private keys, or sensitive values.

### Put in skills when it is reusable procedure

Good skill candidates:

- step-by-step workflow;
- exact commands or safe command patterns;
- test/review/deploy checklist;
- troubleshooting playbook;
- API/tool quirks;
- examples from a successful or failed task;
- pitfalls and how to verify them;
- daily/weekly curation routine.

Prefer patching an existing skill when the new lesson refines an existing workflow. Create a new skill only when no current skill has the right trigger scope.

## End-of-Day Skill Curation Loop

At the end of a work day, run this closed loop:

1. **Collect observations**
   - Review completed sessions, status cards, failed/recovered runs, user corrections, tool evidence, tests, gateway/API smoke, and git state.
   - Exclude secrets and raw credentials.

2. **Normalize into control-loop facts**
   - For each meaningful lesson, fill: objective, object, signal, feedback, controller, action, disturbance, safety, verification, acceptance.

3. **Separate memory from skill**
   - Keep only the bottom logic or stable convention as a compact memory entry.
   - Move procedures, commands, cases, and failure patterns into skills.

4. **Patch before creating**
   - Search existing skills by trigger terms.
   - Patch the most relevant skill if it already exists.
   - Create a new skill only for a genuinely new reusable workflow.

5. **Structure each changed skill by control loop**
   - Trigger / when to use
   - Target state
   - Controlled object and boundary
   - Observables / evidence
   - Feedback and decision rule
   - Actions / commands
   - Disturbances and failure modes
   - Safety constraints
   - Verification checklist
   - Writeback rule

6. **Reduce duplication**
   - Merge overlapping notes into one umbrella skill when safe.
   - Do not delete skills without explicit user confirmation.
   - If a skill is stale, patch it with the corrected control rule and mark old pitfalls as resolved or superseded.

7. **Verify**
   - Re-read changed skills.
   - Check frontmatter and descriptions.
   - Confirm each skill contains actionable verification steps.
   - Confirm memory does not contain task logs or procedural dumps.

## Daily Output Template

```markdown
# 工程控制论式 Skill 梳理

## 今日控制对象
- 对象：
- 目标态：
- 关键反馈：
- 主要扰动：

## 写入 memory 的底层逻辑
- <只列原则/稳定事实>

## 写入或更新的 skills
- `<skill-name>`：新增/修正的流程、坑点、验证

## 被拒绝写入 memory 的内容
- <命令、案例、临时状态、日志等，已放 skill 或不保留>

## 闭环验证
- skill 已重读：是/否
- 重复 skill 已检查：是/否
- 安全边界已检查：是/否
```

## Common Pitfalls

1. **把工作日志塞进 memory。** Memory 只保留底层逻辑和稳定事实；日志、步骤、案例进入 skill 或引用文件。
2. **把 skill 写成流水账。** Skill 必须能指导下一次行动：触发条件、步骤、坑点、验证都要明确。
3. **没有控制对象边界。** 不区分业务仓库、hardflow runtime、profile/SOUL、Feishu、Task Center，会导致错误执行链路。
4. **只总结成功，不总结反馈失败。** 控制论关注反馈误差；失败、误报、延迟、扰动更应该进入 skill 的 pitfall/verification。
5. **重复创建小 skill。** 先搜索并 patch 现有技能，避免技能库碎片化。
6. **忽略安全稳定性。** 涉及 secret、git、runtime、生产数据动作时，安全约束是控制系统稳定性的组成部分，不是附注。
7. **把单个 profile 的规则误当通用规则。** 通用规则必须落到 source SOUL / live SOUL / shared skill，不能只写当前聊天 profile 的 memory。

## Verification Checklist

- [ ] Lesson expressed as target/object/signal/feedback/action/disturbance/safety/verification.
- [ ] Memory entry, if any, is compact and declarative.
- [ ] Procedures and commands are in a skill, not memory.
- [ ] Existing skills were searched before creating a new one.
- [ ] Changed skill was re-read or otherwise verified.
- [ ] No secrets, credentials, or temporary task logs were stored.
- [ ] For Discord work, route-selection discipline remains intact.
- [ ] For all-agent rules, source SOUL, live SOUL, and shared skill copies are aligned where applicable.
