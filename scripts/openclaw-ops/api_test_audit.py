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
ENGINES = {"http", "playwright", "selenium"}
DEFAULT_SENDER_IDENTITY = "ops-agent/api-test-audit"


def now() -> datetime:
    return datetime.now(TZ)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else default


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
        "engine": "http",
        "default_timeout_seconds": 12,
        "base_headers": {},
        "freshness_default_max_age_seconds": 300,
        "endpoints": [
            {
                "id": "example-market",
                "method": "GET",
                "url": "https://example.com/api/market",
                "expect_json": True,
                "require_non_empty": True,
                "freshness_field": "data.ts",
                "freshness_max_age_seconds": 60,
                "required_fields": ["code", "data"],
            }
        ],
        "browser_checks": [
            {
                "id": "example-dashboard",
                "url": "https://example.com/dashboard",
                "expect_text": "在线",
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


def run_browser_check_playwright(url: str, expect_text: str, timeout_seconds: int) -> tuple[bool, str]:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:
        return False, f"playwright_not_available:{exc}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(ignore_https_errors=True)
            try:
                page.goto(url, wait_until="networkidle", timeout=max(1000, int(timeout_seconds) * 1000))
                text = page.content()
                if expect_text and expect_text not in text:
                    return False, "expect_text_missing"
                return True, "ok"
            finally:
                browser.close()
    except Exception as exc:
        return False, str(exc)


def run_browser_check_selenium(url: str, expect_text: str, timeout_seconds: int) -> tuple[bool, str]:
    try:
        from selenium import webdriver  # type: ignore
        from selenium.webdriver.chrome.options import Options  # type: ignore
    except Exception as exc:
        return False, f"selenium_not_available:{exc}"

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(max(3, int(timeout_seconds)))
        driver.get(url)
        text = driver.page_source or ""
        if expect_text and expect_text not in text:
            return False, "expect_text_missing"
        return True, "ok"
    except Exception as exc:
        return False, str(exc)
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def issue_key(kind: str, item_id: str, reason: str) -> str:
    return f"{kind}:{item_id}:{reason}"


def update_issue_state(state: dict[str, Any], high_issues: list[dict[str, Any]]) -> dict[str, int]:
    issues = state.setdefault("issues", {})
    seen_keys = set()
    created = 0
    reopened = 0
    resolved = 0
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
            continue
        if rec.get("status") == "resolved":
            rec["status"] = "open"
            reopened += 1
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
    return {"new_high": created, "reopened_high": reopened, "resolved_high": resolved, "open_high_total": open_total}


def evaluate_endpoint(
    endpoint: dict[str, Any],
    *,
    engine: str,
    headers_base: dict[str, str],
    timeout_default: int,
    freshness_default: int,
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

    if engine == "playwright":
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
    if freshness_field:
        raw_ts = extract_by_path(parsed, freshness_field)
        dt = parse_dt(raw_ts)
        if dt is None:
            result["risk_level"] = "high"
            result["status"] = "failed"
            result["reasons"].append("freshness_field_invalid")
        else:
            age_seconds = int((now() - dt).total_seconds())
            result["freshness_age_seconds"] = age_seconds
            max_age = int(endpoint.get("freshness_max_age_seconds") or freshness_default or 300)
            if age_seconds > max(1, max_age):
                result["risk_level"] = "high"
                result["status"] = "failed"
                result["reasons"].append(f"stale_data:{age_seconds}s>{max_age}s")

    if result["risk_level"] == "high":
        reason = result["reasons"][0] if result["reasons"] else "unknown"
        result["issue_key"] = issue_key("endpoint", endpoint_id, reason)
    return result


def run_browser_checks(engine: str, checks: list[dict[str, Any]], timeout_default: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in checks:
        cid = str(item.get("id", "")).strip() or f"browser-{uuid.uuid4().hex[:8]}"
        url = str(item.get("url", "")).strip()
        expect_text = str(item.get("expect_text", "") or "")
        timeout_seconds = int(item.get("timeout_seconds") or timeout_default or 12)
        row = {"id": cid, "url": url, "risk_level": "low", "status": "ok", "reasons": []}
        if not url:
            row.update({"risk_level": "high", "status": "failed", "reasons": ["missing_url"]})
            row["issue_key"] = issue_key("browser", cid, "missing_url")
            results.append(row)
            continue

        if engine == "playwright":
            ok, note = run_browser_check_playwright(url, expect_text, timeout_seconds)
        elif engine == "selenium":
            ok, note = run_browser_check_selenium(url, expect_text, timeout_seconds)
        else:
            ok, note = False, "browser_checks_require_playwright_or_selenium"

        if not ok:
            row["risk_level"] = "high"
            row["status"] = "failed"
            row["reasons"].append(note)
            row["issue_key"] = issue_key("browser", cid, note)
        results.append(row)
    return results


def main() -> int:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="OpenClaw API audit runner")
    parser.add_argument("--config-file", default=str(home / ".openclaw/ops/api-test-config.json"))
    parser.add_argument("--state-file", default=str(home / ".openclaw/ops/api-test-state.json"))
    parser.add_argument("--history-dir", default=str(home / ".openclaw/ops/api-test-runs"))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--engine", default="", help="http|playwright|selenium; empty uses config")
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
                "engine": normalize_engine(args.engine or "http", default="http"),
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

    engine = normalize_engine(args.engine or config.get("engine", "http"), default="http")
    timeout_default = int(config.get("default_timeout_seconds") or 12)
    freshness_default = int(config.get("freshness_default_max_age_seconds") or 300)
    headers_base = config.get("base_headers") if isinstance(config.get("base_headers"), dict) else {}
    headers_base = {str(k): str(v) for k, v in headers_base.items()}

    endpoint_items = config.get("endpoints") if isinstance(config.get("endpoints"), list) else []
    browser_items = config.get("browser_checks") if isinstance(config.get("browser_checks"), list) else []
    endpoint_items = [x for x in endpoint_items if isinstance(x, dict) and bool(x.get("enabled", True))]
    browser_items = [x for x in browser_items if isinstance(x, dict) and bool(x.get("enabled", True))]

    endpoint_results = [
        evaluate_endpoint(
            x if isinstance(x, dict) else {},
            engine=engine,
            headers_base=headers_base,
            timeout_default=timeout_default,
            freshness_default=freshness_default,
        )
        for x in endpoint_items
    ]
    browser_results = [
        x
        for x in run_browser_checks(
            engine=engine,
            checks=[i if isinstance(i, dict) else {} for i in browser_items],
            timeout_default=timeout_default,
        )
    ]
    all_results = endpoint_results + browser_results

    high_issues = [x for x in all_results if str(x.get("risk_level")) == "high"]
    issue_stats = update_issue_state(state, high_issues)

    normal_log_mode = normalize_log_mode(args.normal_log_mode, default="silent")
    sender_identity = normalize_sender_identity(args.sender_identity)
    risk_reasons: list[str] = []
    if issue_stats["new_high"] > 0:
        risk_reasons.append(f"new_high={issue_stats['new_high']}")
    if issue_stats["reopened_high"] > 0:
        risk_reasons.append(f"reopened_high={issue_stats['reopened_high']}")
    if high_issues:
        risk_reasons.append(f"high_issues={len(high_issues)}")

    # Keep scheduled audit quiet by default: only notify on high-risk findings.
    notify = bool(risk_reasons)

    run_record = {
        "run_id": uuid.uuid4().hex[:12],
        "time": now_iso(),
        "sender_identity": sender_identity,
        "task_id": str(args.task_id or ""),
        "engine": engine,
        "normal_log_mode": normal_log_mode,
        "notify": notify,
        "risk_reasons": risk_reasons,
        "issue_stats": issue_stats,
        "endpoint_count": len(endpoint_results),
        "browser_check_count": len(browser_results),
        "high_count": len(high_issues),
        "config_source": config_source,
        "config_file": str(config_path),
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
        lines.append(f"- normal_log_mode: {normal_log_mode}")
        if risk_reasons:
            lines.append(f"- risk_reasons: {', '.join(risk_reasons)}")
        lines.append(f"- tested_endpoints: {len(endpoint_results)}")
        lines.append(f"- tested_browser_checks: {len(browser_results)}")
        lines.append(f"- high_issues: {len(high_issues)}")
        for item in high_issues[:6]:
            lines.append(f"- high[{item.get('id')}]: {', '.join(item.get('reasons', []))}")
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
