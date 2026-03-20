# OpenViking 记忆链路标准化说明

## 目标

把 `OpenViking` 相关表达统一成 3 层，避免继续把服务层、插件层、路由层混在一起描述。

标准三层如下：

1. 服务层：`OpenViking`
2. 插件层：`memory-openviking`
3. 路由层：`plugins.allow` + `plugins.slots.memory`

## 标准解释

### 1. 服务层

服务层只表示：

1. `openviking-server` 是否启动
2. HTTP 健康检查是否通过

健康检查地址优先级：

1. 显式参数 `--health-url`
2. 运行时 `openclaw.json` 中 `plugins.entries.memory-openviking.config` 里的：
   - `healthUrl`
   - `baseUrl`
   - `port`
3. 环境变量：
   - `OPENVIKING_HEALTH_URL`
   - `OPENVIKING_BASE_URL`
4. 默认地址：
   - `http://127.0.0.1:1933/health`

说明：

1. Windows 本机可能使用非默认端口，例如 `29333`。
2. 标准检查脚本会优先读取运行时插件配置中的端口，而不是强行假设 `1933`。

### 2. 插件层

插件层只表示：

1. `memory-openviking` 是否作为 OpenClaw 记忆插件存在并被允许运行

这里不要把插件是否存在，与服务是否存活混为一谈。

### 3. 路由层

路由层只表示：

1. `plugins.slots.memory`
2. `plugins.allow`

标准增强记忆路由：

```json
{
  "plugins": {
    "allow": ["memory-openviking"],
    "slots": {
      "memory": "memory-openviking"
    }
  }
}
```

标准官方默认路由：

```json
{
  "plugins": {
    "slots": {
      "memory": "memory-core"
    }
  }
}
```

## 运行原则

1. 若当前使用官方内置记忆，则 `mode=official-default`
2. 若当前使用增强记忆，则必须满足：
   - `plugins.slots.memory = "memory-openviking"`
   - `memory-openviking` 插件层通过
   - `OpenViking` 服务层健康检查通过

## 验收命令

```bash
python scripts/openclaw-ops/check_openviking_stack.py --workspace-root .
```

预期：

1. 若当前为官方默认记忆：
   - `mode=official-default`
   - `passed=true`
2. 若当前为 OpenViking 增强记忆：
   - `mode=openviking`
   - `routing_layer.passed=true`
   - `plugin_layer.passed=true`
   - `service_layer.passed=true`
   - `service_layer.url` 应与运行时实际端口一致

## 产物

标准检查会输出：

1. `.workflow/runs/<run_id>/acceptance/openviking-stack.json`
2. `.workflow/gates/openviking_stack.json`

## 故障分层

排障时按以下顺序判断：

1. 服务层问题：
   - 健康检查失败
   - 端口不通
2. 插件层问题：
   - `memory-openviking` 未加载
   - 不在允许运行范围
3. 路由层问题：
   - `plugins.slots.memory` 未切到 `memory-openviking`

不要再把：

1. allowlist 问题
2. slot 绑定问题
3. 服务未启动问题

混成同一类故障。
