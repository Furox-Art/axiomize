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
    """Parse untrusted UTF-8 JSON with unique keys and valid Unicode scalars."""
    if isinstance(raw, bytes):
        # JSON's stdlib autodetection also accepts UTF-16/UTF-32 inputs;
        # our REST and MCP transports require UTF-8 on the wire.
        raw = raw.decode("utf-8")
    value = json.loads(
        raw,
        object_pairs_hook=_unique_object_keys,
        parse_float=_finite_float,
        parse_constant=_reject_nonstandard_constant,
    )
    try:
        # Escaped lone UTF-16 surrogates are valid json.loads input but cannot
        # be sent back as UTF-8; fail before reflecting an invalid request id.
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("JSON contains invalid Unicode scalars") from exc
    return value
