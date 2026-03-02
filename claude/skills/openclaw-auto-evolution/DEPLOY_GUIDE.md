# DEPLOY_GUIDE

## 1. 单机部署步骤

### 1.1 上传 hooks 与工具

```bash
mkdir -p ~/.openclaw/hardflow-hooks/hooks ~/.openclaw/hardflow-hooks/tools ~/.openclaw/logs
# 将本地 hardflow 目录拷贝到 ~/.openclaw/hardflow-hooks/
```

### 1.2 打开 hooks 加载与条目开关

```bash
openclaw config set --json hooks.internal.enabled true
openclaw config set hooks.internal.load.extraDirs[0] ~/.openclaw/hardflow-hooks/hooks

openclaw config set --json hooks.internal.entries.hardflow-experience-capture.enabled true
openclaw config set --json hooks.internal.entries.hardflow-experience-recall.enabled true
openclaw config set --json hooks.internal.entries.hardflow-experience-evolve.enabled true
```

### 1.3 设置定时维护（打分、去重、聚类、晋升/降级）

```bash
( crontab -l 2>/dev/null; \
  echo '# BEGIN HARDFLOW EXPERIENCE MAINTENANCE'; \
  echo '15 1 * * * /usr/bin/env bash $HOME/.openclaw/hardflow-hooks/tools/experience-maintain-cron.sh daily >> $HOME/.openclaw/logs/experience-maintenance.log 2>&1'; \
  echo '30 1 * * 1 /usr/bin/env bash $HOME/.openclaw/hardflow-hooks/tools/experience-maintain-cron.sh weekly >> $HOME/.openclaw/logs/experience-maintenance.log 2>&1'; \
  echo '45 1 1 * * /usr/bin/env bash $HOME/.openclaw/hardflow-hooks/tools/experience-maintain-cron.sh monthly >> $HOME/.openclaw/logs/experience-maintenance.log 2>&1'; \
  echo '# END HARDFLOW EXPERIENCE MAINTENANCE' ) | awk '!seen[$0]++' | crontab -
```

### 1.4 memory provider 配置（OpenRouter）

```bash
openclaw config set memorySearch.provider openai
openclaw config set memorySearch.model baai/bge-m3
openclaw config set memorySearch.remote.baseUrl https://openrouter.ai/api/v1
openclaw config set memorySearch.remote.apiKey <sk-or-...>
```

### 1.5 重启服务（按你的部署方式二选一）

```bash
# systemd
sudo systemctl restart openclaw

# 非 systemd（tmux/手工）
# 停掉旧进程后重新启动 gateway
```

## 2. 六台服务器快速核验命令

```bash
echo -n 'hooks_ready='; openclaw hooks list | head -n 1
echo -n 'capture='; openclaw config get hooks.internal.entries.hardflow-experience-capture.enabled
echo -n 'recall=';  openclaw config get hooks.internal.entries.hardflow-experience-recall.enabled
echo -n 'evolve=';  openclaw config get hooks.internal.entries.hardflow-experience-evolve.enabled
crontab -l | sed -n '/HARDFLOW EXPERIENCE MAINTENANCE/,+5p'
openclaw memory status --json
```

## 3. 回滚

```bash
openclaw config set --json hooks.internal.entries.hardflow-experience-capture.enabled false
openclaw config set --json hooks.internal.entries.hardflow-experience-recall.enabled false
openclaw config set --json hooks.internal.entries.hardflow-experience-evolve.enabled false
# 如需彻底回滚，再移除 extraDirs 对应路径
```
