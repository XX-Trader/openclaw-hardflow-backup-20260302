#!/usr/bin/env python3
"""
提取 agents 目录下的所有 agent 元数据
生成分类索引
"""

import os
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime


def extract_frontmatter(file_path):
    """提取 Markdown 文件的 YAML frontmatter"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 提取 --- 之间的内容
        match = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
        if not match:
            return None

        frontmatter = match.group(1)
        metadata = {}

        # 解析 YAML 格式
        for line in frontmatter.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                metadata[key.strip()] = value.strip()

        return metadata
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None


def main():
    agents_dir = Path("C:/Users/superma/.claude/agents")
    output_dir = Path("C:/Users/superma/.claude/skills/agent-manager/data")

    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)

    # 存储所有 agent 数据
    agents = []
    categories = defaultdict(list)

    # 遍历所有 .md 文件
    for md_file in agents_dir.glob("*.md"):
        metadata = extract_frontmatter(md_file)
        if metadata and 'name' in metadata:
            agent_data = {
                'name': metadata.get('name', ''),
                'description': metadata.get('description', ''),
                'category': metadata.get('category', 'uncategorized'),
                'file': md_file.stem
            }
            agents.append(agent_data)
            categories[agent_data['category']].append(agent_data)

    # 按类别排序
    sorted_categories = sorted(categories.items())

    # 生成索引文档
    index_md = """# Agent 索引

> 自动生成时间: {date}
> Agent 总数: {total}
> 类别数: {categories_count}

---

## 📖 使用说明

### 如何调用 Agent

在对话中直接说明需求，我会自动匹配合适的 agent：

**示例**:
- "帮我审查这段代码" → code-reviewer
- "优化这个Python函数" → python-expert
- "调试这个错误" → debugger

### 手动指定 Agent

你也可以明确指定使用某个 agent：

```
"请使用 python-expert 代理帮我优化代码"
"使用 debugger 代理分析这个错误"
```

---

## 📋 Agent 分类索引

""".format(
        date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        total=len(agents),
        categories_count=len(sorted_categories)
    )

    # 为每个类别生成索引
    for category, agents_list in sorted_categories:
        index_md += f"\n### {category.replace('-', ' ').title()}\n\n"
        index_md += f"| Agent | 描述 |\n"
        index_md += f"|-------|------|\n"

        for agent in sorted(agents_list, key=lambda x: x['name']):
            name = agent['name']
            desc = agent['description'][:80] + '...' if len(agent['description']) > 80 else agent['description']
            index_md += f"| [{name}]({agent['file']}.md) | {desc} |\n"

        index_md += "\n"

    # 添加快速查找表
    index_md += "\n---\n\n## 🔍 快速查找（按字母顺序）\n\n"
    index_md += "| Agent | Category | 描述 |\n"
    index_md += f"|-------|----------|------|\n"

    for agent in sorted(agents, key=lambda x: x['name']):
        name = agent['name']
        category = agent['category']
        desc = agent['description'][:60] + '...' if len(agent['description']) > 60 else agent['description']
        index_md += f"| {name} | {category} | {desc} |\n"

    # 写入索引文件
    index_file = output_dir / "AGENTS_INDEX.md"
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write(index_md)

    # 生成 JSON 数据
    import json
    json_data = {
        'generated_at': datetime.now().isoformat(),
        'total_agents': len(agents),
        'categories': {
            cat: [a['name'] for a in agents_list]
            for cat, agents_list in sorted_categories
        },
        'agents': agents
    }

    json_file = output_dir / "agents.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    print(f"[OK] Index generation complete!")
    print(f"[MD] Markdown: {index_file}")
    print(f"[JSON] Data: {json_file}")
    print(f"[STAT] Total {len(agents)} agents, {len(sorted_categories)} categories")


if __name__ == "__main__":
    main()
