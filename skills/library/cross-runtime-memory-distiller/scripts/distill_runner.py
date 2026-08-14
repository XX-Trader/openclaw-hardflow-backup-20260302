#!/usr/bin/env python3
"""蒸馏主入口：编排全链路 Source Pull → Clean → Score → Classify → Write → Report。

distill_runner 是整个蒸馏技能的唯一执行入口。
它编排所有子模块：source adapter → cleaner → classifier → write gateway → reporter。

CLI 用法:
  python distill_runner.py --hosts openclaw,hermes --sources claude,openclaw --since-hours 48 --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

# ── 路径与 UTF-8 ─────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
CONFIG_DIR = SKILL_DIR / "config"

sys.path.insert(0, str(SCRIPT_DIR))


def _configure_utf8_stdio() -> None:
    """复用仓库 UTF-8 运行时配置。"""
    shared_dir = SCRIPT_DIR.parents[4] / "scripts" / "openclaw-ops" / "shared"
    if str(shared_dir) not in sys.path:
        sys.path.insert(0, str(shared_dir))
    try:
        from utf8_runtime import configure_process_utf8_stdio  # type: ignore
    except Exception:
        return
    configure_process_utf8_stdio()


_configure_utf8_stdio()

# ── 日志 ──────────────────────────────────────────────────────────────

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logger = logging.getLogger("distill_runner")


def _setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """配置日志。"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
        force=True,
    )
    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        logger.addHandler(fh)


# ── 配置加载 ──────────────────────────────────────────────────────────


def load_config(name: str) -> dict:
    """加载配置文件。

    Args:
        name: 配置文件名（如 "memory_limits", "storage_policy"）

    Returns:
        配置字典

    Raises:
        FileNotFoundError: 配置文件不存在时 Fail-Fast
        json.JSONDecodeError: 配置文件格式错误
    """
    env_key = f"{name.upper().replace('.', '_').replace('-', '_')}_CONFIG_PATH"
    env_path = os.environ.get(env_key)
    config_path = Path(env_path) if env_path else CONFIG_DIR / f"{name}.json"
    if not config_path.exists():
        raise FileNotFoundError(f"config_not_found:{config_path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


def join_runtime_path(base: str, *parts: str) -> str:
    root = str(base or "").strip()
    clean_parts = [str(part).strip("/\\") for part in parts if str(part).strip("/\\")]
    if root.startswith("/") and not root.startswith("//"):
        return str(PurePosixPath(root).joinpath(*clean_parts))
    return str(Path(root).joinpath(*clean_parts))


def resolve_default_db_path(hosts: list[str], probe_results: dict[str, dict[str, Any]]) -> str:
    preferred_host = str(hosts[0]).strip().lower() if hosts else "openclaw"
    payload = (
        probe_results.get(preferred_host)
        or probe_results.get("openclaw")
        or next(iter(probe_results.values()), {})
    )
    runtime_home = str(payload.get("home", "")).strip()
    if not runtime_home:
        runtime_home = str(Path.home() / ".openclaw")
    return join_runtime_path(runtime_home, "ops", "distill", "distill.db")


# ── 主流程 ────────────────────────────────────────────────────────────


def run_distill(
    hosts: list[str],
    sources: list[str],
    since_hours: int = 48,
    db_path: str = "",
    evidence_dir: str = "",
    report_dir: str = "",
    skip_llm: bool = False,
    classifier: str = "rules",
    emit_bridge_report: bool = False,
    dry_run: bool = False,
    task_id: str = "",
    trace_id: str = "",
    workspace: str = "",
) -> dict[str, Any]:
    """执行蒸馏全链路。

    步骤:
    1. 探测宿主环境
    2. 接入数据源
    3. 清洗与切分
    4. 打分与路由
    5. 使用确定性规则分类
    6. 写入热记忆 / 落盘产物
    7. 生成报告

    Args:
        hosts: 宿主列表
        sources: 数据源列表
        since_hours: 回溯时间窗口
        db_path: distill.db 路径
        evidence_dir: 证据目录
        report_dir: 报告输出目录
        skip_llm: 旧版兼容参数，等同于选择规则分类器
        classifier: 分类器名称，当前支持 rules
        emit_bridge_report: 产出控制面桥接报告
        dry_run: 只探测+打分，不写入
        task_id: 关联任务 ID
        trace_id: 关联追溯 ID
        workspace: 工作区路径

    Returns:
        蒸馏报告字典
    """
    if classifier != "rules":
        raise ValueError(f"unsupported classifier: {classifier}")
    start_time = datetime.now()

    # 1. 探测宿主环境
    logger.info("=== 蒸馏开始 === hosts=%s sources=%s since=%dh dry_run=%s",
                hosts, sources, since_hours, dry_run)
    from runtime_probe import probe_hosts
    probe_results = probe_hosts(hosts=hosts)

    # 2. 初始化存储层
    if not db_path:
        db_path = resolve_default_db_path(hosts, probe_results)
    from evidence_store import EvidenceStore
    store = EvidenceStore(db_path)
    logger.info("store_initialized:db=%s stats=%s", db_path, store.stats())

    # 3. 加载配置
    try:
        memory_config = load_config("memory_limits")
    except FileNotFoundError:
        logger.warning("memory_limits配置缺失，热记忆写入将跳过")
        memory_config = {}
    try:
        storage_config = load_config("storage_policy")
    except FileNotFoundError:
        logger.warning("storage_policy配置缺失，使用默认存储策略")
        storage_config = {}

    # 4. 接入数据源
    from distill_source_adapters import get_adapter, RawEvent
    all_events: list[dict] = []
    for source in sources:
        try:
            adapter = get_adapter(source, workspace_root=workspace)
        except ValueError as exc:
            logger.warning("skip_source:%s", exc)
            continue

        for host_name in hosts:
            probe_result = probe_results.get(host_name, {})
            # 传递 since_hours 供适配器做 mtime 预过滤
            probe_result["since_hours"] = since_hours
            paths = adapter.probe(probe_result)
            logger.info("source_probed:source=%s host=%s paths=%d", source, host_name, len(paths))

            for path in paths:
                cursor = store.get_cursor(source, host_name, workspace or "default")
                events = adapter.extract(path, cursor)
                event_dicts = [e.to_dict() if hasattr(e, 'to_dict') else e for e in events]
                all_events.extend(event_dicts)

                # 更新游标
                if events and not dry_run:
                    hint = adapter.cursor_hint(path)
                    store.set_cursor(source, host_name, workspace or "default", hint)

    # 全局时间过滤兜底：丢弃 since_hours 之前的事件
    if since_hours > 0:
        from datetime import timedelta
        cutoff_iso = (start_time - timedelta(hours=since_hours)).isoformat()
        before_count = len(all_events)
        all_events = [e for e in all_events if e.get("timestamp", "") >= cutoff_iso or not e.get("timestamp")]
        logger.info("time_filter:before=%d after=%d cutoff=%s", before_count, len(all_events), cutoff_iso)

    logger.info("events_collected:total=%d", len(all_events))

    if not all_events:
        logger.info("no_events:skip_distill")
        return {
            "timestamp": start_time.isoformat(),
            "status": "no_events",
            "summary": {"total_artifacts": 0},
        }

    # 5. 清洗与切分
    from distill_cleaner import clean_event, segment_events_into_windows, score_and_route
    cleaned_events = [clean_event(e) for e in all_events]

    # 落盘归一化事件
    if not dry_run:
        written = store.upsert_events(cleaned_events)
        logger.info("events_stored:written=%d", written)

    # 切分窗口
    windows = segment_events_into_windows(cleaned_events, source="mixed", host="mixed")
    windows = score_and_route(windows)
    high_value = [w for w in windows if w.status == "high_value"]
    logger.info("windows:total=%d high_value=%d index_only=%d skip=%d",
                len(windows), len(high_value),
                sum(1 for w in windows if w.status == "index_only"),
                sum(1 for w in windows if w.status == "skip"))

    # 落盘候选窗口
    if not dry_run:
        for w in windows:
            if w.status != "skip":
                cd = w.to_dict()
                # CandidateWindow 字段 → candidate_windows 表字段映射
                cd.setdefault("candidate_id", cd.get("window_id", store.next_id("cand")))
                cd.setdefault("window_text", cd.get("text", ""))
                store.upsert_candidate(cd)

    # 6. 分类
    from distill_classifier import classify_with_rules
    artifacts: list[dict[str, Any]] = []

    for w in high_value:
        artifact = classify_with_rules(w.text, w.window_id, w.source)

        artifact["artifact_id"] = store.next_id("artifact")
        artifact["trace_id"] = trace_id
        artifact["task_id"] = task_id
        artifact["evidence_refs"] = w.event_ids

        # 落盘产物
        if not dry_run:
            store.upsert_artifact(artifact)
        artifacts.append(artifact)

    # 7. 写入热记忆
    if not dry_run and memory_config:
        from memory_write_gateway import MemoryAction, execute_write
        for artifact in artifacts:
            if artifact.get("target_kind") == "hot_memory" and not artifact.get("requires_human_review"):
                target = "user" if artifact["kind"] == "user" else "memory"
                # 取第一个有 hot_memory_paths 的宿主
                hot_paths = {}
                for h in hosts:
                    hp = probe_results.get(h, {}).get("hot_memory_paths", {})
                    if hp:
                        hot_paths = hp
                        break
                if not hot_paths:
                    continue

                action = MemoryAction(
                    action="add",
                    target=target,
                    content=f"- {artifact['title']}",
                    title=artifact["title"],
                    reason=artifact.get("rationale", "蒸馏产物"),
                )
                result = execute_write(action, hot_paths, memory_config, db_path, artifact["artifact_id"])
                logger.info("memory_write:artifact=%s success=%s", artifact["artifact_id"], result.success)

    # 8. Repo Delta
    repo_delta = None
    if workspace:
        from source_repo_delta import collect_repo_delta
        repo_delta = collect_repo_delta(workspace, since_hours)
        logger.info("repo_delta:changed_files=%d commits=%d",
                     len(repo_delta.get("changed_files", [])),
                     len(repo_delta.get("commits", [])))

    # 9. Skill Draft
    skill_drafts = []
    if not dry_run:
        from skill_draft_generator import generate_skill_draft
        candidates_dir = Path(db_path).parent / "skill-candidates"
        skill_drafts = generate_skill_draft(artifacts, candidates_dir, workspace=workspace)

    # 10. 报告
    from distill_reporter import build_distill_report, build_bridge_report, save_report
    report = build_distill_report(
        artifacts, stats=store.stats(), since_hours=since_hours, dry_run=dry_run,
    )

    if emit_bridge_report:
        bridges = build_bridge_report(artifacts, workspace, trace_id, task_id)
        report["control_plane_bridge_ids"] = [b["bridge_id"] for b in bridges]
        if not dry_run and report_dir:
            for bridge in bridges:
                store.upsert_bridge(bridge)
            save_report({"bridges": bridges, "timestamp": report["timestamp"]},
                        Path(report_dir) / "bridge", "bridge")

    report["elapsed_seconds"] = (datetime.now() - start_time).total_seconds()
    report["skill_drafts"] = skill_drafts
    report["classifier"] = "rules-v1"

    if not dry_run and report_dir:
        save_report(report, report_dir, "distill")

    store.close()

    logger.info("=== 蒸馏完成 === artifacts=%d elapsed=%.1fs",
                len(artifacts), report.get("elapsed_seconds", 0))
    return report


# ── CLI ───────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(description="Cross-Runtime Memory Distiller 主入口")
    parser.add_argument("--hosts", default="openclaw,hermes", help="逗号分隔的宿主列表")
    parser.add_argument("--sources", default="claude,openclaw", help="逗号分隔的数据源列表")
    parser.add_argument("--since-hours", type=int, default=48, help="回溯时间窗口（小时）")
    parser.add_argument("--db-path", default="", help="distill.db 路径")
    parser.add_argument("--evidence-dir", default="", help="证据包目录")
    parser.add_argument("--report-dir", default="", help="报告输出目录")
    parser.add_argument("--classifier", choices=["rules"], default="rules", help="确定性分类器")
    parser.add_argument("--skip-llm", action="store_true",
                        help="旧版兼容参数，等同于 --classifier rules")
    parser.add_argument("--emit-bridge-report", action="store_true", help="产出控制面桥接报告")
    parser.add_argument("--dry-run", action="store_true", help="只探测+打分，不写入热记忆")
    parser.add_argument("--log-level", default="INFO", help="日志级别")
    parser.add_argument("--log-file", default="", help="日志文件")
    parser.add_argument("--task-id", default="", help="关联任务 ID")
    parser.add_argument("--trace-id", default="", help="关联追溯 ID")
    parser.add_argument("--workspace", default="", help="工作区路径（用于 repo delta）")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。"""
    parser = build_parser()
    args = parser.parse_args(argv)

    _setup_logging(args.log_level, args.log_file or None)

    report = run_distill(
        hosts=[h.strip() for h in args.hosts.split(",") if h.strip()],
        sources=[s.strip() for s in args.sources.split(",") if s.strip()],
        since_hours=args.since_hours,
        db_path=args.db_path,
        evidence_dir=args.evidence_dir,
        report_dir=args.report_dir,
        skip_llm=args.skip_llm,
        classifier=args.classifier,
        emit_bridge_report=args.emit_bridge_report,
        dry_run=args.dry_run,
        task_id=args.task_id,
        trace_id=args.trace_id,
        workspace=args.workspace,
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
