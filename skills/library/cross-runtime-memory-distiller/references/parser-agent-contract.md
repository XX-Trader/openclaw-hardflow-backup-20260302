# Parser Agent Contract

## 目标

统一 Hermes 与 OpenClaw 两侧宿主内 Parser Agent 的输入输出形状。

## 输入对象：ParserCandidatePacket

- `candidate_id`
- `host`
- `project`
- `trace_id`
- `task_id`
- `run_id`
- `source`
- `evidence_refs`
- `window_text`
- `target_schema_version`

## 输出要求

- 只能返回结构化 artifact
- 必须保留 `summary / rationale / evidence_refs / confidence / target_kind`
- 不允许直接写 `USER.md` / `MEMORY.md`

## 当前阶段限制

Phase 1 只实现请求封包与宿主适配器，不接真实宿主内 Agent 调度。
