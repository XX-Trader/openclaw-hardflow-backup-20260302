#!/usr/bin/env python3
"""Shared vendor doc and repository catalog for project-aware web evolution."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

DEFAULT_PROJECT_INDEX_DIR = ".workflow/project-index-local"
LEGACY_PROJECT_INDEX_DIR = ".workflow/project-index"

VENDOR_CATALOG: dict[str, dict[str, Any]] = {
    "binance": {
        "host_keywords": ["binance.com"],
        "doc_sources": [
            {
                "id": "binance-spot-general",
                "tag": "binance",
                "name": "Binance Spot API General Info",
                "url": "https://developers.binance.com/docs/binance-spot-api-docs/rest-api/general-api-information",
                "category": "api-doc",
                "tags": ["official", "api", "reference", "binance", "spot"],
                "browser_fallback": True,
                "min_interval_minutes": 180,
            },
            {
                "id": "binance-spot-changelog",
                "tag": "binance",
                "name": "Binance Spot API Changelog",
                "url": "https://developers.binance.com/docs/binance-spot-api-docs/changelog",
                "category": "official-doc",
                "tags": ["official", "api", "release", "binance", "spot"],
                "browser_fallback": True,
                "min_interval_minutes": 180,
            },
        ],
        "repo_source": {
            "vendor": "binance",
            "official_repos": [
                "binance/binance-spot-api-docs",
                "binance/binance-connector-python",
                "binance/binance-connector-js",
                "binance/binance-futures-connector-python",
            ],
            "repo_queries": [
                "org:binance binance connector archived:false",
                "org:binance binance api docs archived:false",
            ],
        },
    }
}


def unique_texts(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def detect_vendors_from_fragments(fragments: list[str]) -> set[str]:
    vendors: set[str] = set()
    for fragment in fragments:
        low = str(fragment or "").lower()
        if not low:
            continue
        for vendor, meta in VENDOR_CATALOG.items():
            if vendor in low:
                vendors.add(vendor)
                continue
            for hint in meta.get("host_keywords", []):
                if str(hint).lower() in low:
                    vendors.add(vendor)
                    break
    return vendors


def detect_vendors_from_urls(urls: list[str]) -> set[str]:
    fragments: list[str] = []
    for value in urls:
        text = str(value or "").strip()
        if not text:
            continue
        fragments.append(text)
        try:
            parsed = urlparse(text)
        except Exception:
            continue
        host = str(parsed.hostname or "").strip().lower()
        if host:
            fragments.append(host)
    return detect_vendors_from_fragments(fragments)


def build_vendor_doc_sources(vendor: str) -> list[dict[str, Any]]:
    meta = VENDOR_CATALOG.get(str(vendor or "").strip().lower())
    if not isinstance(meta, dict):
        return []
    out: list[dict[str, Any]] = []
    for item in meta.get("doc_sources", []):
        if isinstance(item, dict):
            out.append(dict(item))
    return out


def build_vendor_repo_source(vendor: str) -> dict[str, Any] | None:
    meta = VENDOR_CATALOG.get(str(vendor or "").strip().lower())
    if not isinstance(meta, dict):
        return None
    source = meta.get("repo_source")
    if not isinstance(source, dict):
        return None
    official_repos = unique_texts([str(x).strip().lower() for x in source.get("official_repos", [])])
    repo_queries = unique_texts([str(x).strip() for x in source.get("repo_queries", [])])
    return {
        "vendor": str(source.get("vendor", vendor)).strip().lower() or str(vendor).strip().lower(),
        "official_repos": official_repos,
        "repo_queries": repo_queries,
    }
