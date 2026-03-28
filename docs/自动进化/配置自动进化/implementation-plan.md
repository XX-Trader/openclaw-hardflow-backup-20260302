# 配置自动进化 — 实施计划

> 最后更新：2026-03-29
> 需求文档：[architecture.md](architecture.md)
> 所属路线图：[阶段四·任务 4.2 / 4.3](../../execution-roadmap.md)

---

## 1. 模块划分

```
配置自动进化
├── 模块A：下行部署（GitHub → 服务器）
│   ├── Cron: auto_update_daily
│   └── 入口: setup.py → workflow_setup.py
│
├── 模块B：本地快照（运行时变更 → 本地 git）
│   ├── Cron: 待新建（每1小时）
│   └── 脚本: 待新建 local_snapshot_runner.py
│
├── 模块C：变更审核（检测 + 审核）
│   ├── Cron: config_diff_review（每6小时）
│   └── 逻辑: 已内建于 optimization-agent
│
└── 模块D：上行推送（审核通过 → GitHub）
    ├── Cron: ops_git_sync_push（每6小时）
    ├── 执行器: git_sync_push_runner.py
    └── 安装器: install_git_sync_job.py
```

## 2. 代码位置索引

| 模块 | 文件 | 路径 | 行数 | 状态 |
|------|------|------|------|------|
| A·部署入口 | `setup.py` | 项目根目录 | 72 | ✅ 已有 |
| A·安装核心 | `workflow_setup.py` | `scripts/openclaw-ops/policy/` | — | ✅ 已有 |
| B·本地快照 | `local_snapshot_runner.py` | `scripts/openclaw-ops/` | 170 | ✅ 已建 |
| B·Cron 注册 | `register_snapshot_cron.py` | 一次性脚本 | — | ✅ 已执行 |
| C·变更审核 | — | optimization-agent 内建 | — | ✅ 已有 |
| D·Sync 执行器 | `git_sync_push_runner.py` | `scripts/openclaw-ops/` | 652 | ✅ 已有 |
| D·Cron 安装器 | `install_git_sync_job.py` | `scripts/openclaw-ops/` | 259 | ✅ 已有 |

## 3. 实施步骤

### Phase 1：修复 B 层 Clone

- [ ] 在 nofx 服务器 git clone 创建 `/root/openclaw-hardflow-backup-20260302/`
- [ ] 验证 `openclaw.json` 中 `HOOKS_SOURCE_DIR` / `SKILLS_SOURCE_DIR` 可达
- [ ] 手动触发 `auto_update_daily` 验证 pull + install 正常

### Phase 2：配置 C 层同步通道

- [ ] 确认同步策略（C 层直推 GitHub 还是 B 层中转）→ **待用户裁决**
- [ ] 给 `.openclaw/.git` 配置 remote origin 或修改 sync 脚本走 B 层
- [ ] 配置 `.gitignore` 排除运行时临时文件
- [ ] 验证 `ops_git_sync_push` 端到端推送成功

### Phase 3：新建每小时快照 ✅

- [x] 编写 `local_snapshot_runner.py`（C→B 层同步，白名单+排除+内容比对）
- [x] 通过 `register_snapshot_cron.py` 注册为每小时 cron 任务（id=`70a5f20a`）
- [x] 配置排除列表（sessions/auth-profiles/.bak/exception-reports/等）
- [x] 首次同步测试通过，0 错误

### Phase 4：端到端验证

- [ ] Windows 修改 hook → push → 服务器 `auto_update_daily` 拉取安装
- [ ] 服务器修改 config → 小时快照 → `ops_git_sync_push` 推送 → Windows pull

## 4. 待裁决项

| 编号 | 问题 | 影响 |
|------|------|------|
| D1 | C 层变更直接 push，还是通过 B 层中转？ | 决定 Phase 2 实施方案 |
| D2 | B 层路径是否确认为 `/root/openclaw-hardflow-backup-20260302/`？ | 决定 Phase 1 clone 目标 |
| D3 | 快照排除哪些目录？ | 决定 Phase 3 .gitignore 配置 |
