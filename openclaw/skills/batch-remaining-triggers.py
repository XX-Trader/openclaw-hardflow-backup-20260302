#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量为剩余技能添加 triggers
"""
import os

skills_dir = os.path.expanduser("~/.claude/skills")

# 剩余的技能配置
skills_config = {
    "artifacts-builder": {
        "file": "artifacts-builder/SKILL.md",
        "keywords": ["artifacts", "HTML artifacts", "React artifacts", "创建artifact", "构建artifacts"],
    },
    "browser-mcp-guide": {
        "file": "browser-mcp-guide/SKILL.md",
        "keywords": ["浏览器自动化", "浏览器MCP", "Chrome MCP", "browser automation", "Chrome DevTools"],
    },
    "codeagent": {
        "file": "codeagent/SKILL.md",
        "keywords": ["codeagent", "代码代理", "AI代码", "多backend", "Codex", "Claude", "Gemini"],
    },
    "codex": {
        "file": "codex/SKILL.md",
        "keywords": ["Codex CLI", "codex", "代码分析", "代码重构", "自动化代码"],
    },
    "developer-growth-analysis": {
        "file": "developer-growth-analysis/SKILL.md",
        "keywords": ["开发者成长", "技能分析", "成长分析", "开发模式", "coding patterns"],
    },
    "gemini": {
        "file": "gemini/SKILL.md",
        "keywords": ["Gemini", "Google Gemini", "Gemini CLI", "Gemini API", "Google AI"],
    },
    "invoice-organizer": {
        "file": "invoice-organizer/SKILL.md",
        "keywords": ["发票", "票据整理", "财务文件", "invoice", "收据", "财务整理"],
    },
    "logv": {
        "file": "logv/SKILL.md",
        "keywords": ["日志", "日志查看", "日志分析", "log", "log viewer", "去重"],
    },
    "requirements-clarity": {
        "file": "requirements-clarity/skills/SKILL.md",
        "keywords": ["需求澄清", "需求不清晰", "模糊需求", "需求确认", "clarify requirements"],
    },
    "skill-share": {
        "file": "skill-share/SKILL.md",
        "keywords": ["技能分享", "share skill", "Slack技能", "分享到Slack", "协作"],
    },
    "slack-gif-creator": {
        "file": "slack-gif-creator/SKILL.md",
        "keywords": ["GIF", "动图", "GIF制作", "Slack GIF", "动画", "创建GIF"],
    },
    "template-skill": {
        "file": "template-skill/SKILL.md",
        "keywords": ["模板技能", "skill模板", "技能模板", "template"],
    },
    "web-artifacts-builder": {
        "file": "web-artifacts-builder/SKILL.md",
        "keywords": ["web artifacts", "网页artifact", "HTML构建", "web component", "前端artifact"],
    },
}

def add_triggers_to_skill(filepath, keywords):
    """为技能添加 triggers"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查是否已有 triggers
        if 'triggers:' in content:
            return False, "已有 triggers"

        # 生成 triggers 配置
        keywords_str = '\n'.join([f'    - "{kw}"' for kw in keywords])
        triggers_config = f'''triggers:
  keywords:
{keywords_str}
  auto_trigger: true
  confidence_threshold: 0.7

'''

        # 在 frontmatter 中插入
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 2:
                new_content = parts[0] + '---\n' + triggers_config + '---' + parts[1]
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                return True, "已添加"
        return False, "格式问题"

    except Exception as e:
        return False, f"错误: {str(e)}"

def main():
    print("=" * 60)
    print("批量添加 Triggers - 剩余技能补全")
    print("=" * 60)
    print()

    updated = 0
    skipped = 0
    errors = 0

    for skill_name, config in skills_config.items():
        filepath = os.path.join(skills_dir, config['file'])

        if not os.path.exists(filepath):
            print(f"[!] {skill_name} - 文件不存在: {config['file']}")
            errors += 1
            continue

        print(f"处理: {skill_name}...", end=" ")

        success, message = add_triggers_to_skill(filepath, config['keywords'])

        if success:
            print(f"[OK] {message}")
            updated += 1
        elif "已有 triggers" in message:
            print(f"[SKIP] {message}")
            skipped += 1
        else:
            print(f"[FAIL] {message}")
            errors += 1

    print()
    print("=" * 60)
    print(f"更新完成: {updated} 个")
    print(f"跳过: {skipped} 个")
    print(f"错误: {errors} 个")
    print(f"总计: {updated + skipped + errors} 个")
    print("=" * 60)

if __name__ == "__main__":
    main()
