#!/usr/bin/env python3
"""Deprecated workflow profile installer.

The historical implementation invoked cron_setup.py and multiple install_*_job.py
scripts that were removed by the skillized architecture migration. Keep this
tiny compatibility guard so stale automation fails loudly instead of attempting
to install a broken workflow chain.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


REPLACEMENT = (
    "Use the Phase 6 project-delivery-pipeline skillized entrypoint instead: "
    "skills/library/project-delivery-pipeline/SKILL.md and "
    "skills/library/project-delivery-pipeline/scripts/pipeline_runner.py."
)


def build_deprecated_payload(argv: list[str] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "deprecated": True,
        "entrypoint": "openclaw-workflow-manager/scripts/install_workflow_profile.py",
        "reason": (
            "The old installer depended on removed cron_setup.py and install_*_job.py "
            "scripts, so it is no longer a valid installation surface."
        ),
        "replacement": REPLACEMENT,
        "received_args": list(argv or []),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Deprecated OpenClaw workflow profile installer.",
        add_help=True,
    )
    parser.add_argument("--emit-json", action="store_true", help="emit machine-readable deprecation payload")
    args, unknown = parser.parse_known_args(argv)
    payload = build_deprecated_payload(unknown)

    if args.emit_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("ERROR: deprecated workflow installer", file=sys.stderr)
        print(payload["reason"], file=sys.stderr)
        print(REPLACEMENT, file=sys.stderr)

    raise SystemExit(2)


if __name__ == "__main__":
    main()
