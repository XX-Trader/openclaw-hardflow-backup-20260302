#!/usr/bin/env python3
"""API contract and freshness audit (single-pass, no retry loop)."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TZ = timezone(timedelta(hours=8))
LOG_MODES = {"silent", "chat"}
ENGINES = {"http", "playwright", "playwright-real", "selenium"}
DEFAULT_SENDER_IDENTITY = "ops-agent/api-test-audit"
DEFAULT_FRESHNESS_CANDIDATES = [
    "timestamp",
    "ts",
    "time",
    "updated_at",
    "update_time",
    "server_time",
    "data.timestamp",
    "data.ts",
    "data.updated_at",
    "meta.timestamp",
    "meta.ts",
]


def now() -> datetime:
    return datetime.now(TZ)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else default


def parse_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "y", "on"}


def normalize_engine(value: str, default: str = "http") -> str:
    engine = str(value or "").strip().lower()
    return engine if engine in ENGINES else default


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_config() -> dict[str, Any]:
    return {
        "schema_version": "2026-03-02",
        "engine": "playwright-real",
        "endpoint_engine": "http",
        "forbid_http_engine": True,
        "require_browser_checks": True,
        "real_browser": {
            "user_data_dir": os.environ.get("OPENCLAW_CHROME_USER_DATA_DIR", ""),
            "profile_directory": os.environ.get("OPENCLAW_CHROME_PROFILE", "Default"),
            "channel": os.environ.get("OPENCLAW_CHROME_CHANNEL", ""),
            "headless": False,
        },
        "default_timeout_seconds": 12,
        "base_headers": {},
        "freshness_default_max_age_seconds": 300,
        "freshness_auto_detect": True,
        "freshness_candidate_fields": list(DEFAULT_FRESHNESS_CANDIDATES),
        "endpoints": [
            {
                "id": "example-market",
                "method": "GET",
                "url": "https://example.com/api/market",
                "expect_json": True,
                "require_non_empty": True,
                "freshness_field": "data.ts",
                "freshness_max_age_seconds": 60,
                "freshness_required": True,
                "required_fields": ["code", "data"],
            }
        ],
        "browser_checks": [
            {
                "id": "example-dashboard",
                "url": "https://example.com/dashboard",
                "expect_text": "Dashboard",
                "expect_selectors": ["body"],
                "min_score": 80,
                "steps": [
                    {"action": "wait_for", "selector": "body"},
                    {"action": "click", "selector": "text=Login"},
                    {"action": "wait_for", "selector": "text=Dashboard"},
                ],
                "api_expectations": [
                    {
                        "id": "core-data-api",
                        "url_contains": "/api/",
                        "method": "GET",
                        "min_hits": 1,
                        "require_2xx": True,
                        "require_output": True,
                    }
                ],
            }
        ],
    }


def default_state() -> dict[str, Any]:
    return {
        "updated_at": "",
        "runs": 0,
        "issues": {},
        "last_run_file": "",
    }


def extract_by_path(payload: Any, dotted_path: str) -> Any:
    cur = payload
    for token in (dotted_path or "").split("."):
        token = token.strip()
        if not token:
            continue
        if isinstance(cur, dict):
            if token not in cur:
                return None
            cur = cur[token]
            continue
        if isinstance(cur, list):
            if not token.isdigit():
                return None
            idx = int(token)
            if idx < 0 or idx >= len(cur):
                return None
            cur = cur[idx]
            continue
        return None
    return cur


def is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (str, bytes)):
        return len(str(value).strip()) == 0
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        num = float(value)
        if num > 1e12:
            num = num / 1000.0
        try:
            return datetime.fromtimestamp(num, tz=timezone.utc).astimezone(TZ)
        except Exception:
            return None

    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{10,13}", text):
        return parse_dt(float(text))

    candidates = [text, text.replace("Z", "+00:00"), text.replace("/", "-")]
    for c in candidates:
        try:
            dt = datetime.fromisoformat(c)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)
            return dt.astimezone(TZ)
        except Exception:
            continue

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=TZ)
        except Exception:
            continue
    return None


def http_call(method: str, url: str, headers: dict[str, str], body: str, timeout_seconds: int) -> tuple[int, str, str]:
    data = body.encode("utf-8") if body else None
    req = urllib.request.Request(url=url, method=method.upper(), data=data)
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=max(1, int(timeout_seconds))) as resp:
            raw = resp.read()
            status = int(getattr(resp, "status", 200))
            content_type = str(resp.headers.get("Content-Type", ""))
            return status, content_type, raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        return int(exc.code or 0), "", payload
    except Exception as exc:
        return 0, "", str(exc)


def playwright_call(method: str, url: str, headers: dict[str, str], body: str, timeout_seconds: int) -> tuple[int, str, str]:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:
        return 0, "", f"playwright_not_available:{exc}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(ignore_https_errors=True)
            try:
                resp = context.request.fetch(
                    url,
                    method=method.upper(),
                    headers=headers,
                    data=body.encode("utf-8") if body else None,
                    timeout=max(1000, int(timeout_seconds) * 1000),
                )
                status = int(resp.status)
                ctype = str(resp.headers.get("content-type", ""))
                text = resp.text()
                return status, ctype, text
            finally:
                context.close()
                browser.close()
    except Exception as exc:
        return 0, "", str(exc)


def apply_playwright_steps(page: Any, steps: list[dict[str, Any]], timeout_seconds: int) -> tuple[bool, str]:
    timeout_ms = max(1000, int(timeout_seconds) * 1000)
    for idx, step in enumerate(steps, start=1):
        action = str(step.get("action", "")).strip().lower()
        selector = str(step.get("selector", "")).strip()
        value = str(step.get("value", "") or "")
        key = str(step.get("key", "") or "")
        if not action:
            continue
        try:
            if action in {"goto", "navigate"}:
                target = str(step.get("url", "")).strip()
                if not target:
                    return False, f"step_{idx}_missing_url"
                page.goto(target, wait_until="domcontentloaded", timeout=timeout_ms)
            elif action == "click":
                if not selector:
                    return False, f"step_{idx}_missing_selector"
                page.locator(selector).first.click(timeout=timeout_ms)
            elif action == "fill":
                if not selector:
                    return False, f"step_{idx}_missing_selector"
                page.locator(selector).first.fill(value, timeout=timeout_ms)
            elif action == "press":
                if not selector or not key:
                    return False, f"step_{idx}_missing_selector_or_key"
                page.locator(selector).first.press(key, timeout=timeout_ms)
            elif action in {"wait_for", "wait-visible"}:
                if not selector:
                    return False, f"step_{idx}_missing_selector"
                page.locator(selector).first.wait_for(state="visible", timeout=timeout_ms)
            elif action == "wait_network_idle":
                page.wait_for_load_state("networkidle", timeout=timeout_ms)
            elif action == "sleep":
                ms = int(step.get("ms", 500) or 500)
                page.wait_for_timeout(max(1, ms))
            else:
                return False, f"step_{idx}_unsupported_action:{action}"
        except Exception as exc:
            return False, f"step_{idx}_{action}_failed:{exc}"
    return True, "ok"


def match_api_expectation(entry: dict[str, Any], rule: dict[str, Any]) -> bool:
    url = str(entry.get("url", "")).strip()
    method = str(entry.get("method", "")).upper()
    url_contains = str(rule.get("url_contains", "")).strip()
    url_regex = str(rule.get("url_regex", "")).strip()
    expect_method = str(rule.get("method", "")).strip().upper()
    if url_contains and url_contains not in url:
        return False
    if url_regex:
        try:
            if not re.search(url_regex, url):
                return False
        except re.error:
            return False
    if expect_method and method != expect_method:
        return False
    return True


def evaluate_api_expectations(
    api_records: list[dict[str, Any]],
    api_expectations: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    failures: list[str] = []
    reports: list[dict[str, Any]] = []
    for idx, rule in enumerate(api_expectations, start=1):
        rid = str(rule.get("id", "")).strip() or f"rule-{idx}"
        matched = [r for r in api_records if match_api_expectation(r, rule)]
        min_hits = max(1, int(rule.get("min_hits", 1) or 1))
        require_2xx = parse_bool(rule.get("require_2xx"), True)
        require_output = parse_bool(rule.get("require_output"), True)
        required_fields_raw = rule.get("required_fields")
        required_fields = [str(x).strip() for x in required_fields_raw if str(x).strip()] if isinstance(required_fields_raw, list) else []

        report = {
            "id": rid,
            "matched_count": len(matched),
            "min_hits": min_hits,
            "require_2xx": require_2xx,
            "require_output": require_output,
            "required_fields": required_fields,
            "status": "ok",
            "reasons": [],
        }

        if len(matched) < min_hits:
            report["status"] = "failed"
            report["reasons"].append(f"api_no_output:{len(matched)}<{min_hits}")
            failures.append(f"api_no_output:{rid}")
            reports.append(report)
            continue

        if require_2xx and any(not (200 <= int(row.get("status", 0)) < 300) for row in matched):
            report["status"] = "failed"
            report["reasons"].append("api_non_2xx")
            failures.append(f"api_non_2xx:{rid}")

        if require_output:
            has_non_empty = any(not is_empty_value(row.get("response_body", "")) for row in matched)
            if not has_non_empty:
                report["status"] = "failed"
                report["reasons"].append("api_empty_output")
                failures.append(f"api_empty_output:{rid}")

        if required_fields:
            ok_fields = False
            for row in matched:
                payload = row.get("response_json")
                if payload is None:
                    continue
                miss = [field for field in required_fields if extract_by_path(payload, field) is None]
                if not miss:
                    ok_fields = True
                    break
            if not ok_fields:
                report["status"] = "failed"
                report["reasons"].append("api_required_fields_missing")
                failures.append(f"api_required_fields_missing:{rid}")

        reports.append(report)
    return failures, reports


def run_browser_check_playwright(
    url: str,
    expect_text: str,
    timeout_seconds: int,
    *,
    steps: list[dict[str, Any]] | None = None,
    expect_selectors: list[str] | None = None,
    screenshot_file: str = "",
    devtools_file: str = "",
    real_browser: dict[str, Any] | None = None,
) -> tuple[bool, str, str, dict[str, Any]]:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:
        return False, f"playwright_not_available:{exc}", "", {}

    steps = [x for x in (steps or []) if isinstance(x, dict)]
    expected_selectors = [str(x).strip() for x in (expect_selectors or []) if str(x).strip()]
    timeout_ms = max(1000, int(timeout_seconds) * 1000)
    screenshot_path = str(Path(screenshot_file).expanduser()) if screenshot_file else ""
    devtools_path = str(Path(devtools_file).expanduser()) if devtools_file else ""
    try:
        with sync_playwright() as p:
            browser = None
            context = None
            try:
                real_cfg = real_browser if isinstance(real_browser, dict) else {}
                if real_cfg:
                    user_data_dir = str(real_cfg.get("user_data_dir", "")).strip()
                    if not user_data_dir:
                        return False, "missing_real_browser_user_data_dir", "", {}
                    profile_directory = str(real_cfg.get("profile_directory", "Default")).strip()
                    channel = str(real_cfg.get("channel", "chrome")).strip() or None
                    headless = parse_bool(real_cfg.get("headless"), False)
                    launch_args: list[str] = []
                    if profile_directory:
                        launch_args.append(f"--profile-directory={profile_directory}")
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=user_data_dir,
                        channel=channel,
                        headless=headless,
                        ignore_https_errors=True,
                        args=launch_args,
                    )
                else:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(ignore_https_errors=True)

                page = context.pages[0] if context.pages else context.new_page()
                console_rows: list[dict[str, str]] = []
                request_failed_rows: list[dict[str, str]] = []
                api_records: list[dict[str, Any]] = []

                def on_console(msg: Any) -> None:
                    level = str(msg.type or "").strip()
                    text = str(msg.text or "").strip()
                    if not text:
                        return
                    console_rows.append({"level": level, "text": text[:500]})

                def on_request_failed(req: Any) -> None:
                    fail_text = ""
                    if req.failure:
                        fail_text = str(req.failure or "")
                    request_failed_rows.append(
                        {
                            "url": str(req.url or ""),
                            "method": str(req.method or ""),
                            "resource_type": str(req.resource_type or ""),
                            "failure": fail_text[:400],
                        }
                    )

                def on_response(resp: Any) -> None:
                    req = resp.request
                    resource_type = str(getattr(req, "resource_type", "") or "")
                    if resource_type not in {"xhr", "fetch"}:
                        return
                    row: dict[str, Any] = {
                        "url": str(resp.url or ""),
                        "status": int(resp.status or 0),
                        "method": str(getattr(req, "method", "") or "").upper(),
                        "resource_type": resource_type,
                    }
                    body = ""
                    body_json: Any = None
                    try:
                        body = resp.text() or ""
                        row["response_bytes"] = len(body.encode("utf-8", errors="ignore"))
                    except Exception:
                        body = ""
                    if body:
                        row["response_body"] = body[:3000]
                        try:
                            body_json = json.loads(body)
                        except Exception:
                            body_json = None
                    if body_json is not None:
                        row["response_json"] = body_json
                    api_records.append(row)

                page.on("console", on_console)
                page.on("requestfailed", on_request_failed)
                page.on("response", on_response)
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                ok_steps, note_steps = apply_playwright_steps(page, steps, timeout_seconds)
                if not ok_steps:
                    if screenshot_path:
                        Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=screenshot_path, full_page=True)
                    details = {
                        "console": console_rows,
                        "request_failed": request_failed_rows,
                        "api_records": api_records,
                    }
                    if devtools_path:
                        Path(devtools_path).parent.mkdir(parents=True, exist_ok=True)
                        save_json(Path(devtools_path), details)
                    return False, note_steps, screenshot_path, details
                if expect_text:
                    text = page.content()
                    if expect_text not in text:
                        if screenshot_path:
                            Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                            page.screenshot(path=screenshot_path, full_page=True)
                        details = {
                            "console": console_rows,
                            "request_failed": request_failed_rows,
                            "api_records": api_records,
                        }
                        if devtools_path:
                            Path(devtools_path).parent.mkdir(parents=True, exist_ok=True)
                            save_json(Path(devtools_path), details)
                        return False, "expect_text_missing", screenshot_path, details
                for sel in expected_selectors:
                    try:
                        page.locator(sel).first.wait_for(state="visible", timeout=timeout_ms)
                    except Exception:
                        if screenshot_path:
                            Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                            page.screenshot(path=screenshot_path, full_page=True)
                        details = {
                            "console": console_rows,
                            "request_failed": request_failed_rows,
                            "api_records": api_records,
                        }
                        if devtools_path:
                            Path(devtools_path).parent.mkdir(parents=True, exist_ok=True)
                            save_json(Path(devtools_path), details)
                        return False, f"expect_selector_missing:{sel}", screenshot_path, details
                if screenshot_path:
                    Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=screenshot_path, full_page=True)
                details = {
                    "console": console_rows,
                    "request_failed": request_failed_rows,
                    "api_records": api_records,
                }
                if devtools_path:
                    Path(devtools_path).parent.mkdir(parents=True, exist_ok=True)
                    save_json(Path(devtools_path), details)
                return True, "ok", screenshot_path, details
            finally:
                if context is not None:
                    context.close()
                if browser is not None:
                    browser.close()
    except Exception as exc:
        return False, str(exc), screenshot_path, {}


def run_browser_check_selenium(
    url: str,
    expect_text: str,
    timeout_seconds: int,
    *,
    screenshot_file: str = "",
) -> tuple[bool, str, str, dict[str, Any]]:
    try:
        from selenium import webdriver  # type: ignore
        from selenium.webdriver.chrome.options import Options  # type: ignore
    except Exception as exc:
        return False, f"selenium_not_available:{exc}", "", {}

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    driver = None
    screenshot_path = str(Path(screenshot_file).expanduser()) if screenshot_file else ""
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(max(3, int(timeout_seconds)))
        driver.get(url)
        text = driver.page_source or ""
        if expect_text and expect_text not in text:
            if screenshot_path:
                Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                driver.save_screenshot(screenshot_path)
            return False, "expect_text_missing", screenshot_path, {}
        if screenshot_path:
            Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
            driver.save_screenshot(screenshot_path)
        return True, "ok", screenshot_path, {}
    except Exception as exc:
        return False, str(exc), screenshot_path, {}
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def issue_key(kind: str, item_id: str, reason: str) -> str:
    return f"{kind}:{item_id}:{reason}"


def update_issue_state(state: dict[str, Any], high_issues: list[dict[str, Any]]) -> dict[str, Any]:
    issues = state.setdefault("issues", {})
    seen_keys = set()
    created = 0
    reopened = 0
    resolved = 0
    created_keys: list[str] = []
    reopened_keys: list[str] = []
    ts = now_iso()

    for issue in high_issues:
        key = issue["issue_key"]
        seen_keys.add(key)
        rec = issues.get(key)
        if not isinstance(rec, dict):
            issues[key] = {
                "issue_key": key,
                "title": issue.get("title", ""),
                "first_seen": ts,
                "last_seen": ts,
                "status": "open",
                "occurrences": 1,
            }
            created += 1
            created_keys.append(key)
            continue
        if rec.get("status") == "resolved":
            rec["status"] = "open"
            reopened += 1
            reopened_keys.append(key)
        rec["last_seen"] = ts
        rec["title"] = issue.get("title", rec.get("title", ""))
        rec["occurrences"] = int(rec.get("occurrences", 0)) + 1

    for key, rec in list(issues.items()):
        if key in seen_keys:
            continue
        if not isinstance(rec, dict):
            continue
        if rec.get("status") == "open":
            rec["status"] = "resolved"
            rec["resolved_at"] = ts
            resolved += 1

    open_total = sum(1 for v in issues.values() if isinstance(v, dict) and v.get("status") == "open")
    return {
        "new_high": created,
        "reopened_high": reopened,
        "resolved_high": resolved,
        "open_high_total": open_total,
        "new_keys": created_keys,
        "reopened_keys": reopened_keys,
    }


def evaluate_endpoint(
    endpoint: dict[str, Any],
    *,
    endpoint_engine: str,
    headers_base: dict[str, str],
    timeout_default: int,
    freshness_default: int,
    freshness_auto_detect: bool,
    freshness_candidates_default: list[str],
) -> dict[str, Any]:
    endpoint_id = str(endpoint.get("id", "")).strip() or f"endpoint-{uuid.uuid4().hex[:8]}"
    url = str(endpoint.get("url", "")).strip()
    method = str(endpoint.get("method", "GET")).upper()
    timeout_seconds = int(endpoint.get("timeout_seconds") or timeout_default or 12)
    body = str(endpoint.get("body", "") or "")
    headers = dict(headers_base)
    user_headers = endpoint.get("headers")
    if isinstance(user_headers, dict):
        headers.update({str(k): str(v) for k, v in user_headers.items()})

    result: dict[str, Any] = {
        "id": endpoint_id,
        "url": url,
        "method": method,
        "risk_level": "low",
        "status": "ok",
        "reasons": [],
    }
    if not url:
        result.update({"risk_level": "high", "status": "failed", "reasons": ["missing_url"]})
        return result

    probe_engine = normalize_engine(str(endpoint.get("engine", endpoint_engine)), default=endpoint_engine)
    result["probe_engine"] = probe_engine
    if probe_engine in {"playwright", "playwright-real"}:
        status_code, content_type, text = playwright_call(method, url, headers, body, timeout_seconds)
    else:
        status_code, content_type, text = http_call(method, url, headers, body, timeout_seconds)

    result["status_code"] = status_code
    result["content_type"] = content_type
    result["response_size"] = len(text or "")

    if status_code < 200 or status_code >= 300:
        result["risk_level"] = "high"
        result["status"] = "failed"
        result["reasons"].append(f"http_status_{status_code}")
        result["preview"] = (text or "")[:240]
        result["issue_key"] = issue_key("endpoint", endpoint_id, f"http_status_{status_code}")
        return result

    expect_json = bool(endpoint.get("expect_json", True))
    parsed: Any = None
    if expect_json:
        try:
            parsed = json.loads(text)
            result["parsed_json"] = True
        except Exception:
            result["risk_level"] = "high"
            result["status"] = "failed"
            result["reasons"].append("invalid_json")
            result["preview"] = (text or "")[:240]
            result["issue_key"] = issue_key("endpoint", endpoint_id, "invalid_json")
            return result
    else:
        parsed = text

    required_fields = endpoint.get("required_fields") or []
    if isinstance(required_fields, list):
        for field in required_fields:
            field = str(field).strip()
            if not field:
                continue
            if extract_by_path(parsed, field) is None:
                result["risk_level"] = "high"
                result["status"] = "failed"
                result["reasons"].append(f"missing_field:{field}")

    if bool(endpoint.get("require_non_empty", True)):
        data_field = str(endpoint.get("data_field", "")).strip()
        payload = extract_by_path(parsed, data_field) if data_field else parsed
        if is_empty_value(payload):
            result["risk_level"] = "high"
            result["status"] = "failed"
            result["reasons"].append("empty_payload")

    freshness_field = str(endpoint.get("freshness_field", "")).strip()
    freshness_required = parse_bool(endpoint.get("freshness_required"), bool(freshness_field))
    auto_detect = parse_bool(endpoint.get("freshness_auto_detect"), freshness_auto_detect)
    candidates_raw = endpoint.get("freshness_candidate_fields")
    if isinstance(candidates_raw, list) and candidates_raw:
        candidates = [str(x).strip() for x in candidates_raw if str(x).strip()]
    else:
        candidates = list(freshness_candidates_default)
    max_age = int(endpoint.get("freshness_max_age_seconds") or freshness_default or 300)
    probed_fields: list[str] = []
    freshness_selected_field = ""
    freshness_selected_ts = ""
    freshness_selected_dt: datetime | None = None

    if freshness_field:
        probed_fields.append(freshness_field)
        raw_ts = extract_by_path(parsed, freshness_field)
        dt = parse_dt(raw_ts)
        if dt is None:
            result["risk_level"] = "high"
            result["status"] = "failed"
            result["reasons"].append("freshness_field_invalid")
        else:
            freshness_selected_field = freshness_field
            freshness_selected_ts = str(raw_ts)
            freshness_selected_dt = dt
    elif auto_detect:
        parsed_hits: list[tuple[str, str, datetime]] = []
        for field in candidates:
            if not field:
                continue
            probed_fields.append(field)
            raw_ts = extract_by_path(parsed, field)
            dt = parse_dt(raw_ts)
            if dt is None:
                continue
            parsed_hits.append((field, str(raw_ts), dt))
        if parsed_hits:
            field, ts_raw, dt = max(parsed_hits, key=lambda x: x[2])
            freshness_selected_field = field
            freshness_selected_ts = ts_raw
            freshness_selected_dt = dt
        elif freshness_required:
            result["risk_level"] = "high"
            result["status"] = "failed"
            result["reasons"].append("freshness_field_missing")
    elif freshness_required:
        result["risk_level"] = "high"
        result["status"] = "failed"
        result["reasons"].append("freshness_field_missing")

    if freshness_selected_dt is not None:
        age_seconds = int((now() - freshness_selected_dt).total_seconds())
        result["freshness_field"] = freshness_selected_field
        result["freshness_raw_value"] = freshness_selected_ts
        result["freshness_age_seconds"] = age_seconds
        result["freshness_max_age_seconds"] = max(1, max_age)
        if age_seconds > max(1, max_age):
            result["risk_level"] = "high"
            result["status"] = "failed"
            result["reasons"].append(f"stale_data:{age_seconds}s>{max_age}s")

    if probed_fields:
        result["freshness_probed_fields"] = probed_fields[:60]
    result["freshness_required"] = freshness_required
    result["freshness_auto_detect"] = auto_detect

    if result["risk_level"] == "high":
        reason = result["reasons"][0] if result["reasons"] else "unknown"
        result["issue_key"] = issue_key("endpoint", endpoint_id, reason)
    return result


def run_browser_checks(
    *,
    engine: str,
    checks: list[dict[str, Any]],
    timeout_default: int,
    screenshot_dir: Path,
    devtools_dir: Path,
    real_browser: dict[str, Any],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in checks:
        cid = str(item.get("id", "")).strip() or f"browser-{uuid.uuid4().hex[:8]}"
        url = str(item.get("url", "")).strip()
        expect_text = str(item.get("expect_text", "") or "")
        min_score = max(0, min(100, int(item.get("min_score", 80) or 80)))
        steps_raw = item.get("steps")
        steps = [x for x in steps_raw if isinstance(x, dict)] if isinstance(steps_raw, list) else []
        api_expectations_raw = item.get("api_expectations")
        api_expectations = [x for x in api_expectations_raw if isinstance(x, dict)] if isinstance(api_expectations_raw, list) else []
        expect_selectors_raw = item.get("expect_selectors")
        expect_selectors = [str(x).strip() for x in expect_selectors_raw if str(x).strip()] if isinstance(expect_selectors_raw, list) else []
        timeout_seconds = int(item.get("timeout_seconds") or timeout_default or 12)
        screenshot_file = screenshot_dir / f"{cid}.png"
        devtools_file = devtools_dir / f"{cid}.json"
        row = {
            "id": cid,
            "url": url,
            "risk_level": "low",
            "status": "ok",
            "reasons": [],
            "visual_review_required": True,
            "visual_review_mode": "native_ai_vision",
            "screenshot": "",
            "devtools_log": "",
            "steps_count": len(steps),
            "score": 100,
            "min_score": min_score,
            "api_expectations_count": len(api_expectations),
            "expect_selectors_count": len(expect_selectors),
        }
        if not url:
            row.update({"risk_level": "high", "status": "failed", "reasons": ["missing_url"]})
            row["issue_key"] = issue_key("browser", cid, "missing_url")
            results.append(row)
            continue

        if engine == "playwright":
            ok, note, screenshot_path, details = run_browser_check_playwright(
                url,
                expect_text,
                timeout_seconds,
                steps=steps,
                expect_selectors=expect_selectors,
                screenshot_file=str(screenshot_file),
                devtools_file=str(devtools_file),
            )
        elif engine == "playwright-real":
            ok, note, screenshot_path, details = run_browser_check_playwright(
                url,
                expect_text,
                timeout_seconds,
                steps=steps,
                expect_selectors=expect_selectors,
                screenshot_file=str(screenshot_file),
                devtools_file=str(devtools_file),
                real_browser=real_browser,
            )
        elif engine == "selenium":
            ok, note, screenshot_path, details = run_browser_check_selenium(
                url,
                expect_text,
                timeout_seconds,
                screenshot_file=str(screenshot_file),
            )
        else:
            ok, note, screenshot_path, details = False, "browser_checks_require_playwright_or_selenium", "", {}

        if screenshot_path and Path(screenshot_path).exists():
            row["screenshot"] = screenshot_path
        if devtools_file.exists():
            row["devtools_log"] = str(devtools_file)
        if isinstance(details, dict):
            console_rows = details.get("console", []) if isinstance(details.get("console"), list) else []
            request_failed_rows = details.get("request_failed", []) if isinstance(details.get("request_failed"), list) else []
            api_records = details.get("api_records", []) if isinstance(details.get("api_records"), list) else []
        else:
            console_rows, request_failed_rows, api_records = [], [], []

        console_errors = [x for x in console_rows if str(x.get("level", "")).lower() in {"error", "assert"}]
        console_warnings = [x for x in console_rows if str(x.get("level", "")).lower() in {"warning", "warn"}]
        row["console_error_count"] = len(console_errors)
        row["console_warning_count"] = len(console_warnings)
        row["request_failed_count"] = len(request_failed_rows)
        row["api_records_count"] = len(api_records)

        score = 100
        score -= min(40, len(console_errors) * 10)
        score -= min(30, len(request_failed_rows) * 10)

        api_failures: list[str] = []
        api_report: list[dict[str, Any]] = []
        if api_expectations:
            api_failures, api_report = evaluate_api_expectations(api_records, api_expectations)
            score -= min(60, len(api_failures) * 20)
            if api_failures:
                row["reasons"].append("api_expectation_failed")
                row["api_failures"] = api_failures
        row["api_expectation_report"] = api_report

        if not api_expectations and parse_bool(item.get("require_api_output"), True):
            if len(api_records) == 0:
                row["reasons"].append("api_no_output")
                score -= 30

        if not ok:
            score -= 20
        row["score"] = max(0, score)

        if console_errors:
            row["reasons"].append(f"console_errors:{len(console_errors)}")
        if request_failed_rows:
            row["reasons"].append(f"request_failed:{len(request_failed_rows)}")

        if not ok:
            row["risk_level"] = "high"
            row["status"] = "failed"
            row["reasons"].append(note)
            row["issue_key"] = issue_key("browser", cid, note)
        elif row["score"] < min_score:
            row["risk_level"] = "high"
            row["status"] = "failed"
            row["reasons"].append(f"score_below_threshold:{row['score']}<{min_score}")
            row["issue_key"] = issue_key("browser", cid, "score_below_threshold")

        if row["status"] == "ok":
            row["reasons"] = [x for x in row["reasons"] if str(x).strip()]
        results.append(row)
    return results


def main() -> int:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="OpenClaw API audit runner")
    parser.add_argument("--config-file", default=str(home / ".openclaw/ops/api-test-config.json"))
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/api-test-state.json"))
    parser.add_argument("--history-dir", default=str(home / ".openclaw/ops/api-test-runs"))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--engine", default="", help="http|playwright|playwright-real|selenium; empty uses config")
    parser.add_argument("--sender-identity", default=DEFAULT_SENDER_IDENTITY)
    parser.add_argument("--normal-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--allow-auto-default-config", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config_file).expanduser()
    state_path = Path(args.state_file).expanduser()
    history_dir = Path(args.history_dir).expanduser()
    history_dir.mkdir(parents=True, exist_ok=True)

    config = load_json(config_path, None)
    config_source = "file"
    if not isinstance(config, dict):
        if bool(args.allow_auto_default_config):
            config = default_config()
            save_json(config_path, config)
            config_source = "auto-default"
        else:
            sender_identity = normalize_sender_identity(args.sender_identity)
            normal_log_mode = normalize_log_mode(args.normal_log_mode, default="silent")
            run_record = {
                "run_id": uuid.uuid4().hex[:12],
                "time": now_iso(),
                "sender_identity": sender_identity,
                "task_id": str(args.task_id or ""),
                "engine": normalize_engine(args.engine or "playwright-real", default="playwright-real"),
                "normal_log_mode": normal_log_mode,
                "notify": True,
                "risk_reasons": ["config_missing"],
                "issue_stats": {"new_high": 1, "reopened_high": 0, "resolved": 0, "open_total": 1},
                "endpoint_count": 0,
                "browser_check_count": 0,
                "high_count": 1,
                "config_source": "missing",
                "results": [
                    {
                        "id": "api-test-config",
                        "risk_level": "high",
                        "status": "failed",
                        "reasons": ["config_missing"],
                        "config_file": str(config_path),
                        "suggestion": "run init_api_test_config.py to create real endpoint checks",
                    }
                ],
            }
            run_file = history_dir / f"{now().strftime('%Y%m%d_%H%M%S')}_{run_record['run_id']}.json"
            save_json(run_file, run_record)
            state = load_json(state_path, None)
            if not isinstance(state, dict):
                state = default_state()
            state["updated_at"] = now_iso()
            state["runs"] = int(state.get("runs", 0)) + 1
            state["last_run_file"] = str(run_file)
            save_json(state_path, state)
            output = (
                "# api-test-audit\n"
                f"- sender_identity: {sender_identity}\n"
                f"- task: {args.task_id or '-'}\n"
                f"- time: {now_iso()}\n"
                f"- normal_log_mode: {normal_log_mode}\n"
                "- risk_reasons: config_missing\n"
                f"- config_file: {config_path}\n"
                "- action: run init_api_test_config.py and replace placeholders"
            )
            if args.emit_json:
                print(json.dumps({"notify": True, "output": output, "record": str(run_file)}, ensure_ascii=False))
            else:
                print(f"{output}\n- evidence: {run_file}")
            return 0

    state = load_json(state_path, None)
    if not isinstance(state, dict):
        state = default_state()

    engine = normalize_engine(args.engine or config.get("engine", "playwright-real"), default="playwright-real")
    endpoint_engine = normalize_engine(config.get("endpoint_engine", "http"), default="http")
    forbid_http_engine = parse_bool(config.get("forbid_http_engine", True), True)
    require_browser_checks = parse_bool(config.get("require_browser_checks", True), True)
    real_browser_raw = config.get("real_browser")
    real_browser = real_browser_raw if isinstance(real_browser_raw, dict) else {}
    if not str(real_browser.get("user_data_dir", "")).strip():
        real_browser["user_data_dir"] = (
            os.environ.get("OPENCLAW_CHROME_USER_DATA_DIR", "").strip() or os.path.expanduser("~/.config/google-chrome")
        )
    if not str(real_browser.get("profile_directory", "")).strip():
        real_browser["profile_directory"] = os.environ.get("OPENCLAW_CHROME_PROFILE", "Default").strip() or "Default"
    if "channel" not in real_browser:
        real_browser["channel"] = os.environ.get("OPENCLAW_CHROME_CHANNEL", "").strip()
    elif str(real_browser.get("channel", "")).strip().lower() in {"none", "null"}:
        real_browser["channel"] = ""
    if "headless" not in real_browser:
        real_browser["headless"] = False

    timeout_default = int(config.get("default_timeout_seconds") or 12)
    freshness_default = int(config.get("freshness_default_max_age_seconds") or 300)
    freshness_auto_detect = parse_bool(config.get("freshness_auto_detect"), True)
    freshness_candidates_raw = config.get("freshness_candidate_fields")
    if isinstance(freshness_candidates_raw, list) and freshness_candidates_raw:
        freshness_candidates_default = [str(x).strip() for x in freshness_candidates_raw if str(x).strip()]
    else:
        freshness_candidates_default = list(DEFAULT_FRESHNESS_CANDIDATES)
    headers_base = config.get("base_headers") if isinstance(config.get("base_headers"), dict) else {}
    headers_base = {str(k): str(v) for k, v in headers_base.items()}

    endpoint_items = config.get("endpoints") if isinstance(config.get("endpoints"), list) else []
    browser_items = config.get("browser_checks") if isinstance(config.get("browser_checks"), list) else []
    endpoint_items = [x for x in endpoint_items if isinstance(x, dict) and bool(x.get("enabled", True))]
    browser_items = [x for x in browser_items if isinstance(x, dict) and bool(x.get("enabled", True))]

    endpoint_results = [
        evaluate_endpoint(
            x if isinstance(x, dict) else {},
            endpoint_engine=endpoint_engine,
            headers_base=headers_base,
            timeout_default=timeout_default,
            freshness_default=freshness_default,
            freshness_auto_detect=freshness_auto_detect,
            freshness_candidates_default=freshness_candidates_default,
        )
        for x in endpoint_items
    ]
    run_token = uuid.uuid4().hex[:8]
    screenshot_dir = history_dir / "screenshots" / f"{now().strftime('%Y%m%d_%H%M%S')}_{run_token}"
    devtools_dir = history_dir / "devtools" / f"{now().strftime('%Y%m%d_%H%M%S')}_{run_token}"
    browser_results = run_browser_checks(
        engine=engine,
        checks=[i if isinstance(i, dict) else {} for i in browser_items],
        timeout_default=timeout_default,
        screenshot_dir=screenshot_dir,
        devtools_dir=devtools_dir,
        real_browser=real_browser,
    )

    policy_results: list[dict[str, Any]] = []
    if engine == "http" and forbid_http_engine:
        policy_results.append(
            {
                "id": "engine-policy",
                "risk_level": "high",
                "status": "failed",
                "reasons": ["http_engine_forbidden"],
                "issue_key": issue_key("policy", "engine-policy", "http_engine_forbidden"),
                "suggestion": "use playwright-real with browser checks",
            }
        )
    if require_browser_checks and not browser_items:
        policy_results.append(
            {
                "id": "browser-check-policy",
                "risk_level": "high",
                "status": "failed",
                "reasons": ["browser_checks_required"],
                "issue_key": issue_key("policy", "browser-check-policy", "browser_checks_required"),
            }
        )
    if require_browser_checks and browser_items:
        has_interactive_step = False
        for item in browser_items:
            steps = item.get("steps")
            if not isinstance(steps, list):
                continue
            for step in steps:
                if not isinstance(step, dict):
                    continue
                action = str(step.get("action", "")).strip().lower()
                if action in {"click", "fill", "press"}:
                    has_interactive_step = True
                    break
            if has_interactive_step:
                break
        if not has_interactive_step:
            policy_results.append(
                {
                    "id": "browser-check-policy",
                    "risk_level": "high",
                    "status": "failed",
                    "reasons": ["e2e_click_steps_required"],
                    "issue_key": issue_key("policy", "browser-check-policy", "e2e_click_steps_required"),
                }
            )

    all_results = endpoint_results + browser_results + policy_results

    high_issues = [x for x in all_results if str(x.get("risk_level")) == "high"]
    issue_stats = update_issue_state(state, high_issues)
    alert_issue_keys = set(issue_stats.get("new_keys", []) + issue_stats.get("reopened_keys", []))
    alert_issues = [x for x in high_issues if str(x.get("issue_key", "")) in alert_issue_keys]

    normal_log_mode = normalize_log_mode(args.normal_log_mode, default="silent")
    sender_identity = normalize_sender_identity(args.sender_identity)
    risk_reasons: list[str] = []
    if issue_stats["new_high"] > 0:
        risk_reasons.append(f"new_high={issue_stats['new_high']}")
    if issue_stats["reopened_high"] > 0:
        risk_reasons.append(f"reopened_high={issue_stats['reopened_high']}")

    # Keep scheduled audit quiet by default: only notify when there are new/reopened high-risk findings.
    notify = bool(alert_issues)

    run_record = {
        "run_id": uuid.uuid4().hex[:12],
        "time": now_iso(),
        "sender_identity": sender_identity,
        "task_id": str(args.task_id or ""),
        "engine": engine,
        "endpoint_engine": endpoint_engine,
        "freshness_auto_detect": freshness_auto_detect,
        "freshness_candidate_fields_count": len(freshness_candidates_default),
        "forbid_http_engine": forbid_http_engine,
        "require_browser_checks": require_browser_checks,
        "visual_review_mode": "native_ai_vision",
        "normal_log_mode": normal_log_mode,
        "notify": notify,
        "risk_reasons": risk_reasons,
        "issue_stats": issue_stats,
        "endpoint_count": len(endpoint_results),
        "browser_check_count": len(browser_results),
        "high_count": len(high_issues),
        "alert_high_count": len(alert_issues),
        "config_source": config_source,
        "config_file": str(config_path),
        "screenshot_dir": str(screenshot_dir),
        "devtools_dir": str(devtools_dir),
        "results": all_results,
    }
    run_file = history_dir / f"{now().strftime('%Y%m%d_%H%M%S')}_{run_record['run_id']}.json"
    save_json(run_file, run_record)

    state["updated_at"] = now_iso()
    state["runs"] = int(state.get("runs", 0)) + 1
    state["last_run_file"] = str(run_file)
    save_json(state_path, state)

    output = "NO_REPLY"
    if notify:
        lines: list[str] = []
        lines.append("# api-test-audit")
        lines.append(f"- sender_identity: {sender_identity}")
        lines.append(f"- task: {args.task_id or '-'}")
        lines.append(f"- time: {now_iso()}")
        lines.append(f"- engine: {engine}")
        lines.append(f"- endpoint_engine: {endpoint_engine}")
        lines.append(f"- freshness_auto_detect: {freshness_auto_detect}")
        lines.append(f"- normal_log_mode: {normal_log_mode}")
        if risk_reasons:
            lines.append(f"- risk_reasons: {', '.join(risk_reasons)}")
        lines.append(f"- tested_endpoints: {len(endpoint_results)}")
        lines.append(f"- tested_browser_checks: {len(browser_results)}")
        lines.append(f"- high_issues: {len(alert_issues)}")
        for item in alert_issues[:6]:
            lines.append(f"- high[{item.get('id')}]: {', '.join(item.get('reasons', []))}")
            if item.get("score") is not None:
                lines.append(f"- high[{item.get('id')}]_score: {item.get('score')}/{item.get('min_score', '-')}")
            screenshot = str(item.get("screenshot", "")).strip()
            if screenshot:
                lines.append(f"- high[{item.get('id')}]_screenshot: {screenshot}")
            devtools_log = str(item.get("devtools_log", "")).strip()
            if devtools_log:
                lines.append(f"- high[{item.get('id')}]_devtools: {devtools_log}")
        lines.append("- visual_review: use native AI vision on screenshots; do not run image parsing scripts")
        output = "\n".join(lines)

    if args.emit_json:
        print(json.dumps({"notify": notify, "output": output, "record": str(run_file)}, ensure_ascii=False))
    else:
        if notify:
            print(f"{output}\n- evidence: {run_file}")
        else:
            print("NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
