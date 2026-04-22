#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
失败次数跟踪器 — failure_tracker.py

职责：
1. 跟踪同类任务的失败次数
2. 当触发条件达到（连续 2 次失败）时，输出告警并标记需要执行失败学习流程
3. 持久化失败记录到 .workflow/failure-log/failure_records.ndjson

使用方式：
    # 记录一次失败
    python failure_tracker.py record --task-type "api_integration" --model "gpt-5.4" --reason "接口签名不匹配"

    # 检查是否触发失败学习
    python failure_tracker.py check --task-type "api_integration"

    # 查看失败统计
    python failure_tracker.py stats
"""

import json
import sys
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("failure_tracker")

# 北京时间
BEIJING_TZ = timezone(timedelta(hours=8))

# 默认失败记录存放路径
DEFAULT_LOG_DIR = ".workflow/failure-log"
DEFAULT_LOG_FILE = "failure_records.ndjson"

# 触发失败学习的连续失败次数阈值
CONSECUTIVE_FAILURE_THRESHOLD = 2


def get_log_path(log_dir: str = DEFAULT_LOG_DIR) -> Path:
    """
    获取失败记录文件路径，不存在则创建目录。

    参数:
        log_dir: 失败记录目录

    返回:
        失败记录文件的 Path 对象
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    return log_path / DEFAULT_LOG_FILE


def record_failure(
    task_type: str,
    model: str,
    reason: str,
    task_id: Optional[str] = None,
    project_key: Optional[str] = None,
    log_dir: str = DEFAULT_LOG_DIR,
) -> dict:
    """
    记录一次任务失败。

    参数:
        task_type: 任务类型（如 api_integration, data_pipeline）
        model: 使用的 AI 模型
        reason: 失败原因描述
        task_id: 可选的任务 ID
        project_key: 可选的项目标识
        log_dir: 失败记录目录

    返回:
        失败记录字典
    """
    record = {
        "timestamp": datetime.now(BEIJING_TZ).isoformat(),
        "task_type": task_type,
        "model": model,
        "reason": reason,
        "task_id": task_id,
        "project_key": project_key,
    }

    log_file = get_log_path(log_dir)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    logger.info("已记录失败: task_type=%s, model=%s, reason=%s", task_type, model, reason)
    return record


def load_records(log_dir: str = DEFAULT_LOG_DIR) -> list[dict]:
    """
    加载所有失败记录。

    参数:
        log_dir: 失败记录目录

    返回:
        失败记录列表
    """
    log_file = get_log_path(log_dir)
    if not log_file.exists():
        return []

    records = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as err:
                logger.warning("第 %d 行 JSON 解析失败: %s", line_num, err)
    return records


def check_trigger(task_type: str, log_dir: str = DEFAULT_LOG_DIR) -> dict:
    """
    检查指定任务类型是否触发失败学习流程。

    判断逻辑：最近的连续 N 条同类任务记录全部失败 → 触发。

    参数:
        task_type: 任务类型
        log_dir: 失败记录目录

    返回:
        包含 triggered、consecutive_failures、recent_failures 的字典
    """
    records = load_records(log_dir)

    # 过滤同类任务
    same_type_records = [r for r in records if r.get("task_type") == task_type]

    # 按时间倒序
    same_type_records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)

    consecutive_count = len(same_type_records)  # 都是失败记录
    triggered = consecutive_count >= CONSECUTIVE_FAILURE_THRESHOLD

    result = {
        "task_type": task_type,
        "triggered": triggered,
        "consecutive_failures": consecutive_count,
        "threshold": CONSECUTIVE_FAILURE_THRESHOLD,
        "recent_failures": same_type_records[:5],  # 最近 5 条
    }

    if triggered:
        logger.warning(
            "⚠️ 失败学习触发：任务类型 [%s] 连续失败 %d 次（阈值 %d）",
            task_type, consecutive_count, CONSECUTIVE_FAILURE_THRESHOLD,
        )
        logger.warning("   必须与人沟通，分析根因后才能继续")
    else:
        logger.info(
            "任务类型 [%s] 失败 %d 次，未达触发阈值 %d",
            task_type, consecutive_count, CONSECUTIVE_FAILURE_THRESHOLD,
        )

    return result


def get_stats(log_dir: str = DEFAULT_LOG_DIR) -> dict:
    """
    输出失败统计信息。

    参数:
        log_dir: 失败记录目录

    返回:
        按任务类型分组的统计信息
    """
    records = load_records(log_dir)
    stats: dict[str, dict] = {}

    for record in records:
        task_type = record.get("task_type", "unknown")
        if task_type not in stats:
            stats[task_type] = {
                "total_failures": 0,
                "models_involved": set(),
                "reasons": [],
            }
        stats[task_type]["total_failures"] += 1
        stats[task_type]["models_involved"].add(record.get("model", "unknown"))
        stats[task_type]["reasons"].append(record.get("reason", ""))

    # 转换 set 为 list 以便 JSON 序列化
    for task_type_stats in stats.values():
        task_type_stats["models_involved"] = list(task_type_stats["models_involved"])
        # 只保留最近 5 个原因
        task_type_stats["reasons"] = task_type_stats["reasons"][-5:]

    return stats


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="失败次数跟踪器")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # record 子命令
    record_parser = subparsers.add_parser("record", help="记录一次失败")
    record_parser.add_argument("--task-type", required=True, help="任务类型")
    record_parser.add_argument("--model", required=True, help="使用的 AI 模型")
    record_parser.add_argument("--reason", required=True, help="失败原因")
    record_parser.add_argument("--task-id", help="任务 ID")
    record_parser.add_argument("--project-key", help="项目标识")
    record_parser.add_argument("--log-dir", default=DEFAULT_LOG_DIR)

    # check 子命令
    check_parser = subparsers.add_parser("check", help="检查是否触发失败学习")
    check_parser.add_argument("--task-type", required=True, help="任务类型")
    check_parser.add_argument("--log-dir", default=DEFAULT_LOG_DIR)

    # stats 子命令
    stats_parser = subparsers.add_parser("stats", help="查看失败统计")
    stats_parser.add_argument("--log-dir", default=DEFAULT_LOG_DIR)

    args = parser.parse_args()

    if args.command == "record":
        result = record_failure(
            task_type=args.task_type,
            model=args.model,
            reason=args.reason,
            task_id=args.task_id,
            project_key=args.project_key,
            log_dir=args.log_dir,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "check":
        result = check_trigger(args.task_type, args.log_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["triggered"]:
            sys.exit(1)  # 触发失败学习 → 非零退出

    elif args.command == "stats":
        result = get_stats(args.log_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
