#!/usr/bin/env python3
"""Shared Scrapling adapters for OpenClaw web fetching and browser checks."""

from __future__ import annotations

from typing import Any, Callable

SCRAPLING_ENGINES = {"scrapling", "scrapling-stealth"}


def normalize_scrapling_engine(value: str, default: str = "scrapling") -> str:
    engine = str(value or "").strip().lower()
    return engine if engine in SCRAPLING_ENGINES else default


def _headers_to_dict(headers: Any) -> dict[str, str]:
    if isinstance(headers, dict):
        return {str(k): str(v) for k, v in headers.items()}
    if hasattr(headers, "items"):
        try:
            return {str(k): str(v) for k, v in headers.items()}
        except Exception:
            return {}
    return {}


def _response_text(response: Any) -> str:
    body = getattr(response, "body", b"")
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    if body is None:
        return ""
    return str(body)


def _response_payload(response: Any, *, method_name: str) -> dict[str, Any]:
    headers = _headers_to_dict(getattr(response, "headers", {}) or {})
    content_type = ""
    for key, value in headers.items():
        if str(key).lower() == "content-type":
            content_type = str(value)
            break
    return {
        "ok": True,
        "method": method_name,
        "status": int(getattr(response, "status", 0) or 0),
        "content_type": content_type,
        "text": _response_text(response),
        "truncated": False,
        "error": "",
    }


def _error_payload(method_name: str, error_text: str) -> dict[str, Any]:
    return {
        "ok": False,
        "method": method_name,
        "status": 0,
        "content_type": "",
        "text": "",
        "truncated": False,
        "error": str(error_text or "").strip() or "scrapling_failed",
    }


def fetch_with_scrapling_static(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: str = "",
    timeout_seconds: int = 20,
    engine: str = "scrapling",
) -> dict[str, Any]:
    normalized_engine = normalize_scrapling_engine(engine)
    method_name = "http-scrapling-stealth" if normalized_engine == "scrapling-stealth" else "http-scrapling"
    try:
        from scrapling import Fetcher  # type: ignore
    except Exception as exc:
        return _error_payload(method_name, f"scrapling_unavailable:{exc}")

    http_method = str(method or "GET").strip().upper()
    if http_method not in {"GET", "POST", "PUT", "DELETE"}:
        return _error_payload(method_name, f"scrapling_unsupported_method:{http_method}")

    request_fn = getattr(Fetcher, http_method.lower(), None)
    if request_fn is None:
        return _error_payload(method_name, f"scrapling_unsupported_method:{http_method}")

    kwargs: dict[str, Any] = {
        "timeout": max(1, int(timeout_seconds)),
        "follow_redirects": True,
        "stealthy_headers": True,
    }
    if headers:
        kwargs["headers"] = {str(k): str(v) for k, v in headers.items()}
    if body and http_method != "GET":
        kwargs["data"] = str(body)

    try:
        response = request_fn(url, **kwargs)
        return _response_payload(response, method_name=method_name)
    except Exception as exc:
        return _error_payload(method_name, f"scrapling_request_failed:{exc}")


def fetch_with_scrapling_browser(
    url: str,
    *,
    timeout_seconds: int = 20,
    engine: str = "scrapling",
    extra_headers: dict[str, str] | None = None,
    wait_selector: str = "",
    wait_selector_state: str = "visible",
    page_action: Callable[[Any], Any] | None = None,
    disable_resources: bool = False,
    headless: bool = True,
) -> dict[str, Any]:
    normalized_engine = normalize_scrapling_engine(engine)
    method_name = "browser-scrapling-stealth" if normalized_engine == "scrapling-stealth" else "browser-scrapling"
    try:
        if normalized_engine == "scrapling-stealth":
            from scrapling import StealthyFetcher as BrowserFetcher  # type: ignore
        else:
            from scrapling import DynamicFetcher as BrowserFetcher  # type: ignore
    except Exception as exc:
        return _error_payload(method_name, f"scrapling_unavailable:{exc}")

    kwargs: dict[str, Any] = {
        "headless": bool(headless),
        "disable_resources": bool(disable_resources),
        "network_idle": True,
        "load_dom": True,
        "google_search": False,
        "timeout": max(1000, int(timeout_seconds) * 1000),
        "wait": 300,
    }
    if extra_headers:
        kwargs["extra_headers"] = {str(k): str(v) for k, v in extra_headers.items()}
    if wait_selector:
        kwargs["wait_selector"] = str(wait_selector).strip()
        kwargs["wait_selector_state"] = str(wait_selector_state or "visible").strip() or "visible"
    if page_action is not None:
        kwargs["page_action"] = page_action
    if normalized_engine == "scrapling-stealth":
        kwargs["solve_cloudflare"] = True

    try:
        response = BrowserFetcher.fetch(url, **kwargs)
        return _response_payload(response, method_name=method_name)
    except Exception as exc:
        return _error_payload(method_name, f"scrapling_browser_failed:{exc}")
