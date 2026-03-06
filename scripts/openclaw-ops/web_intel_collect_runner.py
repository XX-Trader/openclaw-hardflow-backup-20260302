#!/usr/bin/env python3
"""Web intelligence collector for web-agent.

Design goals:
1) API/HTTP first, browser fallback when needed.
2) Store evidence under ~/.openclaw/web/{raw,parsed,summary}.
3) Output concise cron-friendly summary; quiet mode supports NO_REPLY.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
POLICY_DIR = ROOT / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from io_write_gateway import FileWriteError, atomic_write_text, write_json_atomic  # type: ignore

UTC = timezone.utc
LOG_MODES = {"silent", "chat"}
NOTIFY_ON_MODES = {"error", "change", "always"}
DEFAULT_SENDER_IDENTITY = "web-agent/web-intel-collect"
ANTI_BOT_KEYWORDS = (
    "captcha",
    "cloudflare",
    "verify you are human",
    "access denied",
    "robot check",
    "bot detection",
    "just a moment",
    "security check",
)


def now() -> datetime:
    return datetime.now(tz=UTC)


def now_iso() -> str:
    return now().replace(microsecond=0).isoformat()


def should_quiet(log_mode: str, notify_on: str, failed_count: int, changed_count: int) -> bool:
    if str(log_mode or "").strip().lower() != "silent":
        return False
    mode = str(notify_on or "change").strip().lower()
    if mode == "always":
        return False
    if mode == "error":
        return int(failed_count) <= 0
    return int(failed_count) <= 0 and int(changed_count) <= 0


def parse_iso(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else default


def normalize_sender_identity(value: str, default: str = DEFAULT_SENDER_IDENTITY) -> str:
    sender = str(value or "").strip()
    return sender or default


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    try:
        write_json_atomic(
            path,
            payload,
            ensure_ascii=False,
            indent=2,
            file_mode=0o640,
            dir_mode=0o750,
        )
    except FileWriteError as exc:
        raise RuntimeError(f"save_json_failed:{exc.code}:{path}:{exc.detail or exc}") from exc


def save_text(path: Path, content: str) -> None:
    try:
        atomic_write_text(
            path,
            str(content or ""),
            encoding="utf-8",
            file_mode=0o640,
            dir_mode=0o750,
        )
    except FileWriteError as exc:
        raise RuntimeError(f"save_text_failed:{exc.code}:{path}:{exc.detail or exc}") from exc


def slugify(text: str, default: str) -> str:
    raw = str(text or "").strip().lower()
    slug = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-")
    return slug or default


def compact(text: str, max_len: int = 180) -> str:
    one_line = " ".join(str(text or "").split())
    if len(one_line) <= max_len:
        return one_line
    return one_line[: max_len - 3].rstrip() + "..."


def parse_charset(content_type: str) -> str:
    raw = str(content_type or "").lower()
    marker = "charset="
    idx = raw.find(marker)
    if idx < 0:
        return "utf-8"
    charset = raw[idx + len(marker) :].split(";")[0].strip()
    return charset or "utf-8"


def fetch_with_http(url: str, timeout_seconds: int, max_bytes: int) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "openclaw-web-intel/1.0",
            "Accept": "*/*",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=max(5, int(timeout_seconds))) as resp:
            raw = resp.read(max(1024, int(max_bytes)) + 1)
            truncated = len(raw) > int(max_bytes)
            if truncated:
                raw = raw[: int(max_bytes)]
            content_type = str(resp.headers.get("Content-Type", "")).strip()
            charset = parse_charset(content_type)
            text = raw.decode(charset, errors="replace")
            return {
                "ok": True,
                "method": "http",
                "status": int(getattr(resp, "status", 200)),
                "content_type": content_type,
                "text": text,
                "truncated": bool(truncated),
                "error": "",
            }
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read(max(1024, int(max_bytes))).decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return {
            "ok": False,
            "method": "http",
            "status": int(getattr(exc, "code", 0) or 0),
            "content_type": "",
            "text": body,
            "truncated": False,
            "error": f"http_error:{getattr(exc, 'code', 'unknown')}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "method": "http",
            "status": 0,
            "content_type": "",
            "text": "",
            "truncated": False,
            "error": f"http_request_failed:{exc}",
        }


def fetch_with_browser(url: str, timeout_seconds: int) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:
        return {
            "ok": False,
            "method": "browser",
            "status": 0,
            "content_type": "text/html",
            "text": "",
            "truncated": False,
            "error": f"playwright_unavailable:{exc}",
        }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=max(5000, int(timeout_seconds) * 1000))
            html = page.content()
            browser.close()
            return {
                "ok": True,
                "method": "browser",
                "status": 200,
                "content_type": "text/html",
                "text": html,
                "truncated": False,
                "error": "",
            }
    except Exception as exc:
        return {
            "ok": False,
            "method": "browser",
            "status": 0,
            "content_type": "text/html",
            "text": "",
            "truncated": False,
            "error": f"browser_fetch_failed:{exc}",
        }


def looks_like_antibot(result: dict[str, Any]) -> bool:
    status = int(result.get("status", 0) or 0)
    text = str(result.get("text", "")).lower()
    if status in {403, 429, 503}:
        return True
    return any(keyword in text for keyword in ANTI_BOT_KEYWORDS)


def html_to_text(content: str) -> str:
    text = str(content or "")
    if "<" not in text and ">" not in text:
        return " ".join(text.split())
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_title(content: str, fallback: str) -> str:
    raw = str(content or "")
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    if m:
        return compact(html_to_text(m.group(1)), 120) or fallback
    return fallback


def sha256_text(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8", errors="replace")).hexdigest()


def state_default() -> dict[str, Any]:
    return {
        "schema_version": "2026-03-06",
        "updated_at": "",
        "last_run_at": "",
        "last_report_file": "",
        "sources": {},
    }


def load_sources(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path, {})
    if not isinstance(payload, dict):
        return []
    data = payload.get("sources")
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        if not url:
            continue
        sid = slugify(str(item.get("id", "")).strip(), default=f"source-{idx+1}")
        enabled = bool(item.get("enabled", True))
        category = str(item.get("category", "")).strip()
        tags_raw = item.get("tags")
        tags = [str(x).strip() for x in tags_raw] if isinstance(tags_raw, list) else []
        tags = [x for x in tags if x]
        out.append(
            {
                "id": sid,
                "url": url,
                "enabled": enabled,
                "category": category,
                "tags": tags,
                "browser_fallback": bool(item.get("browser_fallback", True)),
                "min_interval_minutes": max(1, int(item.get("min_interval_minutes", 60))),
            }
        )
    return out


def should_skip_by_interval(last_attempt_at: str, min_interval_minutes: int, force: bool) -> bool:
    if force:
        return False
    dt = parse_iso(last_attempt_at)
    if dt is None:
        return False
    return (now() - dt) < timedelta(minutes=max(1, int(min_interval_minutes)))


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def build_output(
    *,
    sender_identity: str,
    task_id: str,
    started_at: str,
    total: int,
    scanned: int,
    changed: int,
    skipped: int,
    failed: int,
    report_file: Path,
    changed_ids: list[str],
    failed_items: list[dict[str, Any]],
) -> str:
    lines = [
        "web-intel-collect",
        f"- sender_identity: {sender_identity}",
        f"- task: {task_id}",
        f"- time: {started_at}",
        f"- sources_total: {total}",
        f"- scanned: {scanned}",
        f"- changed_count: {changed}",
        f"- skipped_count: {skipped}",
        f"- failed_count: {failed}",
        f"- evidence: {report_file}",
    ]
    if changed_ids:
        lines.append("- changed_sources:")
        for sid in changed_ids[:12]:
            lines.append(f"  - {sid}")
    if failed_items:
        lines.append("- failed_sources:")
        for item in failed_items[:8]:
            lines.append(
                f"  - {item.get('id')}: {compact(str(item.get('error', '') or item.get('status', 'failed')), 140)}"
            )
    return "\n".join(lines)


def main() -> None:
    home = Path(os.path.expanduser("~")).resolve()
    parser = argparse.ArgumentParser(description="Collect internet intelligence for web-agent")
    parser.add_argument("--openclaw-home", default=str(home / ".openclaw"))
    parser.add_argument("--sources-file", default="")
    parser.add_argument("--state-file", default="")
    parser.add_argument("--report-dir", default="")
    parser.add_argument("--raw-dir", default="")
    parser.add_argument("--parsed-dir", default="")
    parser.add_argument("--summary-dir", default="")
    parser.add_argument("--task-id", default="cron:web-intel-collect")
    parser.add_argument("--sender-identity", default=DEFAULT_SENDER_IDENTITY)
    parser.add_argument("--min-interval-minutes", type=int, default=60)
    parser.add_argument("--max-sources", type=int, default=24)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--browser-timeout-seconds", type=int, default=40)
    parser.add_argument("--max-bytes", type=int, default=240000)
    parser.add_argument("--allow-browser-fallback", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--normal-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--notify-on", default="change", choices=sorted(NOTIFY_ON_MODES))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    openclaw_home = Path(args.openclaw_home).expanduser().resolve()
    ops_home = openclaw_home / "ops"
    web_home = openclaw_home / "web"
    sources_file = (
        Path(args.sources_file).expanduser()
        if str(args.sources_file).strip()
        else (ops_home / "web" / "sources.json")
    )
    state_file = (
        Path(args.state_file).expanduser()
        if str(args.state_file).strip()
        else (ops_home / "web-intel" / "state.json")
    )
    report_dir = (
        Path(args.report_dir).expanduser()
        if str(args.report_dir).strip()
        else (ops_home / "web-intel" / "reports")
    )
    raw_dir = Path(args.raw_dir).expanduser() if str(args.raw_dir).strip() else (web_home / "raw")
    parsed_dir = Path(args.parsed_dir).expanduser() if str(args.parsed_dir).strip() else (web_home / "parsed")
    summary_dir = Path(args.summary_dir).expanduser() if str(args.summary_dir).strip() else (web_home / "summary")

    for p in (report_dir, raw_dir, parsed_dir, summary_dir, state_file.parent):
        ensure_dir(p)

    sender_identity = normalize_sender_identity(args.sender_identity)
    log_mode = normalize_log_mode(args.normal_log_mode)
    started_at = now_iso()

    state = load_json(state_file, state_default())
    if not isinstance(state, dict):
        state = state_default()
    source_state = state.get("sources")
    if not isinstance(source_state, dict):
        source_state = {}
        state["sources"] = source_state

    sources = load_sources(sources_file)
    if int(args.max_sources) > 0:
        sources = sources[: int(args.max_sources)]

    results: list[dict[str, Any]] = []
    changed_ids: list[str] = []
    failed_items: list[dict[str, Any]] = []
    skipped_count = 0
    scanned_count = 0

    for source in sources:
        sid = str(source.get("id", "")).strip()
        if not bool(source.get("enabled", True)):
            skipped_count += 1
            results.append({"id": sid, "status": "skipped", "reason": "disabled"})
            continue

        item_state = source_state.get(sid) if isinstance(source_state.get(sid), dict) else {}
        if should_skip_by_interval(
            str(item_state.get("last_attempt_at", "")),
            int(source.get("min_interval_minutes", args.min_interval_minutes)),
            bool(args.force),
        ):
            skipped_count += 1
            results.append({"id": sid, "status": "skipped", "reason": "min_interval"})
            continue

        scanned_count += 1
        url = str(source.get("url", "")).strip()
        fetched = fetch_with_http(url, int(args.timeout_seconds), int(args.max_bytes))
        use_browser = bool(args.allow_browser_fallback) and bool(source.get("browser_fallback", True))
        if use_browser and (not bool(fetched.get("ok"))) and (looks_like_antibot(fetched) or not fetched.get("text")):
            browser_fetched = fetch_with_browser(url, int(args.browser_timeout_seconds))
            if bool(browser_fetched.get("ok")):
                fetched = browser_fetched
            else:
                fetched["error"] = (
                    str(fetched.get("error", "")).strip() + "; " + str(browser_fetched.get("error", "")).strip()
                ).strip("; ")

        now_mark = now_iso()
        item_state = dict(item_state)
        item_state["last_attempt_at"] = now_mark
        item_state["runs"] = int(item_state.get("runs", 0) or 0) + 1

        if not bool(fetched.get("ok")):
            error_text = compact(str(fetched.get("error", "")).strip() or "fetch_failed", 300)
            item_state["last_error"] = error_text
            source_state[sid] = item_state
            failed_row = {
                "id": sid,
                "url": url,
                "status": "failed",
                "method": str(fetched.get("method", "")),
                "error": error_text,
                "status_code": int(fetched.get("status", 0) or 0),
            }
            failed_items.append(failed_row)
            results.append(failed_row)
            continue

        raw_text = str(fetched.get("text", ""))
        plain_text = html_to_text(raw_text)
        fingerprint = sha256_text(plain_text)
        previous_fingerprint = str(item_state.get("fingerprint", ""))
        changed = fingerprint != previous_fingerprint
        title = extract_title(raw_text, sid)
        method = str(fetched.get("method", "http"))

        source_raw_dir = raw_dir / sid
        ensure_dir(source_raw_dir)
        raw_file = source_raw_dir / f"{datetime.now(tz=UTC).strftime('%Y%m%d_%H%M%S')}_{method}.txt"
        save_text(raw_file, raw_text)

        parsed_payload = {
            "schema_version": "2026-03-06",
            "id": sid,
            "url": url,
            "title": title,
            "category": str(source.get("category", "")),
            "tags": list(source.get("tags") or []),
            "fetched_at": now_mark,
            "method": method,
            "status_code": int(fetched.get("status", 200) or 200),
            "truncated": bool(fetched.get("truncated", False)),
            "fingerprint": fingerprint,
            "text_excerpt": plain_text[:4000],
            "raw_file": str(raw_file),
            "changed": bool(changed),
        }
        parsed_file = parsed_dir / f"{sid}.json"
        save_json(parsed_file, parsed_payload)

        summary_file = summary_dir / f"{sid}.md"
        summary_text = "\n".join(
            [
                f"# {title}",
                "",
                f"- source_id: {sid}",
                f"- url: {url}",
                f"- fetched_at: {now_mark}",
                f"- method: {method}",
                f"- status_code: {int(fetched.get('status', 200) or 200)}",
                f"- changed: {str(bool(changed)).lower()}",
                f"- parsed_file: {parsed_file}",
                f"- raw_file: {raw_file}",
                "",
                "## Excerpt",
                "",
                plain_text[:2000] or "(empty)",
            ]
        )
        save_text(summary_file, summary_text)

        item_state["last_success_at"] = now_mark
        item_state["last_error"] = ""
        item_state["fingerprint"] = fingerprint
        item_state["last_method"] = method
        item_state["last_raw_file"] = str(raw_file)
        item_state["last_parsed_file"] = str(parsed_file)
        source_state[sid] = item_state

        if changed:
            changed_ids.append(sid)

        results.append(
            {
                "id": sid,
                "url": url,
                "status": "ok",
                "changed": bool(changed),
                "method": method,
                "status_code": int(fetched.get("status", 200) or 200),
                "parsed_file": str(parsed_file),
                "raw_file": str(raw_file),
            }
        )

    state["schema_version"] = "2026-03-06"
    state["updated_at"] = now_iso()
    state["last_run_at"] = started_at

    report_payload: dict[str, Any] = {
        "ok": True,
        "task": str(args.task_id),
        "sender_identity": sender_identity,
        "generated_at": now_iso(),
        "sources_file": str(sources_file),
        "counts": {
            "sources_total": len(sources),
            "scanned": scanned_count,
            "changed": len(changed_ids),
            "skipped": skipped_count,
            "failed": len(failed_items),
        },
        "results": results,
    }
    report_file = report_dir / f"web_collect_{datetime.now(tz=UTC).strftime('%Y%m%d_%H%M%S')}.json"
    save_json(report_file, report_payload)
    state["last_report_file"] = str(report_file)
    save_json(state_file, state)

    latest_summary_file = summary_dir / "latest_collect.md"
    final_output = build_output(
        sender_identity=sender_identity,
        task_id=str(args.task_id),
        started_at=started_at,
        total=len(sources),
        scanned=scanned_count,
        changed=len(changed_ids),
        skipped=skipped_count,
        failed=len(failed_items),
        report_file=report_file,
        changed_ids=changed_ids,
        failed_items=failed_items,
    )
    save_text(latest_summary_file, final_output + "\n")

    quiet_no_reply = should_quiet(
        log_mode,
        str(args.notify_on),
        failed_count=len(failed_items),
        changed_count=len(changed_ids),
    )
    output_text = "NO_REPLY" if quiet_no_reply else final_output
    response_payload = {
        "ok": True,
        "notify": (not quiet_no_reply),
        "output": output_text,
        "report_file": str(report_file),
        "state_file": str(state_file),
        "latest_summary_file": str(latest_summary_file),
    }

    if bool(args.emit_json):
        print(json.dumps(response_payload, ensure_ascii=False))
    else:
        print(output_text)


if __name__ == "__main__":
    main()
