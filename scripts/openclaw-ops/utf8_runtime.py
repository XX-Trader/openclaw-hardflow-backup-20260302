#!/usr/bin/env python3
"""UTF-8 stdio helpers for cron-facing OpenClaw scripts."""

from __future__ import annotations

import os
import sys
from typing import Any


def _reconfigure_stream(stream: Any) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if not callable(reconfigure):
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        return


def configure_process_utf8_stdio() -> None:
    """Force UTF-8 stdio and child-process defaults for human-facing output."""
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONUTF8"] = "1"
    _reconfigure_stream(sys.stdout)
    _reconfigure_stream(sys.stderr)
