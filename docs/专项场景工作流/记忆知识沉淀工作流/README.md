# 记忆知识沉淀工作流

## 目标

把项目事实、决策、失败经验和可复用模式转为可追溯、可去重的记忆条目，不绑定具体项目名或 Runtime。

## 当前 owner

- 来源探测：`skills/library/cross-runtime-memory-distiller/scripts/runtime_probe.py`
- 蒸馏入口：`skills/library/cross-runtime-memory-distiller/scripts/distill_runner.py`
- 写入门禁：`skills/library/cross-runtime-memory-distiller/scripts/memory_write_gateway.py`
- 项目写回：`scripts/openclaw-ops/project_memory_writer.py`
- 来源变化：`scripts/openclaw-ops/source_registry_watcher.py`

## 验收

来源、证据、分类、去重键和写入结果均可回读；失败条目保留原因，不把推测写成稳定事实。
