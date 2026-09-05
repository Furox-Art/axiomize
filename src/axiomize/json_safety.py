"""Helpers for standards-compliant JSON at interface boundaries.

Python's default JSON encoder emits NaN/Infinity, which RFC 8259 JSON does not
permit. Scientific diagnostics may legitimately contain non-finite sentinels,
so convert them to explicit strings rather than crashing the REST/CLI adapter or
silently emitting invalid JSON.
"""

from __future__ import annotations

import math
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return value
    if isinstance(value, Enum):
        return json_safe(value.value)
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [json_safe(item) for item in value]

    # NumPy scalar/array support without making numpy a hard dependency here.
    item = getattr(value, "item", None)
    if callable(item):
        try:
            converted = item()
        except (TypeError, ValueError):
            converted = value
        if converted is not value:
            return json_safe(converted)
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        try:
            converted = tolist()
        except (TypeError, ValueError):
            converted = value
        if converted is not value:
            return json_safe(converted)
    return str(value)
