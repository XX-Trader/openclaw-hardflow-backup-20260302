#!/usr/bin/env python3
"""
批量为技能添加 triggers
"""
import os
import glob

skills_dir = os.path.expanduser("~/.claude/skills")

# 定义技能和触发关键词（完整版本）
skills_config = {
    # 文档处理
    "docx": {
        "file": "docx/SKILL.md",
        "keywords": ["Word文档", "word", "docx", "word文档", "办公文档", "创建文档", "编辑文档"],
        "display": "Word 文档处理"
    },
    "pdf": {
        "file": "pdf/SKILL.md",
        "keywords": ["PDF文档", "pdf", "pdf处理", "提取pdf", "合并pdf", "处理pdf", "创建pdf"],
        "display": "PDF 文档处理"
    },
    "xlsx": {
        "file": "xlsx/SKILL.md",
        "keywords": ["Excel", "excel", "xlsx", "表格", "电子表格", "spreadsheet", "处理表格"],
        "display": "Excel 表格处理"
    },
    "pptx": {
        "file": "pptx/SKILL.md",
        "keywords": ["PowerPoint", "pptx", "ppt", "演示文稿", "幻灯片", "制作ppt", "创建演示"],
        "display": "PowerPoint 演示文稿"
    },

    # 设计
    "frontend-design": {
        "file": "frontend-design/SKILL.md",
        "keywords": ["前端设计", "web设计", "网页设计", "界面设计", "ui设计"],
        "display": "前端界面设计"
    },
    "algorithmic-art": {
        "file": "algorithmic-art/SKILL.md",
        "keywords": ["算法艺术", "生成艺术", "艺术创作", "p5.js", "创意编程"],
        "display": "算法艺术创作"
    },
    "canvas-design": {
        "file": "canvas-design/SKILL.md",
        "keywords": ["canvas设计", "视觉设计", "海报设计", "平面设计", "创作设计"],
        "display": "Canvas 视觉设计"
    },

    # 开发工具
    "mcp-builder": {
        "file": "mcp-builder/SKILL.md",
        "keywords": ["MCP服务器", "创建MCP", "MCP开发", "Model Context Protocol", "MCP"],
        "display": "MCP 服务器构建"
    },
    "skill-creator": {
        "file": "skill-creator/SKILL.md",
        "keywords": ["创建技能", "技能开发", "自定义技能", "写技能", "制作技能"],
        "display": "技能创建工具"
    },
    "github-actions-runner": {
        "file": "github-actions-runner/SKILL.md",
        "keywords": ["GitHub Actions", "CI/CD", "自动化部署", "GitHub Actions配置", "workflows"],
        "display": "GitHub Actions 配置"
    },

    # 测试
    "webapp-testing": {
        "file": "webapp-testing/SKILL.md",
        "keywords": ["web测试", "应用测试", "playwright测试", "自动化测试", "浏览器测试"],
        "display": "Web 应用测试"
    },

    # 文档工具
    "changelog-generator": {
        "file": "changelog-generator/SKILL.md",
        "keywords": ["更新日志", "changelog", "版本日志", "更新说明", "生成changelog", "版本更新"],
        "display": "更新日志生成"
    },
    "doc-coauthoring": {
        "file": "doc-coauthoring/SKILL.md",
        "keywords": ["协作文档", "合作写作", "文档协作", "共同编辑", "协作编辑"],
        "display": "协作文档写作"
    },
    "product-requirements": {
        "file": "product-requirements/SKILL.md",
        "keywords": ["PRD", "需求文档", "产品需求", "产品经理", "写需求", "产品规划"],
        "display": "产品需求文档"
    },

    # 其他工具
    "file-organizer": {
        "file": "file-organizer/SKILL.md",
        "keywords": ["文件整理", "文件分类", "整理文件", "文件管理", "文件组织"],
        "display": "文件整理工具"
    },
    "image-enhancer": {
        "file": "image-enhancer/SKILL.md",
        "keywords": ["图片增强", "图像优化", "处理图片", "提高画质", "图像处理"],
        "display": "图片增强工具"
    },
    "video-downloader": {
        "file": "video-downloader/SKILL.md",
        "keywords": ["下载视频", "视频下载", "保存视频", "视频保存", "下载器"],
        "display": "视频下载工具"
    },
    "lead-research-assistant": {
        "file": "lead-research-assistant/SKILL.md",
        "keywords": ["潜在客户", "客户研究", "线索研究", "销售线索", "客户分析"],
        "display": "销售线索研究"
    },
    "meeting-insights-analyzer": {
        "file": "meeting-insights-analyzer/SKILL.md",
        "keywords": ["会议分析", "会议纪要", "会议洞察", "分析会议", "会议记录"],
        "display": "会议洞察分析"
    },
    "competitive-ads-extractor": {
        "file": "competitive-ads-extractor/SKILL.md",
        "keywords": ["广告分析", "竞品广告", "广告提取", "竞争对手", "广告研究"],
        "display": "竞争广告提取"
    },
}

def add_triggers_to_skill(filepath, keywords, display_name):
    """为技能添加 triggers"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查是否已有 triggers
        if 'triggers:' in content:
            return f"✅ {display_name} - 已有 triggers，跳过"

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
            # 找到第二个 ---
            parts = content.split('---', 2)
            if len(parts) >= 2:
                # 在第一个 --- 后插入
                new_content = parts[0] + '---\n' + triggers_config + '---' + parts[1]

                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)

                return f"✅ {display_name} - 已添加 triggers"

        return f"⚠️  {display_name} - 格式问题，跳过"

    except Exception as e:
        return f"❌ {display_name} - 错误: {str(e)}"

def main():
    print("=== 批量添加 Triggers ===\n")

    updated = 0
    skipped = 0
    errors = 0

    for skill_name, config in skills_config.items():
        filepath = os.path.join(skills_dir, config['file'])

        if not os.path.exists(filepath):
            print(f"⚠️  {config['display_name']} - 文件不存在: {config['file']}")
            errors += 1
            continue

        result = add_triggers_to_skill(filepath, config['keywords'], config['display_name'])
        print(result)

        if "✅" in result:
            updated += 1
        elif "已有 triggers" in result:
            skipped += 1
        else:
            errors += 1

    print(f"\n=== 完成 ===")
    print(f"已更新: {updated}")
    print(f"已跳过: {skipped}")
    print(f"错误: {errors}")
    print(f"总计: {updated + skipped + errors}")

if __name__ == "__main__":
    main()
