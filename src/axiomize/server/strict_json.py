"""Fail-closed JSON decoding for untrusted REST and MCP request bodies."""

from __future__ import annotations

import json
import math
from typing import Any


def _unique_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    decoded: dict[str, Any] = {}
    for key, value in pairs:
        if key in decoded:
            raise ValueError("duplicate JSON object key")
        decoded[key] = value
    return decoded


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite JSON number")
    return number


def _reject_nonstandard_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def loads(raw: str | bytes) -> Any:
    """Parse RFC-compliant JSON with unambiguous nested object keys."""
    return json.loads(
        raw,
        object_pairs_hook=_unique_object_keys,
        parse_float=_finite_float,
        parse_constant=_reject_nonstandard_constant,
    )
