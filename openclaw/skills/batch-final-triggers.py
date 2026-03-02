#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为最后几个技能添加 triggers
"""
import os

skills_dir = os.path.expanduser("~/.claude/skills")

skills_config = {
    "document-skills/docx": {
        "file": "document-skills/docx/SKILL.md",
        "keywords": ["Word文档", "word", "docx", "word文档", "办公文档"],
    },
    "document-skills/pdf": {
        "file": "document-skills/pdf/SKILL.md",
        "keywords": ["PDF文档", "pdf", "pdf处理", "提取pdf", "处理pdf"],
    },
    "document-skills/pptx": {
        "file": "document-skills/pptx/SKILL.md",
        "keywords": ["PowerPoint", "pptx", "ppt", "演示文稿", "幻灯片"],
    },
    "document-skills/xlsx": {
        "file": "document-skills/xlsx/SKILL.md",
        "keywords": ["Excel", "excel", "xlsx", "表格", "电子表格"],
    },
    "intelligent-router": {
        "file": "intelligent-router/SKILL.md",
        "keywords": ["智能路由", "任务路由", "subagent", "自动路由", "117个subagent"],
    },
    "internal-comms": {
        "file": "internal-comms/SKILL.md",
        "keywords": ["内部沟通", "公司通讯", "内部文档", "状态报告", "公司文档"],
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
    print("批量添加 Triggers - 最后补全")
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
