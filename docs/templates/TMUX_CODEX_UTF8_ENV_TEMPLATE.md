# tmux + codex UTF-8 环境模板

目标：
- 统一 tmux 会话、shell、Python 与 CLI 的 UTF-8 行为；
- 降低中文日志乱码与编码不一致风险。

## 1) 通用环境片段（可放进启动脚本）

```bash
export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"
export LC_CTYPE="${LC_CTYPE:-C.UTF-8}"
export PYTHONUTF8="${PYTHONUTF8:-1}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
export LESSCHARSET="${LESSCHARSET:-utf-8}"
```

## 2) tmux 启动模板

```bash
tmux new-session -d -s "${SESSION_NAME}" \
  "bash -lc 'export LANG=C.UTF-8 LC_ALL=C.UTF-8 LC_CTYPE=C.UTF-8 PYTHONUTF8=1 PYTHONIOENCODING=utf-8; <your_command>'"
```

## 3) codex 命令包装模板

```bash
bash -lc 'export LANG=C.UTF-8 LC_ALL=C.UTF-8 LC_CTYPE=C.UTF-8 PYTHONUTF8=1 PYTHONIOENCODING=utf-8; codex <args>'
```

## 4) 建议策略

- 统一以 UTF-8 保存代码与配置文件。
- 读写文件时显式声明 UTF-8（尤其 Python/Node 脚本）。
- 一旦发现编码异常，先保留原文件并做无损检测，避免覆盖。
