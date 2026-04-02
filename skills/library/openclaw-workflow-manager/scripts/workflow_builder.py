#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
workflow_builder.py — 自然语言 → 工作流模板生成器

将自然语言的流程描述转换为符合 .agents/workflows/*.md 格式的标准化工作流文件。

功能：
- 解析自然语言步骤描述，提取操作动词、目标、参数
- 生成 YAML frontmatter + markdown 步骤格式
- 自动识别 SSH/SCP/Git/npm/python 等命令类型并标注
- 支持 turbo/turbo-all 安全标记
- 支持从现有工作流模板学习格式

用法:
    python workflow_builder.py --help
    python workflow_builder.py --input "部署脚本到服务器" --steps "1.SSH连接 2.上传文件 3.重启服务" --output workflow.md
    python workflow_builder.py --interactive
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def configure_process_utf8_stdio():
    """确保 stdout/stderr 使用 UTF-8 编码。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ──────────────────────────────────────────────
# 步骤解析与分类
# ──────────────────────────────────────────────

STEP_PATTERNS = {
    "ssh_command": {
        "patterns": [
            re.compile(r"(?:SSH|连接|登录|远程)\s*(?:到|服务器|server)", re.IGNORECASE),
            re.compile(r"ssh\s+", re.IGNORECASE),
        ],
        "template": 'ssh -F F:/ssh_keys/ssh_config -o ConnectTimeout=10 {target} "{command}"',
        "safe": False,
    },
    "scp_transfer": {
        "patterns": [
            re.compile(r"(?:SCP|上传|传输|同步|拷贝)\s*(?:文件|脚本|配置)", re.IGNORECASE),
            re.compile(r"scp\s+", re.IGNORECASE),
        ],
        "template": 'scp -F F:/ssh_keys/ssh_config -o ConnectTimeout=10 "{local}" {target}:{remote}',
        "safe": False,
    },
    "git_operation": {
        "patterns": [
            re.compile(r"(?:git|提交|推送|拉取|commit|push|pull)", re.IGNORECASE),
        ],
        "template": "git {action}",
        "safe": False,
    },
    "npm_command": {
        "patterns": [
            re.compile(r"(?:npm|yarn|pnpm)\s+(?:install|run|build|start)", re.IGNORECASE),
        ],
        "template": "npm {action}",
        "safe": True,
    },
    "python_script": {
        "patterns": [
            re.compile(r"(?:python|python3|执行脚本|运行脚本)\s+", re.IGNORECASE),
            re.compile(r"\.py\b", re.IGNORECASE),
        ],
        "template": "python3 {script}",
        "safe": True,
    },
    "verification": {
        "patterns": [
            re.compile(r"(?:验证|检查|确认|测试|查看|检测)", re.IGNORECASE),
            re.compile(r"(?:verify|check|test|validate)", re.IGNORECASE),
        ],
        "template": "# 验证: {description}",
        "safe": True,
    },
    "config_change": {
        "patterns": [
            re.compile(r"(?:修改|更新|配置|添加|删除)\s*(?:配置|config|json|yaml)", re.IGNORECASE),
        ],
        "template": "# 配置变更: {description}",
        "safe": False,
    },
    "restart_service": {
        "patterns": [
            re.compile(r"(?:重启|启动|停止|reload|restart|start|stop|pm2)", re.IGNORECASE),
        ],
        "template": "# 服务操作: {description}",
        "safe": False,
    },
}


def classify_step(step_text):
    """
    将步骤文本分类为操作类型。

    Args:
        step_text: 步骤描述文本。

    Returns:
        tuple[str, dict]: (分类名, 分类配置)。
    """
    for category_name, category_config in STEP_PATTERNS.items():
        for pattern in category_config["patterns"]:
            if pattern.search(step_text):
                return category_name, category_config
    return "general", {"template": "# {description}", "safe": True}


def parse_steps_from_text(text):
    """
    从自然语言文本中提取步骤列表。

    Args:
        text: 包含步骤描述的文本。

    Returns:
        list[dict]: 解析后的步骤列表。
    """
    steps = []

    # 尝试匹配编号列表 (1. xxx 2. xxx)，支持单行和多行
    numbered_steps = re.findall(r"(\d+)[.、)\]]\s*(.+?)(?=\s*\d+[.、)\]]|$)", text)

    if numbered_steps:
        for number, content in numbered_steps:
            content = content.strip()
            category, config = classify_step(content)
            steps.append({
                "number": int(number),
                "description": content,
                "category": category,
                "safe": config.get("safe", True),
            })
    else:
        # 按换行或分号拆分
        raw_steps = re.split(r"[;\n]+", text)
        for idx, raw_step in enumerate(raw_steps, start=1):
            raw_step = raw_step.strip()
            if not raw_step:
                continue
            category, config = classify_step(raw_step)
            steps.append({
                "number": idx,
                "description": raw_step,
                "category": category,
                "safe": config.get("safe", True),
            })

    return steps


# ──────────────────────────────────────────────
# 工作流生成
# ──────────────────────────────────────────────

def generate_workflow(title, description, steps, turbo_all=False, preconditions=None, notes=None):
    """
    生成标准工作流 Markdown 文件内容。

    Args:
        title: 工作流标题。
        description: 工作流描述。
        steps: 步骤列表（来自 parse_steps_from_text）。
        turbo_all: 是否启用 turbo-all。
        preconditions: 前置条件列表。
        notes: 注意事项列表。

    Returns:
        str: 工作流 Markdown 内容。
    """
    lines = [
        "---",
        f"description: {description}",
        "---",
        "",
        f"# {title}",
        "",
    ]

    if turbo_all:
        lines.append("// turbo-all")
        lines.append("")

    if preconditions:
        lines.append("## 前置条件")
        for pc in preconditions:
            lines.append(f"- {pc}")
        lines.append("")

    lines.append("## 流程")
    lines.append("")

    for step in steps:
        lines.append(f"### {step['number']}. {step['description']}")

        # 根据分类添加命令模板提示
        if step["category"] == "ssh_command":
            lines.append("```powershell")
            lines.append('ssh -F F:/ssh_keys/ssh_config -o ConnectTimeout=10 <服务器别名> "<远程命令>"')
            lines.append("```")
        elif step["category"] == "scp_transfer":
            lines.append("```powershell")
            lines.append('scp -F F:/ssh_keys/ssh_config -o ConnectTimeout=10 "<本地路径>" <别名>:<远程路径>')
            lines.append("```")
        elif step["category"] == "git_operation":
            lines.append("```powershell")
            lines.append("git add -A")
            lines.append('git commit -m "<提交信息>"')
            lines.append("git push origin main")
            lines.append("```")
        elif step["category"] == "python_script":
            lines.append("```powershell")
            lines.append("python3 <脚本路径> <参数>")
            lines.append("```")
        elif step["category"] == "verification":
            if not turbo_all and step["safe"]:
                lines.append("// turbo")

        # 安全标记
        if not turbo_all and step["safe"] and step["category"] not in ("verification",):
            lines.append("// turbo")

        lines.append("")

    if notes:
        lines.append("## 注意事项")
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines)


def build_workflow(title, description, steps_text, turbo_all=False,
                   preconditions=None, notes=None, output_path=None):
    """
    构建工作流的完整流程。

    Args:
        title: 工作流标题。
        description: 简短描述。
        steps_text: 步骤描述文本。
        turbo_all: 是否启用全自动。
        preconditions: 前置条件。
        notes: 注意事项。
        output_path: 输出文件路径。

    Returns:
        dict: 构建结果。
    """
    steps = parse_steps_from_text(steps_text)

    if not steps:
        return {"error": "未能从文本中解析出有效步骤"}

    workflow_content = generate_workflow(
        title=title,
        description=description,
        steps=steps,
        turbo_all=turbo_all,
        preconditions=preconditions,
        notes=notes,
    )

    result = {
        "title": title,
        "steps_count": len(steps),
        "categories": list({s["category"] for s in steps}),
        "has_unsafe_steps": any(not s["safe"] for s in steps),
        "content": workflow_content,
    }

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(workflow_content, encoding="utf-8")
        result["output_path"] = str(out)
        print(f"✅ 工作流已生成: {out}")
    else:
        print(workflow_content)

    return result


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

def build_cli_parser():
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="自然语言 → 工作流模板生成器",
    )
    parser.add_argument("--title", required=True, help="工作流标题")
    parser.add_argument("--description", required=True, help="工作流简短描述")
    parser.add_argument("--steps", required=True, help="步骤描述（用分号或换行分隔）")
    parser.add_argument("--output", default=None, help="输出文件路径")
    parser.add_argument("--turbo-all", action="store_true", help="启用全自动模式")
    parser.add_argument("--precondition", action="append", default=None, help="前置条件（可多次指定）")
    parser.add_argument("--note", action="append", default=None, help="注意事项（可多次指定）")
    return parser


def main():
    """CLI 主入口。"""
    configure_process_utf8_stdio()
    parser = build_cli_parser()
    args = parser.parse_args()

    build_workflow(
        title=args.title,
        description=args.description,
        steps_text=args.steps,
        turbo_all=args.turbo_all,
        preconditions=args.precondition,
        notes=args.note,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
