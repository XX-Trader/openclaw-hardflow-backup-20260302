#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量为技能添加 triggers - 完整版
"""
import os
import glob
import re

skills_dir = os.path.expanduser("~/.claude/skills")

# 完整的技能配置（包含所有剩余技能）
skills_config = {
    # 文档处理（已完成的跳过）
    # docx, pdf, xlsx, pptx, frontend-design, mcp-builder, skill-creator, github-actions-runner, webapp-testing, changelog-generator, ui-ux-pro-max

    # 设计创作
    "algorithmic-art": {
        "file": "algorithmic-art/SKILL.md",
        "keywords": ["算法艺术", "生成艺术", "艺术创作", "p5.js", "创意编程", "生成艺术"],
    },
    "canvas-design": {
        "file": "canvas-design/SKILL.md",
        "keywords": ["canvas设计", "视觉设计", "海报设计", "平面设计", "创作设计", "视觉创作"],
    },
    "brand-guidelines": {
        "file": "brand-guidelines/SKILL.md",
        "keywords": ["品牌规范", "品牌设计", "品牌色彩", "排版规范", "品牌指南"],
    },
    "theme-factory": {
        "file": "theme-factory/SKILL.md",
        "keywords": ["主题工具", "主题样式", "主题工厂", "样式模板", "配色方案"],
    },

    # 开发工具
    "product-requirements": {
        "file": "product-requirements/SKILL.md",
        "keywords": ["PRD", "需求文档", "产品需求", "产品经理", "写需求", "产品规划", "需求分析"],
    },
    "prototype-prompt-generator": {
        "file": "prototype-prompt-generator/SKILL.md",
        "keywords": ["原型提示", "原型生成", "UI原型", "设计原型", "原型设计"],
    },

    # 测试与质量
    "code-review": {
        "file": "code-review/SKILL.md",
        "keywords": ["代码审查", "PR review", "pull request", "代码质量", "审查代码"],
    },

    # 文档工具
    "doc-coauthoring": {
        "file": "doc-coauthoring/SKILL.md",
        "keywords": ["协作文档", "合作写作", "文档协作", "共同编辑", "协作编辑", "协作文档写作"],
    },

    # 内容与媒体
    "social-media-copywriter": {
        "file": "social-media-copywriter/SKILL.md",
        "keywords": ["社交媒体", "文案", "社媒文案", "社交媒体写作", "内容创作"],
    },
    "podcast-transcriber": {
        "file": "podcast-transcriber/SKILL.md",
        "keywords": ["播客", "transcript", "转录", "音频转文字", "播客转录"],
    },
    "video-downloader": {
        "file": "video-downloader/SKILL.md",
        "keywords": ["下载视频", "视频下载", "保存视频", "视频保存", "下载器", "视频抓取"],
    },

    # 工具
    "file-organizer": {
        "file": "file-organizer/SKILL.md",
        "keywords": ["文件整理", "文件分类", "整理文件", "文件管理", "文件组织", "文件归类"],
    },
    "image-enhancer": {
        "file": "image-enhancer/SKILL.md",
        "keywords": ["图片增强", "图像优化", "处理图片", "提高画质", "图像处理", "图片优化"],
    },
    "domain-name-brainstormer": {
        "file": "domain-name-brainstormer/SKILL.md",
        "keywords": ["域名", "域名注册", "域名建议", "域名查询", "域名生成"],
    },
    "raffle-winner-picker": {
        "file": "raffle-winner-picker/SKILL.md",
        "keywords": ["抽奖", "随机抽取", "抽奖工具", "随机选择", "抽取"],
    },

    # 研究
    "lead-research-assistant": {
        "file": "lead-research-assistant/SKILL.md",
        "keywords": ["潜在客户", "客户研究", "线索研究", "销售线索", "客户分析", "客户调研"],
    },
    "meeting-insights-analyzer": {
        "file": "meeting-insights-analyzer/SKILL.md",
        "keywords": ["会议分析", "会议纪要", "会议洞察", "分析会议", "会议记录", "会议总结"],
    },
    "competitive-ads-extractor": {
        "file": "competitive-ads-extractor/SKILL.md",
        "keywords": ["广告分析", "竞品广告", "广告提取", "竞争对手", "广告研究", "竞争分析"],
    },

    # AI/ML
    "content-research-writer": {
        "file": "content-research-writer/SKILL.md",
        "keywords": ["内容研究", "内容写作", "调研写作", "内容营销", "文章写作"],
    },

    # 代理管理
    "agent-manager": {
        "file": "agent-manager/SKILL.md",
        "keywords": ["agent管理", "代理管理", "管理agent", "agent管理器"],
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
    print("批量添加 Triggers - 补全剩余技能")
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
