# OpenClaw 本地配置自动进化 — 架构设计

> 最后更新：2026-03-29
> 状态：**待评审**
> 所属路线图阶段：[阶段四：自进化闭环补全](file:///H:/GitHub/openclaw-hardflow-backup-20260302/docs/execution-roadmap.md)（任务 4.2 / 4.3）

---

## 1. 概述

OpenClaw 运行时持续产生配置变更（cron 状态、agent 工作空间、技能安装、config 热更新等），需要一套**双向同步机制**：

- **下行部署**：GitHub → 服务器（新 hooks/skills/config → 安装到运行目录）
- **上行备份**：服务器 → GitHub（运行时变更 → 快照 → 推送回 GitHub 备份）

---

## 2. 三层目录架构

```
┌─────────────────────────────────────────────────┐
│  A 层 · GitHub 仓库（源码 + 备份）              │
│  XX-Trader/openclaw-hardflow-backup-20260302     │
│                                                  │
│  openclaw.json          overlay 配置模板          │
│  hooks/                 HardFlow hooks 源码       │
│  skills/                技能定义源码              │
│  agents/                Agent 指令定义            │
│  cron/jobs.json         Cron 任务蓝图             │
│  scripts/               ops 脚本 + 安装器         │
│  setup.py               部署入口                  │
└────────────┬──────────────────▲───────────────────┘
        git pull           git push
             ↓                  │
┌────────────────────────────────────────────────────┐
│  B 层 · 服务器 Git Clone（中间层）                  │
│  /root/openclaw-hardflow-backup-20260302/           │
│                                                     │
│  用途：                                              │
│  ① 部署入口：python setup.py → 安装到 C 层          │
│  ② openclaw.json 中 SOURCE_DIR 热加载源             │
│  ③ ops_git_sync_push 的 push 工作目录               │
│                                                     │
│  ⚠️ 当前状态：目录不存在，需修复（见§5 Phase 1）    │
└────────────┬──────────────────▲───────────────────────┘
      setup.py 安装         变更同步
             ↓                  │
┌────────────────────────────────────────────────────────┐
│  C 层 · OpenClaw 运行目录（活的）                       │
│  /root/.openclaw/                                       │
│                                                         │
│  openclaw.json      当前生效的主配置                     │
│  hooks/             已安装的 hooks                       │
│  skills/            已安装的 skills                      │
│  agents/            Agent 工作空间（运行时生成）         │
│  cron/jobs.json     当前生效的定时任务（运行时变更）     │
│  .git/              本地 git（小时级快照，无 remote）    │
│  workspace*/        各 agent 工作空间                    │
│                                                         │
│  🔴 运行时持续变更的文件：                              │
│  cron state · agent workspace · config 热更新            │
│  delivery-queue · completions · canvas · session memory  │
└────────────────────────────────────────────────────────┘
```

---

## 3. 四层同步循环与定时任务映射

```
   你在 Windows 开发              服务器运行时产生变更
   push 到 GitHub                        │
        │                                │
        ▼                                ▼
  ┌──────────┐    ③ 每1小时      ┌──────────────┐
  │ A 层     │    本地快照       │ C 层         │
  │ GitHub   │◀──── ④ ─────────│ .openclaw/   │
  │          │    每6小时 push   │  .git/       │
  │          │──── ① ─────────▶│              │
  └──────────┘    每日 pull     └──────────────┘
       ↕              ↕               ↕
  ┌──────────┐   ┌──────────┐   ┌──────────┐
  │ Windows  │   │ B 层     │   │ 审核层   │
  │ 本地clone│   │ 服务器   │   │ 白名单   │
  │ git pull │   │ clone    │   │ 密钥扫描 │
  └──────────┘   └──────────┘   └──────────┘
```

### 3.1 ① 下行部署：GitHub → 服务器安装

| Cron 任务 | 周期 | Agent | 动作 |
|-----------|------|-------|------|
| `auto_update_daily` | 每日 03:00 | ops-agent | `git pull` B 层 → `setup.py` 安装到 C 层 → 失败通知 |

### 3.2 ② 变更检测与审核

| Cron 任务 | 周期 | Agent | 动作 |
|-----------|------|-------|------|
| `config_diff_review` | 每 6 小时 | optimization-agent | 监控 C 层本地 git 变更 → 触发审核 |

### 3.3 ③ 本地快照

| Cron 任务 | 周期 | Agent | 动作 |
|-----------|------|-------|------|
| **待新建** | 每 1 小时 | optimization-agent | C 层 `git add + commit`（仅本地，不 push） |

### 3.4 ④ 上行备份：运行时变更 → GitHub

| Cron 任务 | 周期 | Agent | 动作 |
|-----------|------|-------|------|
| `ops_git_sync_push` | 每 6 小时 | optimization-agent | 读取 C 层增量变更 → 白名单过滤 → 敏感信息扫描 → 整理同步到 B 层 → push 到 GitHub |

### 3.5 ⑤ Windows 本地同步

| 方式 | 周期 | 动作 |
|------|------|------|
| 手动 `git pull` | 按需 | `H:\GitHub\openclaw-hardflow-backup-20260302\` 拉取最新 |

---

## 4. 涉及的脚本文件清单

| 文件 | 位置 | 作用 |
|------|------|------|
| [setup.py](file:///H:/GitHub/openclaw-hardflow-backup-20260302/setup.py) | 项目根目录 | 部署入口，调用 workflow_setup.py |
| [git_sync_push_runner.py](file:///H:/GitHub/openclaw-hardflow-backup-20260302/scripts/openclaw-ops/git_sync_push_runner.py) | `scripts/openclaw-ops/` | 审核 + push 执行器（652 行） |
| [install_git_sync_job.py](file:///H:/GitHub/openclaw-hardflow-backup-20260302/scripts/openclaw-ops/install_git_sync_job.py) | `scripts/openclaw-ops/` | 注册 cron 任务安装器 |
| [jobs.json](file:///H:/GitHub/openclaw-hardflow-backup-20260302/cron/jobs.json) | `cron/` | Cron 任务蓝图（22 个） |
| [jobs_agent_mapping.md](file:///H:/GitHub/openclaw-hardflow-backup-20260302/cron/jobs_agent_mapping.md) | `cron/` | Agent 与任务映射表 |

---

## 5. 当前状态与实施计划

### ✅ 已就绪

- GitHub 仓库、C 层运行目录、C 层本地 git
- `ops_git_sync_push` / `config_diff_review` / `auto_update_daily` 脚本和 cron 均已注册
- Windows 本地 clone

### ❌ 缺失项（3 个 Gap）

| 编号 | 缺失 | 影响 | 修复方案 | Phase |
|------|------|------|----------|-------|
| G1 | B 层 Clone 不存在 | `auto_update_daily` 无法 pull；SOURCE_DIR 指空 | `git clone` 到 `/root/openclaw-hardflow-backup-20260302/` | Phase 1 |
| G2 | C 层 git 无 remote | `ops_git_sync_push` 无法 push 到 GitHub | 给 C 层 git 添加 remote（或通过 B 层中转） | Phase 2 |
| G3 | 缺每小时本地快照 | 变更无法按小时粒度追踪 | 新建 cron 任务 | Phase 3 |

### 实施步骤

**Phase 1 — 修复 B 层 Clone（G1）**
1. 在 nofx 服务器 `git clone` 创建 B 层
2. 验证 `HOOKS_SOURCE_DIR` / `SKILLS_SOURCE_DIR` 可达
3. 验证 `auto_update_daily` 能正常 pull + install

**Phase 2 — 配置 C 层同步通道（G2）**
1. 确认同步策略（C 层直推 GitHub 还是 B 层中转）
2. 配置 `.gitignore` 排除运行时临时文件
3. 验证 `ops_git_sync_push` 端到端可用

**Phase 3 — 新建每小时快照（G3）**
1. 编写 `local_snapshot_runner.py`
2. 注册 cron 任务（每小时执行）
3. 配置排除列表

**Phase 4 — 端到端验证**
1. Windows 修改 hook → push → 服务器自动 pull + install
2. 服务器修改 config → 等快照 → 推送到 GitHub → Windows pull

---

## 6. 待用户裁决

> [!IMPORTANT]

1. **同步方向策略**：C 层变更直接 push 到 GitHub，还是通过 B 层 clone 中转？
2. **B 层路径确认**：`/root/openclaw-hardflow-backup-20260302/`？
3. **快照排除列表**：`logs/`、`delivery-queue/`、`completions/`、`canvas/`、`workspace*/` 临时文件、`telegram/` 是否排除？

---

## 7. 相关文档索引

| 文档 | 路径 | 内容 |
|------|------|------|
| 本文（配置同步架构） | `docs/design/openclaw-config-sync-architecture.md` | 三层目录架构、四层同步循环、实施计划 |
| 执行路线图 | `docs/execution-roadmap.md` | 六阶段执行计划（本文属阶段四） |
| Cron 任务映射表 | `cron/jobs_agent_mapping.md` | 22 个定时任务与 Agent 映射 |
| 工作流优化审计 | `docs/2026-03-25-工作流优化审计与路线图.md` | 工作流优化审计报告 |
| Telegram 输出规范 | `docs/telegram-output-format-spec.md` | 多列表格输出格式标准 |
| 基础设施规范 | `docs/plans/2026-03-22-openclaw-infrastructure-foundation-spec.md` | OpenClaw 基础设施规范 |
