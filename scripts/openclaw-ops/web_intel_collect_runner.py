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
import subprocess
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
from scrapling_runtime import fetch_with_scrapling_browser  # type: ignore

UTC = timezone.utc
LOG_MODES = {"silent", "chat"}
NOTIFY_ON_MODES = {"error", "change", "always"}
DEFAULT_SENDER_IDENTITY = "web-agent/web-intel-collect"
ANTI_BOT_KEYWORDS = (
    "captcha",
    "cloudflare",
    "verify you are human",
    "confirm you are human",
    "checking your browser",
    "access denied",
    "robot check",
    "bot detection",
    "just a moment",
    "security check",
    "turnstile",
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


def parse_json_output(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(raw):
        if ch != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(raw[idx:])
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    for candidate in reversed(lines):
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def policy_enforcer_path() -> Path:
    return POLICY_DIR / "policy_enforcer.py"


def invoke_policy_enforcer(db_path: Path, args: list[str], timeout: int = 30) -> tuple[bool, dict[str, Any], str]:
    script = policy_enforcer_path()
    if not script.exists():
        return False, {}, f"policy_enforcer_missing:{script}"
    cmd = [sys.executable, str(script), "--db", str(db_path), *args]
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=max(5, int(timeout)),
            check=False,
        )
    except Exception as exc:
        return False, {}, f"policy_enforcer_exec_failed:{exc}"

    payload = parse_json_output(proc.stdout or "")
    if proc.returncode != 0:
        err_text = (proc.stderr or "").strip() or str((payload or {}).get("error", "")) or f"exit={proc.returncode}"
        return False, payload or {}, f"policy_enforcer_failed:{err_text}"
    if not isinstance(payload, dict):
        return False, {}, "policy_enforcer_invalid_json_output"
    if not bool(payload.get("ok", False)):
        return False, payload, str(payload.get("error", "policy_enforcer_return_not_ok"))
    return True, payload, ""


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


def humanize_collect_error(error_text: str, status_code: int) -> tuple[str, str]:
    text = compact(error_text, 220)
    lower = text.lower()
    if lower.startswith("http_error:"):
        code = int(status_code or 0) or int((text.split(":", 1)[1] or "0").strip() or 0)
        return "HTTP 请求失败", f"目标站点返回状态码 {code}"
    if lower.startswith("http_request_failed:"):
        detail = text.split(":", 1)[1].strip()
        return "HTTP 请求异常", compact(detail or "网络请求失败", 180)
    if lower.startswith("playwright_unavailable:"):
        detail = text.split(":", 1)[1].strip()
        return "浏览器回退不可用", compact(detail or "Playwright 不可用", 180)
    if lower.startswith("selenium_unavailable:"):
        detail = text.split(":", 1)[1].strip()
        return "浏览器回退不可用", compact(detail or "Selenium 不可用", 180)
    if lower.startswith("browser_request_failed:"):
        detail = text.split(":", 1)[1].strip()
        return "浏览器回退失败", compact(detail or "浏览器获取页面失败", 180)
    if lower.startswith("browser_antibot_challenge") or lower.startswith("http_antibot_challenge"):
        return "目标站点触发反爬校验", "页面返回了 Cloudflare/验证码 等反爬挑战"
    if "just a moment" in lower or "captcha" in lower or "security check" in lower:
        return "目标站点触发反爬校验", "站点返回了反爬/人机验证页面"
    return "采集失败", text or "未提供详细信息"


def humanize_collect_error(error_text: str, status_code: int) -> tuple[str, str]:
    text = compact(error_text, 220)
    lower = text.lower()
    if lower.startswith("http_error:"):
        code = int(status_code or 0) or int((text.split(":", 1)[1] or "0").strip() or 0)
        return "HTTP 璇锋眰澶辫触", f"鐩爣绔欑偣杩斿洖鐘舵€佺爜 {code}"
    if lower.startswith("http_request_failed:"):
        detail = text.split(":", 1)[1].strip()
        return "HTTP 璇锋眰寮傚父", compact(detail or "缃戠粶璇锋眰澶辫触", 180)
    if lower.startswith(("playwright_unavailable:", "selenium_unavailable:", "scrapling_unavailable:")):
        detail = text.split(":", 1)[1].strip()
        return "娴忚鍣ㄥ洖閫€涓嶅彲鐢?", compact(detail or "娴忚鍣ㄥ紩鎿庝笉鍙敤", 180)
    if lower.startswith(("browser_request_failed:", "scrapling_browser_failed:", "scrapling_request_failed:")):
        detail = text.split(":", 1)[1].strip()
        return "娴忚鍣ㄥ洖閫€澶辫触", compact(detail or "娴忚鍣ㄨ幏鍙栭〉闈㈠け璐?", 180)
    if lower.startswith("browser_antibot_challenge") or lower.startswith("http_antibot_challenge"):
        return "鐩爣绔欑偣瑙﹀彂鍙嶇埇鏍￠獙", "椤甸潰杩斿洖浜� Cloudflare/captcha/turnstile 绛夊弽鐖寫鎴?"
    if "just a moment" in lower or "captcha" in lower or "security check" in lower:
        return "鐩爣绔欑偣瑙﹀彂鍙嶇埇鏍￠獙", "绔欑偣杩斿洖浜嗗弽鐖�/浜烘満楠岃瘉椤甸潰"
    return "閲囬泦澶辫触", text or "鏈彁渚涜缁嗕俊鎭?"


def humanize_collect_error(error_text: str, status_code: int) -> tuple[str, str]:
    text = compact(error_text, 220)
    lower = text.lower()
    if lower.startswith("http_error:"):
        code = int(status_code or 0) or int((text.split(":", 1)[1] or "0").strip() or 0)
        return "HTTP \u8bf7\u6c42\u5931\u8d25", f"\u76ee\u6807\u7ad9\u70b9\u8fd4\u56de\u72b6\u6001\u7801 {code}"
    if lower.startswith("http_request_failed:"):
        detail = text.split(":", 1)[1].strip()
        return "HTTP \u8bf7\u6c42\u5f02\u5e38", compact(detail or "\u7f51\u7edc\u8bf7\u6c42\u5931\u8d25", 180)
    if lower.startswith(("playwright_unavailable:", "selenium_unavailable:", "scrapling_unavailable:")):
        detail = text.split(":", 1)[1].strip()
        return (
            "\u6d4f\u89c8\u5668\u56de\u9000\u4e0d\u53ef\u7528",
            compact(detail or "Playwright/Selenium/Scrapling \u4e0d\u53ef\u7528", 180),
        )
    if lower.startswith(
        (
            "browser_request_failed:",
            "browser_fetch_failed:",
            "scrapling_browser_failed:",
            "scrapling_request_failed:",
        )
    ):
        detail = text.split(":", 1)[1].strip()
        return "\u6d4f\u89c8\u5668\u56de\u9000\u5931\u8d25", compact(detail or "\u6d4f\u89c8\u5668\u9875\u9762\u83b7\u53d6\u5931\u8d25", 180)
    if lower.startswith("browser_antibot_challenge") or lower.startswith("http_antibot_challenge"):
        return (
            "\u76ee\u6807\u7ad9\u70b9\u89e6\u53d1\u53cd\u722c\u6821\u9a8c",
            "\u9875\u9762\u8fd4\u56de\u4e86 Cloudflare/captcha/turnstile \u7b49\u53cd\u722c\u6311\u6218\u3002",
        )
    if "just a moment" in lower or "captcha" in lower or "security check" in lower:
        return "\u76ee\u6807\u7ad9\u70b9\u89e6\u53d1\u53cd\u722c\u6821\u9a8c", "\u7ad9\u70b9\u8fd4\u56de\u4e86\u53cd\u722c/\u4eba\u673a\u9a8c\u8bc1\u9875\u9762"
    return "\u91c7\u96c6\u5931\u8d25", text or "\u672a\u63d0\u4f9b\u8be6\u7ec6\u4fe1\u606f"


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


def fetch_with_playwright(url: str, timeout_seconds: int) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:
        return {
            "ok": False,
            "method": "browser-playwright",
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
                "method": "browser-playwright",
                "status": 200,
                "content_type": "text/html",
                "text": html,
                "truncated": False,
                "error": "",
            }
    except Exception as exc:
        return {
            "ok": False,
            "method": "browser-playwright",
            "status": 0,
            "content_type": "text/html",
            "text": "",
            "truncated": False,
            "error": f"browser_fetch_failed:{exc}",
        }


def fetch_with_scrapling(url: str, timeout_seconds: int) -> dict[str, Any]:
    return fetch_with_scrapling_browser(
        url,
        timeout_seconds=max(5, int(timeout_seconds)),
        engine="scrapling-stealth",
        disable_resources=True,
        headless=True,
    )


def fetch_with_selenium(url: str, timeout_seconds: int) -> dict[str, Any]:
    try:
        from selenium import webdriver  # type: ignore
        from selenium.webdriver.chrome.options import Options  # type: ignore
    except Exception as exc:
        return {
            "ok": False,
            "method": "browser-selenium",
            "status": 0,
            "content_type": "text/html",
            "text": "",
            "truncated": False,
            "error": f"selenium_unavailable:{exc}",
        }

    driver = None
    try:
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(max(5, int(timeout_seconds)))
        driver.get(url)
        html = str(driver.page_source or "")
        return {
            "ok": True,
            "method": "browser-selenium",
            "status": 200,
            "content_type": "text/html",
            "text": html,
            "truncated": False,
            "error": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "method": "browser-selenium",
            "status": 0,
            "content_type": "text/html",
            "text": "",
            "truncated": False,
            "error": f"browser_fetch_failed:{exc}",
        }
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def fetch_with_browser(url: str, timeout_seconds: int) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for fetcher in (fetch_with_playwright, fetch_with_selenium):
        result = fetcher(url, timeout_seconds)
        if bool(result.get("ok")) and not looks_like_antibot(result):
            return result
        if bool(result.get("ok")) and looks_like_antibot(result):
            result = dict(result)
            result["ok"] = False
            result["error"] = "browser_antibot_challenge"
        attempts.append(result)

    combined_error = "; ".join(
        dict.fromkeys(str(item.get("error", "")).strip() for item in attempts if str(item.get("error", "")).strip())
    ).strip()
    first = attempts[0] if attempts else {}
    return {
        "ok": False,
        "method": "browser",
        "status": int(first.get("status", 0) or 0),
        "content_type": str(first.get("content_type", "") or "text/html"),
        "text": str(first.get("text", "") or ""),
        "truncated": False,
        "error": combined_error or "browser_fetch_failed",
    }


def fetch_with_browser(url: str, timeout_seconds: int) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for fetcher in (fetch_with_scrapling, fetch_with_playwright, fetch_with_selenium):
        result = fetcher(url, timeout_seconds)
        if bool(result.get("ok")) and not looks_like_antibot(result):
            return result
        if bool(result.get("ok")) and looks_like_antibot(result):
            result = dict(result)
            result["ok"] = False
            result["error"] = "browser_antibot_challenge"
        attempts.append(result)

    combined_error = "; ".join(
        dict.fromkeys(str(item.get("error", "")).strip() for item in attempts if str(item.get("error", "")).strip())
    ).strip()
    first = attempts[0] if attempts else {}
    return {
        "ok": False,
        "method": "browser",
        "status": int(first.get("status", 0) or 0),
        "content_type": str(first.get("content_type", "") or "text/html"),
        "text": str(first.get("text", "") or ""),
        "truncated": False,
        "error": combined_error or "browser_fetch_failed",
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
    has_failures = bool(failed_items)
    lines = [
        "网页情报采集异常" if has_failures else "网页情报采集",
        f"- 任务: {task_id}",
        f"- 时间: {started_at}",
        f"- 汇总: 来源总数={total}，扫描={scanned}，变更={changed}，跳过={skipped}，失败={failed}",
        f"- 报告文件: {report_file}",
    ]
    if changed_ids:
        lines.append("- 发生变更:")
        for sid in changed_ids[:12]:
            lines.append(f"  - {sid}")
    if failed_items:
        lines.append("- 异常明细:")
        for item in failed_items[:8]:
            issue, detail = humanize_collect_error(
                str(item.get("error", "") or item.get("status", "failed")),
                int(item.get("status_code", 0) or 0),
            )
            lines.append(f"  - 来源: {item.get('id')}")
            lines.append(f"    问题: {issue}")
            lines.append(f"    详情: {detail}")
    return "\n".join(lines)


def build_failure_output(task_id: str, started_at: str, error_text: str) -> str:
    issue, detail = humanize_collect_error(error_text, 0)
    lines = [
        "网页情报采集异常",
        f"- 任务: {task_id}",
        f"- 时间: {started_at}",
        "- 问题: 采集器入口异常",
        f"- 详情: {issue}：{detail}",
    ]
    return "\n".join(lines)


def follow_up_lines(tasks: list[dict[str, Any]]) -> list[str]:
    if not tasks:
        return []
    lines = ["- 已派生修复任务:"]
    for item in tasks[:8]:
        task_id = str(item.get("task_id", "")).strip() or "-"
        assignee = str(item.get("assignee", "")).strip() or "-"
        status = str(item.get("status", "")).strip() or "created"
        lines.append(f"  - {task_id} -> {assignee} ({status})")
    return lines


def classify_collect_follow_up(item: dict[str, Any]) -> dict[str, str]:
    error_text = str(item.get("error", "") or "").strip().lower()
    if "playwright_unavailable:" in error_text or "selenium_unavailable:" in error_text:
        return {
            "kind": "browser-runtime-missing",
            "assignee": "ops-agent",
            "priority": "high",
            "pool": "jobs",
        }
    if (
        "http_error:403" in error_text
        or "http_antibot_challenge" in error_text
        or "browser_antibot_challenge" in error_text
        or "cloudflare" in error_text
        or "captcha" in error_text
    ):
        return {
            "kind": "anti-bot-blocked",
            "assignee": "ops-agent",
            "priority": "high",
            "pool": "jobs",
        }
    return {
        "kind": "fetch-failed",
        "assignee": "ops-agent",
        "priority": "medium",
        "pool": "todo",
    }


def create_collect_follow_up_tasks(
    *,
    db_path: Path,
    actor: str,
    report_file: Path,
    run_task_id: str,
    started_at: str,
    failed_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    created: list[dict[str, Any]] = []
    errors: list[str] = []
    day_token = started_at[:10].replace("-", "") or datetime.now(tz=UTC).strftime("%Y%m%d")
    for item in failed_items:
        sid = slugify(str(item.get("id", "")).strip(), "source")
        url = str(item.get("url", "")).strip()
        error_text = str(item.get("error", "")).strip() or "fetch_failed"
        status_code = int(item.get("status_code", 0) or 0)
        follow_up = classify_collect_follow_up(item)
        issue_key = sha256_text(f"{sid}|{follow_up['kind']}|{day_token}")[:10]
        task_id = f"todo-web-intel-collect-{sid}-{day_token}-{issue_key}"
        issue, detail = humanize_collect_error(error_text, status_code)

        requirement = "\n".join(
            [
                f"web-intel collect task: {run_task_id}",
                f"source_id: {sid}",
                f"url: {url}",
                f"first_seen_at: {started_at}",
                f"report_file: {report_file}",
                f"status_code: {status_code}",
                f"error: {error_text}",
                "",
                "需要闭环处理，而不是仅聊天告警：",
                "1. 复现 HTTP 抓取失败，并判断是否为 Cloudflare/验证码/403。",
                "2. 验证浏览器兜底运行环境是否可用（Playwright/Selenium/Chrome 驱动）。",
                "3. 若浏览器可用仍被拦截，给出最小修复方案：真实浏览器策略、可抓取的官方替代源，或明确的人工接管条件。",
                "4. 修复后重新执行 web_intel_collect_runner，确认该来源不再失败。",
            ]
        )
        acceptance = "至少完成一次复现、一次修复尝试、一次复验，并把证据写回任务。"
        context_payload = {
            "problem": f"{sid} collect failed: {issue}",
            "location": url or sid,
            "first_seen_at": started_at,
            "impact": issue,
            "evidence": f"{report_file}",
            "current_state": error_text,
            "expected_state": "目标来源可稳定采集，不再返回反爬挑战或运行时依赖错误。",
            "operation_path": f"web_intel_collect_runner::{sid}",
            "reproduction_steps": f"运行 {run_task_id} 或手动执行 web_intel_collect_runner 并观察 {sid} 的采集结果。",
            "scope": f"web-intel collect source={sid}",
            "constraints": "优先保持官方来源；若必须改为替代源，需要在任务中写明原因与验证结果。",
            "acceptance_criteria": acceptance,
            "full_background": requirement,
        }
        create_args = [
            "create-task",
            "--task-id",
            task_id,
            "--task-type",
            "web_intel_collect_repair",
            "--reason",
            f"[WEB_INTEL_COLLECT] {sid} {issue}",
            "--source",
            actor,
            "--request-source",
            "ai",
            "--priority",
            follow_up["priority"],
            "--risk-level",
            "low",
            "--pool",
            follow_up["pool"],
            "--assignee",
            follow_up["assignee"],
            "--need-human-confirm",
            "false",
            "--human-confirmed",
            "true",
            "--context-json",
            json.dumps(context_payload, ensure_ascii=False),
            "--requirement",
            requirement,
            "--result-output",
            "目标来源恢复可采集；若仍不可采集，任务中需留下已验证的阻断原因与替代方案。",
            "--acceptance",
            acceptance,
            "--observable-outputs",
            f"report_file={report_file},source_id={sid},url={url}",
            "--acceptance-thresholds",
            "修复后重跑 web-intel 任务，该来源 failed=0；或留下明确不可自动解决结论。",
            "--scheduled-at",
            now_iso(),
            "--actor",
            actor,
        ]
        ok, payload, err = invoke_policy_enforcer(db_path, create_args, timeout=35)
        if ok:
            created.append(
                {
                    "task_id": task_id,
                    "assignee": follow_up["assignee"],
                    "status": "created",
                    "source_id": sid,
                    "issue": issue,
                    "detail": detail,
                }
            )
            continue
        if "task_id already exists" in err:
            created.append(
                {
                    "task_id": task_id,
                    "assignee": follow_up["assignee"],
                    "status": "existing",
                    "source_id": sid,
                    "issue": issue,
                    "detail": detail,
                }
            )
            continue
        payload_error = str(payload.get("error", "")).strip() if isinstance(payload, dict) else ""
        errors.append(f"{sid}:{err or payload_error or 'create_follow_up_task_failed'}")
    return created, errors


def cli_flag_enabled(flag: str) -> bool:
    return str(flag or "").strip() in {str(part).strip() for part in sys.argv[1:]}


def cli_flag_value(flag: str, default: str = "") -> str:
    parts = sys.argv[1:]
    for idx, part in enumerate(parts):
        if part == flag and idx + 1 < len(parts):
            return str(parts[idx + 1]).strip()
        if part.startswith(flag + "="):
            return str(part.split("=", 1)[1]).strip()
    return default


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
    parser.add_argument("--db", default="")
    parser.add_argument("--task-id", default="cron:web-intel-collect")
    parser.add_argument("--sender-identity", default=DEFAULT_SENDER_IDENTITY)
    parser.add_argument("--min-interval-minutes", type=int, default=60)
    parser.add_argument("--max-sources", type=int, default=24)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--browser-timeout-seconds", type=int, default=40)
    parser.add_argument("--max-bytes", type=int, default=240000)
    parser.add_argument("--allow-browser-fallback", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--create-follow-up-tasks", action=argparse.BooleanOptionalAction, default=True)
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
    db_path = Path(args.db).expanduser() if str(args.db).strip() else (ops_home / "task-center" / "task_center.db")
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
        http_antibot = looks_like_antibot(fetched)
        should_try_browser = use_browser and (
            http_antibot or ((not bool(fetched.get("ok"))) and (http_antibot or not fetched.get("text")))
        )
        if should_try_browser:
            browser_fetched = fetch_with_browser(url, int(args.browser_timeout_seconds))
            if bool(browser_fetched.get("ok")) and not looks_like_antibot(browser_fetched):
                fetched = browser_fetched
            else:
                combined_errors: list[str] = []
                if http_antibot:
                    combined_errors.append("http_antibot_challenge")
                elif not bool(fetched.get("ok")):
                    combined_errors.append(str(fetched.get("error", "")).strip())
                browser_error = str(browser_fetched.get("error", "")).strip()
                if browser_error:
                    combined_errors.append(browser_error)
                fetched = dict(fetched)
                fetched["ok"] = False
                fetched["error"] = "; ".join(x for x in combined_errors if x).strip("; ") or "fetch_failed"

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

    report_file = report_dir / f"web_collect_{datetime.now(tz=UTC).strftime('%Y%m%d_%H%M%S')}.json"
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
    save_json(report_file, report_payload)
    follow_up_tasks: list[dict[str, Any]] = []
    follow_up_errors: list[str] = []
    if bool(args.create_follow_up_tasks) and failed_items:
        follow_up_tasks, follow_up_errors = create_collect_follow_up_tasks(
            db_path=db_path,
            actor=sender_identity,
            report_file=report_file,
            run_task_id=str(args.task_id),
            started_at=started_at,
            failed_items=failed_items,
        )
        for item in failed_items:
            sid = str(item.get("id", "")).strip()
            task_row = next((x for x in follow_up_tasks if str(x.get("source_id", "")).strip() == sid), None)
            if task_row:
                item["follow_up_task_id"] = str(task_row.get("task_id", "")).strip()
                item["follow_up_status"] = str(task_row.get("status", "")).strip()
        report_payload["follow_up_tasks"] = follow_up_tasks
        report_payload["follow_up_errors"] = follow_up_errors
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
    extra_lines = follow_up_lines(follow_up_tasks)
    if follow_up_errors:
        extra_lines.append("- 建单失败:")
        for item in follow_up_errors[:8]:
            extra_lines.append(f"  - {item}")
    if extra_lines:
        final_output = final_output + "\n" + "\n".join(extra_lines)
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
        "follow_up_tasks": follow_up_tasks,
        "follow_up_errors": follow_up_errors,
    }

    if bool(args.emit_json):
        print(json.dumps(response_payload, ensure_ascii=False))
    else:
        print(output_text)


def run_cli() -> int:
    try:
        main()
        return 0
    except Exception as exc:
        task_id = cli_flag_value("--task-id", "cron:web-intel-collect") or "cron:web-intel-collect"
        output = build_failure_output(task_id, now_iso(), str(exc))
        payload = {
            "ok": False,
            "notify": True,
            "output": output,
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }
        if cli_flag_enabled("--emit-json"):
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(output)
        return 1


if __name__ == "__main__":
    raise SystemExit(run_cli())
