# OpenClaw 功能文档索引

> 最后更新：2026-03-29
>
> **规则**：功能按层级建文件夹，每个文件夹内 `README.md` 为索引。本文件只列目录结构和引用位置。

---

## 功能目录树

```
docs/
├── 自动进化/                              ← 自动进化体系
│   ├── README.md                          索引：子功能清单
│   └── 配置自动进化/                      ← 双向同步：GitHub ↔ 服务器
│       ├── README.md                      索引：定时任务、脚本清单
│       ├── architecture.md                架构设计（三层目录+四层循环）
│       └── implementation-plan.md         实施计划（模块划分+代码位置+Phase 1-4）
│
├── 部署与运维/                            ← 待后续迁入
├── 治理与审核/                            ← 待后续迁入
├── 协议与规范/                            ← 待后续迁入
└── execution-roadmap.md                   六阶段执行总纲
```

## 已整理的功能

| 功能 | 入口 | 状态 |
|------|------|------|
| [自动进化体系](自动进化/README.md) | `docs/自动进化/` | 🔧 整理中 |
| └─ [配置自动进化](自动进化/配置自动进化/README.md) | `docs/自动进化/配置自动进化/` | 🔧 实施中 |

## 待迁入整理的文档

> 以下文档待后续按功能归类到对应文件夹。

### 部署与运维（待建 `docs/部署与运维/`）

| 文档 | 当前位置 |
|------|----------|
| Linux 服务器部署 | `docs/2026-03-19-openclaw-linux-服务器部署说明.md` |
| Windows 本机部署 | `docs/2026-03-19-openclaw-windows-本机部署说明.md` |
| 安装与工作流部署 | `docs/2026-03-19-openclaw-安装与工作流部署说明.md` |
| Gateway 守护 | `docs/2026-03-11-openclaw-gateway-service-supervisor-guard.md` |
| 多项目服务器模板 | `docs/2026-03-17-multi-project-server-template.md` |
| Rollout 进度 | `docs/2026-03-17-openclaw-rollout-status.md` |

### 治理与审核（待建 `docs/治理与审核/`）

| 文档 | 当前位置 |
|------|----------|
| Cron 任务治理 | `docs/2026-03-20-openclaw-5台服务器-job现状与冗余治理说明.md` |
| 工作流优化审计 | `docs/2026-03-25-工作流优化审计与路线图.md` |
| 工作流升级方案 | `docs/2026-03-20-openclaw-workflow-主升级方案.md` |

### 协议与规范（待建 `docs/协议与规范/`）

| 文档 | 当前位置 |
|------|----------|
| Trace ID 协议 | `docs/trace_id_protocol.md` |
| 任务派发协议 | `docs/task_dispatch_protocol.md` |
| 错误驱动进化 | `docs/error_driven_evolution.md` |
| Telegram 输出规范 | `docs/telegram-output-format-spec.md` |

---

## 文档编写规范

1. **层级结构**：功能大类 → 子功能 → 各自文件夹，目录层级与需求层级一致
2. **文件夹索引**：每个文件夹内 `README.md` 只写概述、文档清单、涉及的任务/脚本
3. **具体内容**：架构设计 → `architecture.md`、实施计划 → `implementation-plan.md`
4. **本文件**：只做目录汇总 + 引用位置，不写具体逻辑
5. **新增功能**：先建文件夹和 README.md → 写需求和实施计划 → 回来更新本索引
