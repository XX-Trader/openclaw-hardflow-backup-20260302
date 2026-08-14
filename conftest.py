"""Assign every collected test to exactly one CI tier."""

from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent
QUICK_TEST_MODULES = frozenset(
    {
        "tests/scripts_openclaw_ops/test_active_agent_registry.py",
        "tests/scripts_openclaw_ops/test_api_doc_gate.py",
        "tests/scripts_openclaw_ops/test_ensure_runtime_skills.py",
        "tests/scripts_openclaw_ops/test_git_sync_push_runner.py",
        "tests/scripts_openclaw_ops/test_intelligent_router.py",
        "tests/scripts_openclaw_ops/test_project_pipeline_entry.py",
        "tests/scripts_openclaw_ops/test_repository_policy_check.py",
        "tests/scripts_openclaw_ops/test_runtime_docs_clean.py",
        "tests/scripts_openclaw_ops/test_runtime_host_defaults.py",
        "tests/scripts_openclaw_ops/test_runtime_profile_templates.py",
        "tests/scripts_openclaw_ops/test_schedule_registry.py",
    }
)


def _relative_test_path(item: pytest.Item) -> str:
    path = Path(str(item.path)).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Keep quick and integration runs exhaustive and mutually exclusive."""

    for item in items:
        quick = item.get_closest_marker("quick") is not None
        integration = item.get_closest_marker("integration") is not None
        if quick and integration:
            raise pytest.UsageError(f"test has conflicting tier markers: {item.nodeid}")
        if not quick and not integration:
            tier = "quick" if _relative_test_path(item) in QUICK_TEST_MODULES else "integration"
            item.add_marker(getattr(pytest.mark, tier))
