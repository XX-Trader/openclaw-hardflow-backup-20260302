#!/usr/bin/env python3
"""Compatibility helpers for dataclass decorators across Python versions."""

from __future__ import annotations

import sys
from dataclasses import dataclass as stdlib_dataclass
from typing import Any


def compat_dataclass(*args: Any, **kwargs: Any):
    """Return a dataclass decorator compatible with Python < 3.10.

    Args:
        *args: Positional arguments forwarded to ``dataclasses.dataclass``.
        **kwargs: Keyword arguments forwarded to ``dataclasses.dataclass``.

    Returns:
        A dataclass decorator or decorated class from the stdlib implementation.

    Raises:
        TypeError: Propagated from ``dataclasses.dataclass`` for unsupported
            keyword combinations other than ``slots``.
    """

    normalized_kwargs = dict(kwargs)
    if sys.version_info < (3, 10):
        normalized_kwargs.pop("slots", None)
    return stdlib_dataclass(*args, **normalized_kwargs)
