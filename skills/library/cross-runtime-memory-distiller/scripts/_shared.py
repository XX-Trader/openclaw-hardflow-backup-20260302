#!/usr/bin/env python3
"""蒸馏技能共享工具函数。

避免各模块重复实现相同的基础设施代码（如 UTF-8 配置、路径解析）。
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
CONFIG_DIR = SKILL_DIR / "config"


def configure_utf8_stdio() -> None:
    """尽量复用仓库现有 UTF-8 运行时配置。

    查找共享目录下的 utf8_runtime 模块，找不到时静默降级，不影响功能。
    """
    shared_dir = SCRIPT_DIR.parents[3] / "scripts" / "openclaw-ops" / "shared"
    if str(shared_dir) not in sys.path:
        sys.path.insert(0, str(shared_dir))
    try:
        from utf8_runtime import configure_process_utf8_stdio  # type: ignore
    except Exception:
        return
    configure_process_utf8_stdio()
