#!/usr/bin/env python3
"""Root setup entry for OpenClaw hardflow.

Examples:
  python setup.py
  python setup.py --dry-run
  python setup.py --yes
  python setup.py --install-cron-setup --cron-channel telegram --cron-to <target> --yes
  python setup.py --install-cron-setup --cron-install-governance-evolution-job --cron-governance-evolution-repo-path . --yes
  python setup.py setup --openclaw-home ~/.openclaw --scan-root .
  python setup.py cron-off
  python setup.py cron-on
  python setup.py cron-status
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def has_mode_arg(argv: list[str]) -> bool:
    if not argv:
        return False
    first = argv[0].strip().lower()
    return first in {"init", "setup"}


def has_scan_root_arg(argv: list[str]) -> bool:
    for idx, token in enumerate(argv):
        if token == "--scan-root":
            # supports: --scan-root .
            return idx + 1 < len(argv)
        if token.startswith("--scan-root="):
            return True
    return False


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    workflow_setup_py = repo_root / "scripts" / "openclaw-ops" / "policy" / "workflow_setup.py"
    cron_switch_py = repo_root / "scripts" / "openclaw-ops" / "cron_switch.py"
    if not workflow_setup_py.exists():
        print(f"[setup] missing file: {workflow_setup_py}")
        return 2
    if not cron_switch_py.exists():
        print(f"[setup] missing file: {cron_switch_py}")
        return 2

    args = list(sys.argv[1:])
    if args:
        head = args[0].strip().lower()
        if head in {"cron-off", "cron-on", "cron-status"}:
            action = {"cron-off": "off", "cron-on": "on", "cron-status": "status"}[head]
            cmd = [sys.executable, str(cron_switch_py), action, *args[1:]]
            proc = subprocess.run(cmd, cwd=str(repo_root), check=False)
            return int(proc.returncode)

    if not has_mode_arg(args):
        args.insert(0, "init")
    if not has_scan_root_arg(args):
        args.extend(["--scan-root", "."])

    cmd = [sys.executable, str(workflow_setup_py), *args]
    proc = subprocess.run(cmd, cwd=str(repo_root), check=False)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
