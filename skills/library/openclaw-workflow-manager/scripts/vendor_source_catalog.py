#!/usr/bin/env python3
"""Shared vendor doc and repository catalog for project-aware web evolution."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

DEFAULT_PROJECT_INDEX_DIR = ".workflow/project-index-local"
LEGACY_PROJECT_INDEX_DIR = ".workflow/project-index"

VENDOR_CATALOG: dict[str, dict[str, Any]] = {
    "github": {
        "host_keywords": ["github.com"],
        "doc_sources": [
            {
                "id": "github-rest-getting-started",
                "tag": "github",
                "name": "GitHub REST API Getting Started",
                "url": "https://docs.github.com/en/rest/using-the-rest-api/getting-started-with-the-rest-api",
                "category": "api-doc",
                "tags": ["official", "api", "reference", "github"],
                "browser_fallback": True,
                "min_interval_minutes": 180,
            },
            {
                "id": "github-rest-versioning",
                "tag": "github",
                "name": "GitHub REST API Versions",
                "url": "https://docs.github.com/en/rest/about-the-rest-api/api-versions",
                "category": "official-doc",
                "tags": ["official", "api", "release", "github"],
                "browser_fallback": True,
                "min_interval_minutes": 180,
            },
        ],
        "repo_source": {
            "vendor": "github",
            "official_repos": [
                "github/rest-api-description",
                "github/docs",
                "cli/cli",
            ],
            "repo_queries": [
                "org:github rest api archived:false",
                "org:github api client archived:false",
            ],
        },
    }
}

COMMON_HOST_TOKENS = {
    "api",
    "apis",
    "app",
    "apps",
    "cloud",
    "com",
    "cn",
    "co",
    "dev",
    "developers",
    "developer",
    "docs",
    "doc",
    "fapi",
    "dapi",
    "io",
    "net",
    "org",
    "openapi",
    "platform",
    "prod",
    "production",
    "rest",
    "sandbox",
    "service",
    "services",
    "stage",
    "staging",
    "test",
    "testnet",
    "www",
    "ws",
    "wss",
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


def extract_host_repo_terms(host: str) -> list[str]:
    parts = re.split(r"[^a-z0-9]+", str(host or "").strip().lower())
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if not part or len(part) < 3 or part in COMMON_HOST_TOKENS:
            continue
        if part.isdigit():
            continue
        if part in seen:
            continue
        seen.add(part)
        out.append(part)
    return out[:4]


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


def build_host_repo_source(host: str) -> dict[str, Any] | None:
    clean_host = str(host or "").strip().lower()
    if not clean_host or detect_vendors_from_fragments([clean_host]):
        return None
    terms = extract_host_repo_terms(clean_host)
    if not terms:
        return None
    phrase = " ".join(terms[:3]).strip()
    if not phrase:
        return None
    return {
        "vendor": terms[0],
        "host": clean_host,
        "official_repos": [],
        "repo_queries": unique_texts(
            [
                f"{phrase} api sdk archived:false",
                f"{phrase} api client archived:false",
                f"{phrase} official sdk archived:false",
            ]
        ),
    }


def build_host_repo_sources(hosts: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for host in hosts:
        row = build_host_repo_source(host)
        if row is None:
            continue
        key = str(row.get("host", "")).strip().lower() or str(row.get("vendor", "")).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out
