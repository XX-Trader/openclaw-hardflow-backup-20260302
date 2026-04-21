# Shared Host Contract

## 目标

定义共享蒸馏核心与宿主适配器之间的稳定边界。

## 最小契约

- 共享核心只依赖 `RuntimeProbeResult`
- 宿主差异只存在于 `host_adapter_hermes.py` / `host_adapter_openclaw.py`
- 共享核心不直接拼宿主硬编码路径
- 宿主适配器不直接写热记忆，只负责封装解析请求与后续落盘桥接

## RuntimeProbeResult 字段

- `host`
- `runtime_kind`
- `transport`
- `distro`
- `home`
- `session_roots`
- `hot_memory_paths`
- `workspace_roots`
- `state_db`
