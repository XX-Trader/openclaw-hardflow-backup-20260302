#!/usr/bin/env python3
"""
项目记忆写入器。
消费蒸馏报告，按 project_key 路由写入项目记忆目录。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


def setup_logging() -> logging.Logger:
    log_dir = Path(".workflow/logs/project_memory_writer")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"

    logger = logging.getLogger("project_memory_writer")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(logging.WARNING)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return logger


DATA_DIR = Path(".workflow/project-memory")

ArtifactType = Literal["profile", "decision", "api", "source", "rule", "changelog"]

ROUTE_MAP: dict[ArtifactType, tuple[str, str]] = {
    "profile": ("PROJECT_PROFILE.md", "overwrite"),
    "decision": ("DECISIONS.md", "append"),
    "api": ("API_REGISTRY.json", "merge_json"),
    "source": ("SOURCE_REGISTRY.json", "merge_json"),
    "rule": ("DELIVERY_RULES.md", "overwrite"),
    "changelog": ("CHANGELOG.ndjson", "append_ndjson"),
}


@dataclass
class Artifact:
    project_key: str
    artifact_type: ArtifactType
    content: str
    source: str = "distill"
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


def ensure_project_dir(project_key: str) -> Path:
    project_dir = DATA_DIR / project_key
    project_dir.mkdir(parents=True, exist_ok=True)

    skeleton = {
        "PROJECT_PROFILE.md": f"# {project_key} 项目画像\n\n",
        "DECISIONS.md": f"# {project_key} 决策记录\n\n",
        "DELIVERY_RULES.md": f"# {project_key} 交付规则\n\n",
        "API_REGISTRY.json": json.dumps({"project_key": project_key, "apis": []}, ensure_ascii=False, indent=2),
        "SOURCE_REGISTRY.json": json.dumps({"project_key": project_key, "sources": []}, ensure_ascii=False, indent=2),
    }

    for filename, content in skeleton.items():
        filepath = project_dir / filename
        if not filepath.exists():
            filepath.write_text(content, encoding="utf-8")

    return project_dir


def write_artifact(project_dir: Path, artifact: Artifact) -> dict:
    target, mode = ROUTE_MAP.get(artifact.artifact_type, ("UNKNOWN", "skip"))
    target_path = project_dir / target

    if mode == "skip":
        return {"status": "skipped", "reason": "unknown_artifact_type"}

    if mode == "overwrite":
        target_path.write_text(artifact.content, encoding="utf-8")
        return {"status": "written", "mode": "overwrite", "path": str(target_path)}

    elif mode == "append":
        with open(target_path, "a", encoding="utf-8") as f:
            f.write(f"\n## [{artifact.timestamp}]\n\n{artifact.content}\n")
        return {"status": "written", "mode": "append", "path": str(target_path)}

    elif mode == "merge_json":
        try:
            existing = json.loads(target_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            existing = {"project_key": artifact.project_key}

        try:
            new_data = json.loads(artifact.content)
        except json.JSONDecodeError:
            return {"status": "error", "reason": "invalid_json_content"}

        # 简单合并策略：以新数据为主
        if isinstance(new_data, dict):
            existing.update(new_data)
        target_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "written", "mode": "merge_json", "path": str(target_path)}

    elif mode == "append_ndjson":
        with open(target_path, "a", encoding="utf-8") as f:
            record = {
                "timestamp": artifact.timestamp,
                "content": artifact.content,
                "source": artifact.source,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return {"status": "written", "mode": "append_ndjson", "path": str(target_path)}

    return {"status": "error", "reason": "unknown_mode"}


def parse_distill_report(path: Path) -> list[Artifact]:
    content = path.read_text(encoding="utf-8")
    artifacts: list[Artifact] = []

    # 尝试解析 JSON 格式
    try:
        data = json.loads(content)
        routed = data.get("project_routed_artifacts", [])
        for item in routed:
            artifacts.append(Artifact(
                project_key=item.get("project_key", ""),
                artifact_type=item.get("artifact_type", "changelog"),
                content=item.get("content", ""),
                source="distill",
            ))
        return artifacts
    except json.JSONDecodeError:
        pass

    # 尝试解析 Markdown 格式（正则提取）
    import re
    pattern = re.compile(
        r"## 项目路由产物\s*\n"
        r".*?- project_key:\s*(\S+)\s*\n"
        r".*?- artifact_type:\s*(\S+)\s*\n"
        r".*?### 内容\s*\n(.*?)(?=## 项目路由产物|$)",
        re.DOTALL,
    )
    for match in pattern.finditer(content):
        artifacts.append(Artifact(
            project_key=match.group(1),
            artifact_type=match.group(2),  # type: ignore[arg-type]
            content=match.group(3).strip(),
            source="distill",
        ))

    return artifacts


def main(argv: list[str] | None = None) -> int:
    global DATA_DIR
    parser = argparse.ArgumentParser(description="项目记忆写入器")
    parser.add_argument("--distill-report", help="蒸馏报告路径")
    parser.add_argument("--data-dir", default="", help="项目记忆根目录")
    parser.add_argument("--project-key", help="直接指定项目 key")
    parser.add_argument("--artifact-type", choices=["profile", "decision", "api", "source", "rule", "changelog"])
    parser.add_argument("--content", help="直接指定内容")
    parser.add_argument("--content-file", help="从文件读取直接写入内容")
    parser.add_argument("--source", default="manual", help="来源")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if str(args.data_dir or "").strip():
        DATA_DIR = Path(args.data_dir).expanduser()

    logger = setup_logging()

    artifacts: list[Artifact] = []
    direct_content = args.content
    if args.content_file:
        content_path = Path(args.content_file).expanduser()
        if not content_path.exists():
            print(json.dumps({"error": "content_file_not_found"}, ensure_ascii=False))
            return 1
        direct_content = content_path.read_text(encoding="utf-8")

    if args.distill_report:
        report_path = Path(args.distill_report)
        if not report_path.exists():
            print(json.dumps({"error": "report_not_found"}, ensure_ascii=False))
            return 1
        artifacts = parse_distill_report(report_path)
    elif args.project_key and args.artifact_type and direct_content:
        artifacts = [Artifact(
            project_key=args.project_key,
            artifact_type=args.artifact_type,  # type: ignore[arg-type]
            content=direct_content,
            source=args.source,
        )]
    else:
        print(json.dumps({"error": "insufficient_arguments"}, ensure_ascii=False))
        return 1

    results: list[dict] = []
    for artifact in artifacts:
        if not artifact.project_key:
            results.append({"status": "skipped", "reason": "missing_project_key"})
            continue

        if args.dry_run:
            target, mode = ROUTE_MAP.get(artifact.artifact_type, ("UNKNOWN", "skip"))
            result = {
                "status": "dry_run",
                "mode": mode,
                "path": str(DATA_DIR / artifact.project_key / target),
            }
        else:
            project_dir = ensure_project_dir(artifact.project_key)
            result = write_artifact(project_dir, artifact)
        result["project_key"] = artifact.project_key
        result["artifact_type"] = artifact.artifact_type
        results.append(result)
        logger.info("写入 %s/%s: %s", artifact.project_key, artifact.artifact_type, result["status"])

    summary = {
        "processed": len(artifacts),
        "success": len([r for r in results if r.get("status") == "written"]),
        "failed": len([r for r in results if r.get("status") == "error"]),
        "skipped": len([r for r in results if r.get("status") == "skipped"]),
        "details": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
