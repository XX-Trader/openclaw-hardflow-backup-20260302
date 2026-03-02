#!/bin/bash
# 批量为技能添加 triggers 的脚本
# 使用方法: bash ~/.claude/skills/batch-add-triggers.sh

SKILLS_DIR="$HOME/.claude/skills"

# 定义技能和触发关键词
declare -A SKILLS_TRIGGERS

# 文档处理技能
SKILLS_TRIGGERS[docx]="Word文档,word,docx,word文档,办公文档,创建文档,编辑文档"
SKILLS_TRIGGERS[pdf]="PDF文档,pdf,pdf处理,提取pdf,合并pdf,处理pdf,创建pdf"
SKILLS_TRIGGERS[xlsx]="Excel,excel,xlsx,表格,电子表格,spreadsheet,处理表格"
SKILLS_TRIGGERS[pptx]="PowerPoint,pptx,ppt,演示文稿,幻灯片,制作ppt,创建演示"

# 设计技能
SKILLS_TRIGGERS[ui-ux-pro-max]="UI设计,UX设计,界面设计,配色方案,用户体验,前端设计,ui/ux,网页设计"
SKILLS_TRIGGERS[frontend-design]="前端设计,web设计,网页设计,界面设计,ui设计"
SKILLS_TRIGGERS[algorithmic-art]="算法艺术,生成艺术,艺术创作,p5.js,创意编程"
SKILLS_TRIGGERS[canvas-design]="canvas设计,视觉设计,海报设计,平面设计,创作设计"

# 开发工具
SKILLS_TRIGGERS[mcp-builder]="MCP服务器,创建MCP,MCP开发,Model Context Protocol"
SKILLS_TRIGGERS[skill-creator]="创建技能,技能开发,自定义技能,写技能"
SKILLS_TRIGGERS[github-actions-runner]="GitHub Actions,CI/CD,自动化部署,GitHub Actions配置"

# 测试工具
SKILLS_TRIGGERS[webapp-testing]="web测试,应用测试,playwright测试,自动化测试"

# 文档工具
SKILLS_TRIGGERS[changelog-generator]="更新日志,changelog,版本日志,更新说明,生成changelog"
SKILLS_TRIGGERS[doc-coauthoring]="协作文档,合作写作,文档协作,共同编辑"
SKILLS_TRIGGERS[product-requirements]="PRD,需求文档,产品需求,产品经理,写需求"

# 其他工具
SKILLS_TRIGGERS[file-organizer]="文件整理,文件分类,整理文件,文件管理"
SKILLS_TRIGGERS[image-enhancer]="图片增强,图像优化,处理图片,提高画质"
SKILLS_TRIGGERS[video-downloader]="下载视频,视频下载,保存视频"
SKILLS_TRIGGERS[lead-research-assistant]="潜在客户,客户研究,线索研究,销售线索"

echo "=== 批量添加 Triggers ==="
echo ""

for skill in "${!SKILLS_TRIGGERS[@]}"; do
    keywords="${SKILLS_TRIGGERS[$skill]}"

    # 查找技能文件
    if [ -f "$SKILLS_DIR/$skill/SKILL.md" ]; then
        filepath="$SKILLS_DIR/$skill/SKILL.md"
    elif [ -f "$SKILLS_DIR/$skill.md" ]; then
        filepath="$SKILLS_DIR/$skill.md"
    else
        echo "⚠️  跳过 $skill (文件不存在)"
        continue
    fi

    echo "处理: $skill"

    # 检查是否已有 triggers
    if grep -q "triggers:" "$filepath"; then
        echo "  ✅ 已有 triggers，跳过"
        continue
    fi

    # 读取文件前几行
    first_line=$(head -1 "$filepath")

    # 如果不是 frontmatter 格式，添加
    if [[ ! "$first_line" == "---" ]]; then
        echo "  ⚠️  没有 frontmatter，需要手动处理"
        continue
    fi

    # 在 frontmatter 中插入 triggers（在 --- 后面）
    # 创建临时文件
    temp_file=$(mktemp)

    # 读取 frontmatter 部分
    awk -v keywords="$keywords" '
    BEGIN { in_frontmatter = 1; inserted = 0 }
    /^---$/ {
        if (in_frontmatter && !inserted) {
            in_frontmatter = 0
            inserted = 1
            # 添加 triggers
            print "triggers:"
            print "  keywords:"
            n = split(keywords, kws, ",")
            for (i = 1; i <= n; i++) {
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", kws[i])
                print "    - \"" kws[i] "\""
            }
            print "  auto_trigger: true"
            print "  confidence_threshold: 0.7"
            print ""
            print "---"
            next
        }
    }
    { print }
    ' "$filepath" > "$temp_file"

    # 替换原文件
    mv "$temp_file" "$filepath"
    echo "  ✅ 已添加 triggers"
done

echo ""
echo "=== 完成 ==="
echo "已更新技能数量: $(ls -1 "$SKILLS_DIR"/*/SKILL.md 2>/dev/null | wc -l)"
