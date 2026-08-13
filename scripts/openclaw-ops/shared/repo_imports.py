"""Resolve first-party script owners when tools run directly from a source checkout."""

from __future__ import annotations

import sys
from pathlib import Path


OWNER_SCRIPT_DIRS = (
    "skills/library/control-plane-ops/scripts/policy",
    "scripts/openclaw-ops/shared",
    "skills/library/control-plane-ops/scripts",
    "skills/library/openclaw-workflow-manager/scripts",
    "skills/library/todo-patrol/scripts",
    "skills/library/log-monitor/scripts",
    "skills/library/task-cost-analytics/scripts",
    "skills/library/web-intelligence/scripts",
    "skills/library/receiving-code-review/scripts",
    "skills/library/openclaw-security-audit/scripts",
    "skills/library/config-watchdog/scripts",
    "skills/library/git-sync/scripts",
    "skills/library/fleet-sync/scripts",
)


def find_repository_root(source: str | Path) -> Path | None:
    start = Path(source).resolve()
    for candidate in (start.parent, *start.parents):
        if (
            (candidate / "scripts" / "openclaw-ops" / "shared").is_dir()
            and (candidate / "skills" / "library").is_dir()
        ):
            return candidate
    return None


def bootstrap_repository_imports(source: str | Path) -> Path | None:
    """Prepend existing owner directories and return the repository root."""

    root = find_repository_root(source)
    if root is None:
        return None
    resolved = [root / relative for relative in OWNER_SCRIPT_DIRS]
    for directory in reversed(resolved):
        value = str(directory)
        if directory.is_dir() and value not in sys.path:
            sys.path.insert(0, value)
    return root
