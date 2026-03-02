# 自动进化经验系统接入（OpenClaw Server Setup 附录）

更新时间：2026-03-01 10:30

## 1. 目标

把经验沉淀流程固化为可运维系统：

1. 会话收口自动 capture
2. Agent 启动自动 recall
3. 结果反馈自动 evolve
4. daily/weekly/monthly 定时维护

## 2. 需要的信息

1. 服务器列表（别名、用户、HOME）
2. OpenClaw 配置路径（`~/.openclaw/config/openclaw.json`）
3. hooks 目录（推荐 `~/.claude/hooks`）
4. memory provider 方案（含 embedding key）
5. 服务重启方式（systemd/tmux）

## 3. 核心开关

```bash
openclaw config set --json hooks.internal.enabled true
openclaw config set hooks.internal.load.extraDirs[0] ~/.claude/hooks

openclaw config set --json hooks.internal.entries.hardflow-experience-capture.enabled true
openclaw config set --json hooks.internal.entries.hardflow-experience-recall.enabled true
openclaw config set --json hooks.internal.entries.hardflow-experience-evolve.enabled true
```

## 4. memory（OpenRouter）

```bash
openclaw config set memorySearch.provider openai
openclaw config set memorySearch.model baai/bge-m3
openclaw config set memorySearch.remote.baseUrl https://openrouter.ai/api/v1
openclaw config set memorySearch.remote.apiKey <sk-or-...>
```

## 5. 验收

```bash
openclaw hooks check
openclaw hooks list | grep hardflow-experience
crontab -l | sed -n '/HARDFLOW EXPERIENCE MAINTENANCE/,+5p'
openclaw memory status --json
```

## 6. 关联文档

1. `HARDFLOW_HOOKS_REUSE.md`
2. `HARDFLOW_SERVER_SETUP_PLAYBOOK.md`
3. `C:\Users\superma\.claude\skills\openclaw-hardflow-automation\README.md`
