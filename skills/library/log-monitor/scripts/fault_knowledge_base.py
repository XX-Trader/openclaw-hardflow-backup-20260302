#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fault_knowledge_base.py — 故障知识库索引与查询引擎

将 docs/ 下的故障文档自动解析为结构化索引，支持：
- 按关键词/症状模糊匹配故障
- 按故障类型分类检索
- 返回诊断步骤和修复方案
- 自动从新故障文档中提取经验

用法:
    python fault_knowledge_base.py --help
    python fault_knowledge_base.py --docs-dir /path/to/docs/ --build-index
    python fault_knowledge_base.py --query "配置文件启动失败"
    python fault_knowledge_base.py --docs-dir /path/to/docs/ --query "cron任务不执行" --top 3
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
# 故障类型定义
# ──────────────────────────────────────────────

FAULT_CATEGORIES = {
    "config_fault": {
        "label": "配置故障",
        "keywords": ["配置", "config", "json", "yaml", "插件", "plugin", "引用缺失", "路径错误",
                     "语法错误", "parse error", "not found", "missing"],
    },
    "cron_fault": {
        "label": "定时任务故障",
        "keywords": ["cron", "定时", "调度", "schedule", "任务不执行", "卡住", "running",
                     "error", "超时", "timeout", "executor"],
    },
    "deploy_fault": {
        "label": "部署故障",
        "keywords": ["部署", "deploy", "发布", "上线", "服务器", "server", "SSH", "SCP",
                     "pm2", "restart", "nginx"],
    },
    "agent_fault": {
        "label": "Agent 故障",
        "keywords": ["agent", "子agent", "会话", "session", "模型", "model", "API",
                     "rate limit", "token", "SOUL", "skill"],
    },
    "data_fault": {
        "label": "数据/存储故障",
        "keywords": ["数据库", "database", "sqlite", "task_center", "磁盘", "disk",
                     "内存", "memory", "OOM", "存储"],
    },
    "evolution_fault": {
        "label": "进化/自我优化故障",
        "keywords": ["进化", "evolution", "自我优化", "治理", "governance", "巡检",
                     "benchmark", "评分", "score", "优化"],
    },
    "network_fault": {
        "label": "网络/API 故障",
        "keywords": ["网络", "network", "API", "HTTP", "429", "timeout", "连接",
                     "connection", "refused", "GitHub", "token"],
    },
}


def classify_fault(text):
    """
    将文本分类到故障类别。

    Args:
        text: 文档内容或查询文本。

    Returns:
        list[tuple[str, int]]: 匹配的类别和命中关键词数，按命中数降序。
    """
    matches = []
    text_lower = text.lower()

    for category_name, category_config in FAULT_CATEGORIES.items():
        hit_count = sum(1 for kw in category_config["keywords"] if kw.lower() in text_lower)
        if hit_count > 0:
            matches.append((category_name, hit_count))

    return sorted(matches, key=lambda x: x[1], reverse=True)


# ──────────────────────────────────────────────
# 文档解析
# ──────────────────────────────────────────────

def parse_fault_document(file_path):
    """
    解析故障文档，提取结构化信息。

    Args:
        file_path: Markdown 文档路径。

    Returns:
        dict: 解析后的故障记录。
    """
    target = Path(file_path)
    if not target.exists():
        return None

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    # 提取标题
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else target.stem

    # 提取日期
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", target.name)
    doc_date = date_match.group(1) if date_match else None

    # 提取章节
    sections = {}
    current_section = "summary"
    current_content = []

    for line in content.splitlines():
        heading_match = re.match(r"^#{1,3}\s+(.+)$", line)
        if heading_match:
            if current_content:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = heading_match.group(1).strip()
            current_content = []
        else:
            current_content.append(line)

    if current_content:
        sections[current_section] = "\n".join(current_content).strip()

    # 提取关键词/症状
    symptoms = []
    for section_name, section_content in sections.items():
        if re.search(r"(?:问题|故障|异常|错误|症状|现象)", section_name):
            # 提取列表项
            items = re.findall(r"[-*]\s+(.+)", section_content)
            symptoms.extend(items)

    # 提取修复步骤
    fixes = []
    for section_name, section_content in sections.items():
        if re.search(r"(?:修复|解决|处理|建议|方案|对策|修复步骤)", section_name):
            items = re.findall(r"(?:\d+[.、]|\-)\s+(.+)", section_content)
            fixes.extend(items)

    # 提取关键文件路径
    file_refs = re.findall(r"`([^`]*(?:\.py|\.json|\.sh|\.ts|\.md|\.yaml)[^`]*)`", content)

    # 分类
    categories = classify_fault(content)

    return {
        "id": target.stem,
        "title": title,
        "date": doc_date,
        "file_path": str(target),
        "categories": [c[0] for c in categories[:3]],
        "primary_category": categories[0][0] if categories else "unknown",
        "symptoms": symptoms[:10],
        "fixes": fixes[:10],
        "file_refs": list(set(file_refs))[:20],
        "content_length": len(content),
        "section_count": len(sections),
    }


# ──────────────────────────────────────────────
# 索引构建
# ──────────────────────────────────────────────

def build_knowledge_index(docs_dir, output_path=None):
    """
    扫描 docs 目录构建故障知识库索引。

    Args:
        docs_dir: 文档目录。
        output_path: 索引输出路径。

    Returns:
        dict: 知识库索引。
    """
    docs_path = Path(docs_dir)
    if not docs_path.exists():
        return {"error": f"目录不存在: {docs_dir}"}

    entries = []
    for md_file in docs_path.rglob("*.md"):
        parsed = parse_fault_document(md_file)
        if parsed:
            entries.append(parsed)

    # 按日期降序排列
    entries.sort(key=lambda x: x.get("date") or "0000-00-00", reverse=True)

    # 按类别汇总
    category_index = {}
    for entry in entries:
        cat = entry.get("primary_category", "unknown")
        if cat not in category_index:
            category_index[cat] = {
                "label": FAULT_CATEGORIES.get(cat, {}).get("label", cat),
                "count": 0,
                "entries": [],
            }
        category_index[cat]["count"] += 1
        category_index[cat]["entries"].append({
            "id": entry["id"],
            "title": entry["title"],
            "date": entry["date"],
        })

    index = {
        "built_at": datetime.now().isoformat(),
        "docs_dir": str(docs_dir),
        "total_entries": len(entries),
        "category_index": category_index,
        "entries": entries,
    }

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(index, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"✅ 知识库索引已构建: {out} ({len(entries)} 条记录)")

    return index


# ──────────────────────────────────────────────
# 查询引擎
# ──────────────────────────────────────────────

def query_knowledge_base(index, query_text, top_n=5):
    """
    在知识库中查询匹配的故障记录。

    Args:
        index: 知识库索引。
        query_text: 查询文本。
        top_n: 返回前 N 条结果。

    Returns:
        list[dict]: 匹配结果。
    """
    query_lower = query_text.lower()
    query_tokens = set(re.findall(r"[\w\u4e00-\u9fff]+", query_lower))

    scored_results = []
    for entry in index.get("entries", []):
        score = 0

        # 标题匹配
        title_lower = entry.get("title", "").lower()
        for token in query_tokens:
            if token in title_lower:
                score += 10

        # 症状匹配
        for symptom in entry.get("symptoms", []):
            symptom_lower = symptom.lower()
            for token in query_tokens:
                if token in symptom_lower:
                    score += 5

        # 类别匹配
        query_categories = classify_fault(query_text)
        entry_categories = set(entry.get("categories", []))
        for qc, _ in query_categories:
            if qc in entry_categories:
                score += 3

        # 文件引用匹配
        for ref in entry.get("file_refs", []):
            for token in query_tokens:
                if token in ref.lower():
                    score += 2

        if score > 0:
            scored_results.append({
                "score": score,
                "entry": entry,
            })

    scored_results.sort(key=lambda x: x["score"], reverse=True)
    return scored_results[:top_n]


def format_query_results(results, query_text):
    """格式化查询结果为 Markdown。"""
    lines = [
        f"# 🔍 故障知识库查询结果",
        "",
        f"> 查询: `{query_text}`",
        f"> 匹配: {len(results)} 条",
        "",
    ]

    if not results:
        lines.append("**未找到匹配的故障记录。**")
        return "\n".join(lines)

    for idx, result in enumerate(results, start=1):
        entry = result["entry"]
        score = result["score"]
        lines.append(f"## {idx}. {entry['title']} (相关度: {score})")
        lines.append("")
        if entry.get("date"):
            lines.append(f"- 📅 {entry['date']}")
        lines.append(f"- 📂 类型: {FAULT_CATEGORIES.get(entry.get('primary_category', ''), {}).get('label', entry.get('primary_category', '未知'))}")
        lines.append(f"- 📄 文件: `{entry.get('file_path', 'N/A')}`")

        if entry.get("symptoms"):
            lines.append(f"- **症状**: {'; '.join(entry['symptoms'][:3])}")

        if entry.get("fixes"):
            lines.append(f"- **修复**: {'; '.join(entry['fixes'][:3])}")

        if entry.get("file_refs"):
            lines.append(f"- **相关文件**: {', '.join(f'`{r}`' for r in entry['file_refs'][:5])}")

        lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

def build_cli_parser():
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="故障知识库 — 自动索引故障文档并支持关键词查询",
    )
    parser.add_argument("--docs-dir", default=None, help="文档目录")
    parser.add_argument("--build-index", action="store_true", help="构建索引")
    parser.add_argument("--index-output", default=None, help="索引输出路径")
    parser.add_argument("--query", default=None, help="查询关键词")
    parser.add_argument("--index-path", default=None, help="已有索引文件路径（查询时使用）")
    parser.add_argument("--top", type=int, default=5, help="返回前 N 条结果")
    return parser


def main():
    """CLI 主入口。"""
    configure_process_utf8_stdio()
    parser = build_cli_parser()
    args = parser.parse_args()

    if args.build_index and args.docs_dir:
        index = build_knowledge_index(args.docs_dir, args.index_output)
        if args.query:
            results = query_knowledge_base(index, args.query, args.top)
            print(format_query_results(results, args.query))
    elif args.query:
        if args.index_path:
            index = json.loads(Path(args.index_path).read_text(encoding="utf-8"))
        elif args.docs_dir:
            index = build_knowledge_index(args.docs_dir)
        else:
            print("❌ 查询需要 --docs-dir 或 --index-path", file=sys.stderr)
            sys.exit(1)
        results = query_knowledge_base(index, args.query, args.top)
        print(format_query_results(results, args.query))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
