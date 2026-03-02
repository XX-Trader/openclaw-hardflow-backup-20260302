# HardFlow 全自动落地手册（服务器版）

更新时间：2026-03-01 10:30

## 1. 适用范围

本手册用于把 HardFlow 自动化链路部署到任意 OpenClaw 服务器：

1. hooks 自动提醒与经验进化
2. hardflow 脚本执行链路
3. `hardflow.env` 自动化命令配置
4. 评分门禁与改进回流

## 2. 每台服务器必须提供的信息

最少必须有：

1. `SERVER_ALIAS`（ssh_config 别名）
2. `PROJECT_ROOT`（项目根，必须有 `scripts/hardflow/hardflow-run.sh`）
3. `DEPLOY_CMD`（可执行的一行命令）

建议补充：

1. `GIT_PUSH_CMD`
2. `SCORE_MAX_RETRIES`（建议 1~3）
3. 该项目是否允许自动 deploy / 自动 git push

## 3. 服务器目录标准

1. hooks：`~/.claude/hooks/`
2. 脚本：`~/.openclaw/workspace/scripts/hardflow/`
3. 环境：`~/.openclaw/hardflow/hardflow.env`

## 4. hardflow.env 必配项

```bash
DEPLOY_CMD='...'
GIT_PUSH_CMD='...'
SCORE_MAX_RETRIES='1'

SCORE_REQUIREMENTS_CMD='bash <PROJECT_ROOT>/scripts/hardflow/score-gate.sh requirements "$SCORECARD_FILE"'
SCORE_SOLUTION_CMD='bash <PROJECT_ROOT>/scripts/hardflow/score-gate.sh solution "$SCORECARD_FILE"'
SCORE_FRONTEND_CMD='bash <PROJECT_ROOT>/scripts/hardflow/score-gate.sh frontend "$SCORECARD_FILE"'
SCORE_BACKEND_CMD='bash <PROJECT_ROOT>/scripts/hardflow/score-gate.sh backend "$SCORECARD_FILE"'
SCORE_SECURITY_CMD='bash <PROJECT_ROOT>/scripts/hardflow/score-gate.sh security "$SCORECARD_FILE"'
SCORE_RELEASE_CMD='bash <PROJECT_ROOT>/scripts/hardflow/score-gate.sh release "$SCORECARD_FILE"'
SCORE_FINAL_CMD='bash <PROJECT_ROOT>/scripts/hardflow/score-gate.sh final "$SCORECARD_FILE"'

IMPROVE_REQUIREMENTS_CMD='bash <PROJECT_ROOT>/scripts/hardflow/improve-gate.sh requirements'
IMPROVE_SOLUTION_CMD='bash <PROJECT_ROOT>/scripts/hardflow/improve-gate.sh solution'
IMPROVE_FRONTEND_CMD='bash <PROJECT_ROOT>/scripts/hardflow/improve-gate.sh frontend'
IMPROVE_BACKEND_CMD='bash <PROJECT_ROOT>/scripts/hardflow/improve-gate.sh backend'
IMPROVE_SECURITY_CMD='bash <PROJECT_ROOT>/scripts/hardflow/improve-gate.sh security'
IMPROVE_RELEASE_CMD='bash <PROJECT_ROOT>/scripts/hardflow/improve-gate.sh release'
IMPROVE_FINAL_CMD='bash <PROJECT_ROOT>/scripts/hardflow/improve-gate.sh final'
```

注意：`SCORE_*_CMD` 必须包含 `"$SCORECARD_FILE"`。

## 5. hooks 开关配置

```bash
openclaw config set --json hooks.internal.enabled true
openclaw config set hooks.internal.load.extraDirs[0] ~/.claude/hooks

openclaw config set --json hooks.internal.entries.hardflow-command-guard.enabled true
openclaw config set --json hooks.internal.entries.hardflow-audit.enabled true
openclaw config set --json hooks.internal.entries.hardflow-stop-gate-reminder.enabled true
openclaw config set --json hooks.internal.entries.hardflow-experience-capture.enabled true
openclaw config set --json hooks.internal.entries.hardflow-experience-recall.enabled true
openclaw config set --json hooks.internal.entries.hardflow-experience-evolve.enabled true
```

## 6. 验收命令（每台）

```bash
# hooks
find ~/.claude/hooks -maxdepth 1 -type d -name 'hardflow-*' | wc -l
openclaw hooks check

# hardflow env + scripts
test -f ~/.openclaw/hardflow/hardflow.env && echo env-ok
test -f ~/.openclaw/workspace/scripts/hardflow/hardflow-run.sh && echo runner-ok
test -f ~/.openclaw/workspace/scripts/hardflow/score-gate.sh && echo score-ok
test -f ~/.openclaw/workspace/scripts/hardflow/improve-gate.sh && echo improve-ok

# 最小闭环
cd <PROJECT_ROOT>
bash scripts/hardflow/hardflow-run.sh classify --task "env verify"
bash scripts/hardflow/hardflow-run.sh score-gate --gate requirements --max-retries 1
bash scripts/hardflow/hardflow-run.sh score-report --gate requirements --format text
```

## 7. 给 bot 的标准提示词（可直接发）

```text
为当前服务器配置 ~/.openclaw/hardflow/hardflow.env：
1) 自动识别项目根目录（包含 scripts/hardflow/hardflow-run.sh）。
2) 自动填写 GIT_PUSH_CMD、SCORE_*_CMD、IMPROVE_*_CMD（基于当前项目路径）。
3) 自动尝试识别 DEPLOY_CMD（deploy-prod.sh / deploy.sh / make deploy / docker compose）。
4) 若无法确认 DEPLOY_CMD，只问我 1 个问题并等待回答。
5) chmod 600 ~/.openclaw/hardflow/hardflow.env
6) 运行验证：
   - bash scripts/hardflow/hardflow-run.sh classify --task "env verify"
   - bash scripts/hardflow/hardflow-run.sh score-gate --gate requirements --max-retries 1
   - bash scripts/hardflow/hardflow-run.sh score-report --gate requirements --format text
7) 输出“变量已配置清单（仅显示 <set>）+ 验证结果”。
```

## 8. 本地长期备份建议

1. hooks：`C:\Users\superma\.claude\hooks`
2. 技能归档：`C:\Users\superma\.claude\skills\openclaw-hardflow-automation`
3. setup 手册：`C:\Users\superma\.claude\skills\openclaw-server-setup`
