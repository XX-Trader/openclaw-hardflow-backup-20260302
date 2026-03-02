#!/usr/bin/env python3
"""
修复 SKILL.md 文件的 YAML frontmatter 格式
确保每个文件都有正确的格式:
---
name: skill-name
description: "..."
version: "1.0.0"
triggers:
  keywords:
    - "关键词1"
---
"""

import os
import re
import sys
from pathlib import Path
from collections import OrderedDict

SKILLS_DIR = Path("C:/Users/superma/.claude/skills")

def find_skill_files():
    """查找所有 SKILL.md 文件"""
    return sorted(SKILLS_DIR.glob("*/SKILL.md"))

def parse_yaml_value(value):
    """简单解析 YAML 值"""
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value.lower() == 'true':
        return True
    if value.lower() == 'false':
        return False
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value

def parse_frontmatter(content):
    """解析 frontmatter，返回 (frontmatter_dict, body_content)"""
    # 匹配开头的 YAML 块
    pattern = r'^---\s*\n(.*?)\n---\s*\n?(.*)$'
    match = re.match(pattern, content, re.DOTALL)

    if not match:
        return None, content

    fm_str = match.group(1)
    body = match.group(2)

    # 简单解析 YAML
    fm = OrderedDict()
    lines = fm_str.split('\n')
    current_key = None
    current_subkey = None
    in_list = False
    list_items = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # 顶级键值对
        if not line.startswith(' ') and ':' in line:
            key, _, value = line.partition(':')
            key = key.strip()
            value = value.strip()

            if value == '':
                # 可能是嵌套结构
                current_key = key
                fm[key] = OrderedDict()
                in_list = False
            else:
                fm[key] = parse_yaml_value(value)
                current_key = None

        # 二级键（2空格缩进）
        elif line.startswith('  ') and not line.startswith('    ') and ':' in line:
            stripped = line.strip()
            key, _, value = stripped.partition(':')
            key = key.strip()
            value = value.strip()

            if current_key and isinstance(fm.get(current_key), dict):
                if value == '':
                    current_subkey = key
                    fm[current_key][key] = []
                    in_list = True
                else:
                    fm[current_key][key] = parse_yaml_value(value)

        # 列表项（4空格缩进 + 短横线）
        elif line.startswith('    - '):
            item = stripped[2:].strip()  # 去掉 "- "
            item = parse_yaml_value(item)
            if current_key and current_subkey and isinstance(fm.get(current_key, {}).get(current_subkey), list):
                fm[current_key][current_subkey].append(item)

        i += 1

    return fm, body

def extract_name_from_path(filepath):
    """从文件路径提取技能名称"""
    return filepath.parent.name

def format_yaml_value(value, indent=0):
    """格式化 YAML 值"""
    indent_str = '  ' * indent

    if isinstance(value, dict):
        lines = []
        for k, v in value.items():
            if isinstance(v, list):
                lines.append(f'{indent_str}{k}:')
                for item in v:
                    if isinstance(item, str) and ('"' in item or ':' in item):
                        lines.append(f'{indent_str}  - "{item}"')
                    elif isinstance(item, str):
                        lines.append(f'{indent_str}  - "{item}"')
                    else:
                        lines.append(f'{indent_str}  - {item}')
            elif isinstance(v, dict):
                lines.append(f'{indent_str}{k}:')
                lines.append(format_yaml_value(v, indent + 1))
            elif isinstance(v, bool):
                lines.append(f'{indent_str}{k}: {str(v).lower()}')
            elif isinstance(v, str):
                if ':' in v or '\n' in v or '"' in v:
                    lines.append(f'{indent_str}{k}: "{v}"')
                else:
                    lines.append(f'{indent_str}{k}: "{v}"')
            else:
                lines.append(f'{indent_str}{k}: {v}')
        return '\n'.join(lines)
    else:
        return f'{indent_str}{value}'

def format_frontmatter(fm):
    """格式化 frontmatter 为 YAML 字符串"""
    lines = ['---']

    # 按照特定顺序输出字段
    order = ['name', 'displayName', 'description', 'version', 'author', 'license', 'updated_at', 'triggers', 'tools', 'permissions']

    for key in order:
        if key in fm:
            value = fm[key]
            if key == 'triggers' and isinstance(value, dict):
                lines.append('triggers:')
                if 'keywords' in value:
                    lines.append('  keywords:')
                    for kw in value['keywords']:
                        lines.append(f'    - "{kw}"')
                if 'auto_trigger' in value:
                    lines.append(f'  auto_trigger: {str(value["auto_trigger"]).lower()}')
                if 'confidence_threshold' in value:
                    lines.append(f'  confidence_threshold: {value["confidence_threshold"]}')
            elif key == 'tools' and isinstance(value, dict):
                lines.append('tools:')
                for subkey, subvalue in value.items():
                    lines.append(f'  {subkey}:')
                    for item in subvalue:
                        lines.append(f'    - {item}')
            elif key == 'permissions' and isinstance(value, dict):
                lines.append('permissions:')
                for subkey, subvalue in value.items():
                    lines.append(f'  {subkey}: {subvalue}')
            elif isinstance(value, str):
                lines.append(f'{key}: "{value}"')
            elif isinstance(value, bool):
                lines.append(f'{key}: {str(value).lower()}')
            elif isinstance(value, (int, float)):
                lines.append(f'{key}: {value}')
            elif isinstance(value, list):
                lines.append(f'{key}:')
                for item in value:
                    lines.append(f'  - {item}')
            else:
                lines.append(f'{key}: {value}')

    # 输出不在 order 中的其他字段
    for key, value in fm.items():
        if key not in order:
            if isinstance(value, str):
                lines.append(f'{key}: "{value}"')
            elif isinstance(value, bool):
                lines.append(f'{key}: {str(value).lower()}')
            else:
                lines.append(f'{key}: {value}')

    lines.append('---')
    return '\n'.join(lines)

def fix_frontmatter(filepath):
    """修复单个文件的 frontmatter"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return {
            'filepath': filepath,
            'skill_name': extract_name_from_path(filepath),
            'issues': [f'读取失败: {e}'],
            'existing_fm': None,
            'new_fm': None,
            'body': '',
            'needs_fix': True,
            'error': True
        }

    skill_name = extract_name_from_path(filepath)
    existing_fm, body = parse_frontmatter(content)

    issues = []

    # 检查问题
    if existing_fm is None:
        issues.append("缺少 frontmatter")
    else:
        if 'name' not in existing_fm:
            issues.append("缺少 name 字段")

    # 生成修复后的 frontmatter
    if existing_fm:
        # 合并现有字段
        new_fm = OrderedDict()
        new_fm['name'] = skill_name

        if 'displayName' in existing_fm:
            new_fm['displayName'] = existing_fm['displayName']
        elif 'description' in existing_fm:
            # 如果没有 displayName，用 description 的前50字符作为 displayName
            desc = existing_fm['description']
            if isinstance(desc, str) and len(desc) > 10:
                new_fm['displayName'] = desc[:50] + ('...' if len(desc) > 50 else '')

        if 'description' in existing_fm:
            new_fm['description'] = existing_fm['description']
        else:
            new_fm['description'] = f'{skill_name} 技能'

        if 'version' in existing_fm:
            new_fm['version'] = existing_fm['version']
        else:
            new_fm['version'] = '1.0.0'

        # 复制其他字段
        for key in ['author', 'license', 'updated_at']:
            if key in existing_fm:
                new_fm[key] = existing_fm[key]

        if 'triggers' in existing_fm:
            new_fm['triggers'] = existing_fm['triggers']

        if 'tools' in existing_fm:
            new_fm['tools'] = existing_fm['tools']

        if 'permissions' in existing_fm:
            new_fm['permissions'] = existing_fm['permissions']
    else:
        new_fm = OrderedDict([
            ('name', skill_name),
            ('description', f'{skill_name} 技能'),
            ('version', '1.0.0'),
        ])

    return {
        'filepath': filepath,
        'skill_name': skill_name,
        'issues': issues,
        'existing_fm': existing_fm,
        'new_fm': new_fm,
        'body': body.strip(),
        'needs_fix': len(issues) > 0 or existing_fm is None
    }

def apply_fix(result, dry_run=True):
    """应用修复"""
    if not result['needs_fix']:
        return False

    new_content = format_frontmatter(result['new_fm']) + '\n\n' + result['body']

    if dry_run:
        print(f"\n{'='*60}")
        print(f"文件: {result['filepath']}")
        print(f"技能名: {result['skill_name']}")
        print(f"问题: {result['issues']}")
        print(f"\n新 frontmatter:")
        print(format_frontmatter(result['new_fm']))
        return False
    else:
        with open(result['filepath'], 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True

def main():
    files = find_skill_files()
    print(f"找到 {len(files)} 个 SKILL.md 文件\n")

    results = []
    correct_count = 0
    needs_fix_count = 0

    for filepath in files:
        result = fix_frontmatter(filepath)
        results.append(result)
        if result['needs_fix']:
            needs_fix_count += 1
            print(f"[X] {result['skill_name']}: {result['issues']}")
        else:
            correct_count += 1
            print(f"[OK] {result['skill_name']}: 格式正确")

    # 统计
    print(f"\n{'='*60}")
    print(f"统计: 正确 {correct_count} / 需修复 {needs_fix_count} / 总计 {len(results)}")

    return results

if __name__ == '__main__':
    dry_run = '--apply' not in sys.argv

    if dry_run:
        print("=== 干运行模式（只检查，不修改）===")
        print("使用 --apply 参数来实际修改文件\n")
    else:
        print("=== 应用模式（将修改文件）===\n")

    results = main()

    if not dry_run:
        print("\n正在应用修复...")
        fixed = 0
        for result in results:
            if result.get('error'):
                print(f"  [!] {result['skill_name']}: 跳过（读取错误）")
                continue
            if apply_fix(result, dry_run=False):
                fixed += 1
                print(f"  [+] {result['skill_name']}")
        print(f"\n修复完成: {fixed} 个文件")
