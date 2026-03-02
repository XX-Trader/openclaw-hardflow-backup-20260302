# HardFlow 经验自动进化（OpenClaw Hooks）

## 1. 目标
这套方案将“经验沉淀 + 召回 + 进化”做成可持续闭环：

1. `capture`：在会话收口/切换时沉淀经验卡片。  
2. `recall`：在 Agent 启动时按相关度召回经验。  
3. `evolve`：在任务结束后按结果更新成功/失败统计。  
4. `maintain`：定时执行打分、去重、聚类、晋升/降级。

## 2. Hook 列表（分开运行）

1. `hardflow-experience-capture`  
触发：`command:stop/new/reset`  
功能：从会话中抽取问题、根因、步骤、验证、回滚，写入经验卡。

2. `hardflow-experience-recall`  
触发：`agent:bootstrap`  
功能：基于 `todo.md/done.md` 召回 Top-K 经验并注入 bootstrap。

3. `hardflow-experience-evolve`  
触发：`command:stop`  
功能：根据 gate / session 结果更新成功率统计。

## 3. 维护主流程（新增）

维护脚本：`scripts/hardflow/experience-maintain.mjs`

执行步骤：
1. 打分：综合完整度、验证质量、成功率、复用次数、新鲜度。  
2. 去重：先按 `fingerprint` 精确去重，再做近似去重。  
3. 聚类：按文本相似度 + 标签重合度聚类。  
4. 晋升/降级：按阈值写入 `draft/candidate/stable/deprecated`。

产物：
1. `.workflow/experience/cards.ndjson`（回写生命周期与分数）  
2. `.workflow/experience/stats.json`（回写维护指标）  
3. `.workflow/experience/maintenance/latest-report.json`  
4. `.workflow/experience/maintenance/clusters.json`  
5. `.workflow/experience/maintenance/SOP_STABLE.md`  
6. `workspace/memory/YYYY-MM-DD.md`（追加维护摘要）

## 4. 定时任务（新增）

运行器：`scripts/hardflow/experience-maintain-cron.sh`

推荐周期：
1. 每日：`daily`（增量维护）  
2. 每周：`weekly`（聚类与质量收敛）  
3. 每月：`monthly`（晋升/降级更严格）

`deploy-evolution-hooks.sh` 会自动安装以下 crontab：
```cron
15 1 * * *  ... experience-maintain-cron.sh daily
30 1 * * 1  ... experience-maintain-cron.sh weekly
45 1 1 * *  ... experience-maintain-cron.sh monthly
```

## 5. 与 OpenClaw memory 的结合

1. 主存储：`.workflow/experience/*`（结构化经验库）。  
2. memory 适配：维护任务会把摘要追加到 `workspace/memory/YYYY-MM-DD.md`。  
3. 索引刷新：运行器会执行 `openclaw memory index --force`（失败不阻断主流程）。  
4. 无 memory 文件时：运行器会自动创建 `workspace/memory` 和 `MEMORY.md`。

## 6. 本地自测

```bash
node --experimental-strip-types scripts/hardflow/hook-selftest.mjs \
  --hooks-dir .claude/hardflow/hooks \
  --workspace .workflow/tmp-hook-selftest
```

预期输出包含：
```text
[hook-selftest] ok
```

## 7. 批量部署到 6 台服务器

```bash
bash scripts/hardflow/deploy-evolution-hooks.sh
```

部署动作包括：
1. 上传 hooks 与维护脚本。  
2. 合并 `openclaw.json`（启用 3 个经验 hooks）。  
3. 补齐 `workspace/memory`、`MEMORY.md`、当日 memory 文件。  
4. 安装日/周/月定时任务。  
5. 立即执行一次 daily 维护。  
6. 校验 hooks 与 memory 状态。

## 8. 回滚

1. 在 `openclaw.json` 关闭 3 个经验 hooks。  
2. 删除 crontab 中 `HARDFLOW EXPERIENCE MAINTENANCE` 区块。  
3. 删除 `~/.openclaw/hardflow-hooks`。  
4. 重启或等待 gateway 热重载生效。
