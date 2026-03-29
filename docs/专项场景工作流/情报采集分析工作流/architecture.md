# 情报采集分析工作流 — 架构设计

> 版本：v1.0 | 2026-03-29

## 三通道架构

```mermaid
graph TB
    subgraph 通道一 - 上游社区同步
        A1[OpenClaw 上游 GitHub] -->|git pull --ff-only| B1[auto_update_install_runner.py]
        B1 -->|有更新| C1{setup.py --yes}
        C1 -->|安装成功| D1[.openclaw/ 更新]
        C1 -->|安装失败| E1[Telegram 告警]
    end
    subgraph 通道二 - 网页情报采集
        A2[web_sources_runtime.py 情报源] -->|配置| B2[web_intel_collect_runner.py]
        B2 -->|HTTP/Playwright 爬取| C2{内容变更?}
        C2 -->|有变更| D2[存档 + Telegram 通知]
        C2 -->|无变更| E2[NO_REPLY]
        C2 -->|爬取失败| F2[自动建单修复]
    end
    subgraph 通道三 - 开源项目扫描
        A3[GitHub 高信号仓库列表] -->|API 采集| B3[github_web_evolution_runner.py]
        A4[Skill4Agent 技能库] -->|MCP 查询| B3
        B3 -->|新工具/方法论| C3[创建评估 TODO]
    end
```

## 情报源管理

| 组件 | 路径 | 说明 |
|------|------|------|
| 情报源运行时 | `web_sources_runtime.py` (13KB) | 情报源注册/查询/状态管理 |
| 供应商目录 | `vendor_source_catalog.py` (6KB) | 技术供应商跟踪 |
| 情报评审器 | `web_intel_review_runner.py` (42KB) | 采集结果结构化评审 |

## 故障恢复策略

| 失败类型 | 处理方式 |
|----------|----------|
| HTTP 超时 | 指数退避重试（3次） |
| 网页结构变化 | 记录异常 + 创建修复工单 |
| API 限速 | 延迟队列，24h 后重试 |
| 凭证过期 | Telegram 告警 + TODO |
