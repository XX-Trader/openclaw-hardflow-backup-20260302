---
name: auto-fix
displayName: "受控缺陷修复"
version: "2.0.0"
description: "兼容入口：将缺陷复现、隔离修改、验证、审查和可选发布交给通用项目交付流水线"
description_zh: "受控缺陷修复兼容入口"
updated_at: "2026-08-14"
triggers:
  keywords:
    - "自动修复"
    - "持续修复"
    - "修复并验证"
---

# 受控缺陷修复

本 Skill 保留 `auto-fix` 名称以兼容现有 Agent 能力绑定，实际执行统一委托给 [project-delivery-pipeline](../project-delivery-pipeline/SKILL.md)。仓库只维护一套隔离修改、验证、审查、写回和发布状态机。

## 执行契约

1. 先记录可复现的失败命令、退出码和最小样本。
2. 将缺陷描述作为 `--requirement`，目标仓库通过 `--command-cwd` 注入。
3. 修改动作通过 `--code-command` 注入，并在隔离 Agent 工作区执行。
4. 验证命令通过 `--verification-command` 注入。
5. 至少两条独立审查命令通过重复的 `--code-review-command` 注入。
6. 默认先执行 `--dry-run`；真实发布还要显式提供 `--git-publish-command`。

## 边界

- 不生成带待补业务逻辑的源文件。
- 不猜测数据模型、接口实现、目录结构或技术栈。
- 不默认提交、合并、部署或推送。
- 测试通过、审查通过和远端回读分别记录，不互相替代。

## 示例

```powershell
pwsh -NoProfile -Command 'python .\skills\library\project-delivery-pipeline\scripts\pipeline_runner.py --project-key TARGET_PROJECT --requirement "复现并修复目标缺陷" --command-cwd <project-dir> --code-command <code-command> --verification-command <test-command> --dry-run --emit-json'
```

真实命令、Runtime Home、工作区和发布方式均由目标项目契约提供。
