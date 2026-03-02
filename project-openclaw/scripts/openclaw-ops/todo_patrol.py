#!/usr/bin/env python3
"""
TODO patrol script (15-minute cycle).

Main behavior:
1. Read coordinator TODO.md and detect unfinished items.
2. De-duplicate alerts by item + status.
3. Check execution ownership/status from TODO-EXECUTION-BOARD.md.
4. Only ask coordinator assignment for UNASSIGNED items.
5. Merge tester failures into TODO.md (de-duplicated append).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8))

STATUS_UNASSIGNED = "UNASSIGNED"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_BLOCKED = "BLOCKED"
STATUS_DONE = "DONE"


def now_tz() -> datetime:
    return datetime.now(TZ)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def parse_todo_items(content: str) -> list[dict]:
    items: list[dict] = []
    lines = content.split("\n")
    current_section = ""
    current_priority = ""

    for i, line in enumerate(lines):
        if line.startswith("## "):
            current_section = line[3:].strip()
            continue

        if "P0" in line:
            current_priority = "P0"
        elif "P1" in line:
            current_priority = "P1"
        elif "P2" in line:
            current_priority = "P2"

        if line.strip().startswith("- [ ]"):
            item_text = line.strip()[6:].strip()
            if item_text:
                items.append(
                    {
                        "id": sha256(item_text),
                        "text": item_text,
                        "section": current_section,
                        "priority": current_priority,
                        "line_num": i + 1,
                        "raw_line": line.strip(),
                    }
                )
    return items


def parse_exec_board(content: str) -> dict[str, dict]:
    assignments: dict[str, dict] = {}
    pattern = r"#### 工单：([^\n]+)\n((?:(?!####)[\s\S])*)"
    matches = re.findall(pattern, content)

    for title, body in matches:
        role_match = re.search(r"^### (\S+)", body, re.MULTILINE)
        role = role_match.group(1) if role_match else "unknown"

        status = STATUS_UNASSIGNED
        if "进行中" in body or "执行中" in body or "IN_PROGRESS" in body.upper():
            status = STATUS_IN_PROGRESS
        elif "阻塞" in body or "BLOCKED" in body.upper():
            status = STATUS_BLOCKED
        elif "完成" in body or "DONE" in body.upper() or "已修复" in body:
            status = STATUS_DONE

        schedule_match = re.search(r"\*\*排期[^：]*：*\*?\*?([^*\n]+)", body)
        schedule = schedule_match.group(1).strip() if schedule_match else ""

        assignments[title] = {
            "role": role,
            "status": status,
            "schedule": schedule,
            "title": title,
        }
    return assignments


def match_todo_to_exec(todo_item: dict, exec_board: dict[str, dict]) -> dict | None:
    todo_text = todo_item["text"].lower()

    for title, info in exec_board.items():
        title_lower = title.lower()
        keywords = []
        for word in todo_text.split():
            if len(word) > 2 and word not in ["后端", "前端", "确认", "接口", "字段"]:
                keywords.append(word.lower())

        match_count = sum(1 for kw in keywords if kw in title_lower)
        if match_count >= 2 or (len(keywords) <= 2 and match_count >= 1):
            return info
    return None


def get_tester_failures(tester_reports_dir: Path) -> list[dict]:
    failures: list[dict] = []
    if not tester_reports_dir.exists():
        return failures

    recent_reports = sorted(
        tester_reports_dir.glob("tester_*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:3]

    table_pattern = (
        r"\| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| "
        r"([^|]+) \| (\d+) \| ([^|]+) \| ([^|]+) \| (OPEN[^|]*) \|"
    )

    for report_path in recent_reports:
        try:
            content = report_path.read_text(encoding="utf-8")
            if "FAIL" not in content and "OPEN/P0" not in content and "OPEN/P1" not in content:
                continue

            matches = re.findall(table_pattern, content)
            for match in matches:
                failures.append(
                    {
                        "sender": match[0].strip(),
                        "finder": match[1].strip(),
                        "category": match[2].strip(),
                        "location": match[3].strip(),
                        "time": match[4].strip(),
                        "count": int(match[5]),
                        "root_cause": match[6].strip(),
                        "solution": match[7].strip(),
                        "status": match[8].strip(),
                        "source_file": str(report_path),
                    }
                )
        except Exception:
            continue
    return failures


def load_state(state_file: Path) -> dict:
    if state_file.exists():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "updated_at": "",
        "todo_items": {},
        "alerted_items": {},
        "last_tester_check": "",
    }


def save_state(state_file: Path, state: dict, now: datetime) -> None:
    state["updated_at"] = now.isoformat()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def should_alert(item_id: str, status: str, state: dict, now: datetime) -> bool:
    alerted = state.get("alerted_items", {})
    key = f"{item_id}:{status}"
    if key not in alerted:
        return True

    last_alert = alerted.get(key, "")
    if last_alert:
        try:
            last_time = datetime.fromisoformat(last_alert)
            if (now - last_time) < timedelta(hours=1):
                return False
        except Exception:
            pass
    return True


def mark_alerted(item_id: str, status: str, state: dict, now: datetime) -> None:
    key = f"{item_id}:{status}"
    if "alerted_items" not in state:
        state["alerted_items"] = {}
    state["alerted_items"][key] = now.isoformat()


def merge_tester_failures_to_todo(
    failures: list[dict],
    todo_content: str,
    state: dict,
    now: datetime,
) -> tuple[str, list[str]]:
    if not failures:
        return todo_content, []

    added_items: list[str] = []
    existing_text = todo_content.lower()
    lines = todo_content.split("\n")

    has_tester_section = any("测试失败/阻塞项" in line for line in lines)
    new_lines: list[str] = []
    if not has_tester_section and failures:
        new_lines.append("")
        new_lines.append("## 测试失败/阻塞项（自动并入）")
        new_lines.append(f'> 更新时间：{now.strftime("%Y-%m-%d %H:%M")} UTC+8')
        new_lines.append("")

    for item in failures:
        item_text = f'{item["category"]}：{item["location"]} - {item["root_cause"][:50]}'
        item_hash = sha256(item_text)

        if item_hash in state.get("todo_items", {}):
            continue
        if item["location"] and item["location"].lower() in existing_text:
            continue

        priority = "P0" if "P0" in item["status"] else ("P1" if "P1" in item["status"] else "P2")
        line = (
            f'- [ ] {priority} {item_text}'
            f'（来源：tester 报告 {Path(item["source_file"]).name}）'
        )
        new_lines.append(line)
        added_items.append(item_text)

        if "todo_items" not in state:
            state["todo_items"] = {}
        state["todo_items"][item_hash] = {
            "added_at": now.isoformat(),
            "source": "tester",
            "status": STATUS_BLOCKED,
        }

    if new_lines:
        return todo_content.rstrip() + "\n" + "\n".join(new_lines) + "\n", added_items
    return todo_content, []


def format_message(
    todo_items: list[dict],
    exec_board: dict[str, dict],
    added_items: list[str],
    now: datetime,
    task: str,
) -> str:
    lines: list[str] = []
    unassigned = []
    in_progress = []
    blocked = []

    for item in todo_items:
        exec_info = match_todo_to_exec(item, exec_board)
        if exec_info:
            item["owner"] = exec_info["role"]
            item["status"] = exec_info["status"]
            item["schedule"] = exec_info.get("schedule", "")
        else:
            item["owner"] = "-"
            item["status"] = STATUS_UNASSIGNED
            item["schedule"] = ""

        if item["status"] == STATUS_UNASSIGNED:
            unassigned.append(item)
        elif item["status"] == STATUS_IN_PROGRESS:
            in_progress.append(item)
        elif item["status"] == STATUS_BLOCKED:
            blocked.append(item)

    if not unassigned and not blocked and not added_items:
        return "NO_REPLY"

    lines.append("发送人：ops-agent")
    lines.append("发现者：todo-patrol")
    lines.append(f"任务：{task}")
    lines.append("来源类别：workflow|TODO")
    lines.append(f"时间区间：{now.strftime('%Y-%m-%d %H:%M:%S')}（UTC+8）")
    lines.append("")

    if unassigned:
        lines.append("## 待分配任务（请求 coordinator 分配执行人）")
        for item in unassigned[:5]:
            lines.append(f"- [{item['priority']}] {item['text'][:60]}...")
            lines.append(f"  - owner: {item['owner']}")
            lines.append(f"  - status: {item['status']}")
        lines.append("")

    if in_progress:
        lines.append(f"## 进行中任务（{len(in_progress)}项，无需分配）")
        for item in in_progress[:3]:
            lines.append(f"- [{item['priority']}] {item['text'][:50]}... | owner: {item['owner']}")
        if len(in_progress) > 3:
            lines.append(f"  - ... 及其他 {len(in_progress) - 3} 项")
        lines.append("")

    if blocked:
        lines.append(f"## 阻塞项（{len(blocked)}项）")
        for item in blocked[:3]:
            lines.append(f"- [{item['priority']}] {item['text'][:50]}...")
        lines.append("")

    if added_items:
        lines.append(f"## 新并入测试失败项（{len(added_items)}项）")
        for item in added_items[:3]:
            lines.append(f"- {item[:60]}...")
        lines.append("")

    if unassigned:
        lines.append("## 需用户确认")
        lines.append("> 以上未分配项是否需要 coordinator 立即分配执行人？")
        lines.append("> 回复 \"分配\" 或指定执行人即可触发分配流程")

    return "\n".join(lines)


def main() -> None:
    home = Path(os.path.expanduser("~"))
    default_ops_root = Path(
        os.environ.get("WORKSPACE_OPS_ROOT", str(home / ".openclaw/workspace-ops-agent"))
    ).expanduser()
    default_ops_dir = Path(
        os.environ.get("OPENCLAW_OPS_DIR", str(default_ops_root / "ops"))
    ).expanduser()
    default_coordinator_ws = Path(
        os.environ.get("COORDINATOR_WORKSPACE", str(home / ".openclaw/workspace-coordinator"))
    ).expanduser()
    default_tester_ws = Path(
        os.environ.get("TESTER_WORKSPACE", str(home / ".openclaw/workspace-tester"))
    ).expanduser()

    parser = argparse.ArgumentParser()
    parser.add_argument("--task", default="cron:todo-patrol")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ops-dir", default=str(default_ops_dir))
    parser.add_argument("--coordinator-ws", default=str(default_coordinator_ws))
    parser.add_argument("--tester-ws", default=str(default_tester_ws))
    parser.add_argument("--state-file", default="")
    parser.add_argument("--todo-file", default="")
    parser.add_argument("--exec-board-file", default="")
    args = parser.parse_args()

    now = now_tz()
    ops_dir = Path(args.ops_dir).expanduser()
    coordinator_ws = Path(args.coordinator_ws).expanduser()
    tester_ws = Path(args.tester_ws).expanduser()

    state_file = Path(args.state_file).expanduser() if args.state_file else ops_dir / "todo-patrol-state.json"
    todo_file = Path(args.todo_file).expanduser() if args.todo_file else coordinator_ws / "TODO.md"
    exec_board_file = (
        Path(args.exec_board_file).expanduser()
        if args.exec_board_file
        else coordinator_ws / "TODO-EXECUTION-BOARD.md"
    )
    tester_reports_dir = tester_ws / "reports"

    ops_dir.mkdir(parents=True, exist_ok=True)
    state = load_state(state_file)

    if not todo_file.exists():
        print("NO_REPLY")
        return

    todo_content = todo_file.read_text(encoding="utf-8")
    todo_items = parse_todo_items(todo_content)

    exec_board: dict[str, dict] = {}
    if exec_board_file.exists():
        exec_content = exec_board_file.read_text(encoding="utf-8")
        exec_board = parse_exec_board(exec_content)

    tester_failures = get_tester_failures(tester_reports_dir)

    added_items: list[str] = []
    if tester_failures and not args.dry_run:
        todo_content, added_items = merge_tester_failures_to_todo(tester_failures, todo_content, state, now)
        if added_items:
            todo_file.write_text(todo_content, encoding="utf-8")

    alert_items: list[dict] = []
    for item in todo_items:
        exec_info = match_todo_to_exec(item, exec_board)
        status = exec_info["status"] if exec_info else STATUS_UNASSIGNED
        if should_alert(item["id"], status, state, now):
            alert_items.append(item)
            mark_alerted(item["id"], status, state, now)

    save_state(state_file, state, now)

    msg = format_message(alert_items if alert_items else todo_items, exec_board, added_items, now, args.task)
    print(msg)


if __name__ == "__main__":
    main()

