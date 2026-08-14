# 贡献指南

## 开发环境

1. 使用 Python 3.11 或兼容版本、Git 和 PowerShell 7。
2. 安装开发依赖：`python -m pip install -r requirements-dev.txt`。
3. 新需求先更新 `requirements.md`，可见行为变化同步 `CHANGELOG.md`。

## 变更原则

- 保持领域中立；项目目录、命令、Runtime 和外部连接均通过参数、环境变量或项目契约注入。
- 不提交凭证、会话记录、机器专属配置、缓存或运行产物。
- 修改现有唯一 owner，避免创建职责重叠的脚本或 Skill。
- Bug 修复同时补充可复现的回归测试。

## 本地门禁

```powershell
pwsh -NoProfile -Command 'python -m pytest -q -m quick'
pwsh -NoProfile -Command 'python -m pytest -q -m integration'
pwsh -NoProfile -Command 'python .\scripts\openclaw-ops\repository_policy_check.py --tracked-only --emit-json'
pwsh -NoProfile -Command 'git diff --check'
```

`quick` 与 `integration` 覆盖全部测试且互不重叠。提交应保持范围单一，并在说明中记录症状、根因、验证命令和结果。

## 提交与评审

- 提交标题简洁描述结果，正文说明重要边界和回滚方式。
- 评审关注需求符合性、失败路径、跨平台行为、敏感信息和证据完整性。
- 发布前确认本地提交已被目标远端分支包含。
