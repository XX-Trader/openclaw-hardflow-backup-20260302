#!/usr/bin/env python3
"""Root setup entry for the skillized project delivery runtime.

Examples:
  python setup.py
  python setup.py --dry-run
  python setup.py --runtime-home ~/.hardflow-runtime
  python setup.py --runtime-home ~/.openclaw --runtime-name openclaw
  python setup.py --runtime-home ~/.hermes --runtime-name hermes
  python setup.py rollback --runtime-home ~/.hardflow-runtime
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
    return first in {"install", "init", "setup", "rollback"}


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    runtime_installer_py = (
        repo_root
        / "skills"
        / "library"
        / "project-delivery-pipeline"
        / "scripts"
        / "runtime_installer.py"
    )
    cron_switch_py = repo_root / "skills" / "library" / "control-plane-ops" / "scripts" / "cron_switch.py"
    if not runtime_installer_py.exists():
        print(f"[setup] missing file: {runtime_installer_py}")
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
        args.insert(0, "install")
    if "--repo-root" not in args and not any(token.startswith("--repo-root=") for token in args):
        args.extend(["--repo-root", str(repo_root)])

    cmd = [sys.executable, str(runtime_installer_py), *args]
    proc = subprocess.run(cmd, cwd=str(repo_root), check=False)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
