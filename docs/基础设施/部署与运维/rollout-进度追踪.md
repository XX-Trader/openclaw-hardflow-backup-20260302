# 通用运行时发布进度

## 当前基线

- [x] 项目交付入口使用通用命名和环境变量。
- [x] Profile 模板移至 `config/runtime-profiles/`。
- [x] 实现阶段使用隔离工作区。
- [x] 验证、审查、部署、写回和发布均产生独立证据。
- [x] 部署仅在明确需求与已配置命令同时存在时启用。
- [x] 会话转录、缓存和机器专属状态从跟踪文件中移除。
- [ ] 在每个目标环境执行安装、连接器与部署 smoke。

## 环境验收表

| 环境 | Runtime Home | Profile | 安装 smoke | 路由 smoke | 项目验证 | 部署 smoke | 远端回读 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `TARGET_RUNTIME_A` | `TARGET_RUNTIME_HOME_A` | `TARGET_PROFILE_A` | pending | pending | pending | optional | pending |
| `TARGET_RUNTIME_B` | `TARGET_RUNTIME_HOME_B` | `TARGET_PROFILE_B` | pending | pending | pending | optional | pending |

## 每次发布步骤

1. 读取 `requirements.md` 与项目规则。
2. 运行安装演练和定向测试。
3. 检查配置差异、会话文件、缓存和敏感值。
4. 对明确要求部署的环境运行项目命令与烟测。
5. 提交、推送并回读远端 SHA。
6. 将失败原因和只需重跑的阶段写入进度表。

## 证据字段

- `runtime_id`
- `profile`
- `run_id`
- `command`
- `exit_code`
- `artifact_path`
- `commit_sha`
- `remote_sha`
- `rollback_result`

真实账号、频道、主机和目录由环境清单管理，不写入此仓库。
