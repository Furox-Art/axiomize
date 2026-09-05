"""Hard, interface-independent safety limits for Axiomize.

Approval gates control *policy* (whether expensive work may begin).  These limits
are separate resource-safety ceilings and cannot be bypassed with an approval
flag.  Keep them conservative enough for scientific work while preventing an
accidental or hostile request from allocating unbounded memory/CPU.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_MCP_MESSAGE_BYTES = 2 * 1024 * 1024
MAX_RUN_JSON_BYTES = 16 * 1024 * 1024
MAX_PROVIDER_RESPONSE_BYTES = 8 * 1024 * 1024

MAX_POINTS = 200_000
MAX_SAMPLES = 100_000
MAX_ARRAY_ITEMS = 200_000
MAX_SCAN_VALUES = 10_000
MAX_QUANTILES = 101
MAX_MODEL_VARIABLES = 1_000
MAX_MODEL_PARAMETERS = 2_000
MAX_MODEL_EQUATIONS = 2_000
MAX_MODEL_CONSTRAINTS = 2_000
MAX_MODEL_COMPONENTS = 64

# Dense network execution currently materializes an n x n adjacency matrix.
MAX_DENSE_NETWORK_NODES = 2_000
# History-like arrays should stay well below a multi-GB accidental allocation.
MAX_RESULT_CELLS = 10_000_000
MAX_CONTROL_DIMENSION = 2_048
MAX_BAYES_DRAWS = 100_000
MAX_OPTIMIZER_ITERATIONS = 100_000

MAX_EXPRESSION_CHARS = 8_192
MAX_EXPRESSION_NODES = 512
MAX_EXPRESSION_DEPTH = 40
MAX_INTEGER_DIGITS = 64
MAX_ABS_CONSTANT_EXPONENT = 1_000.0


def bounded_int(value: Any, *, name: str, minimum: int = 0, maximum: int) -> int:
    """Coerce an integer-like value and enforce an inclusive hard range."""
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if result < minimum or result > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}; got {result}")
    return result


def bounded_float(
    value: Any,
    *,
    name: str,
    minimum: float | None = None,
    maximum: float | None = None,
    minimum_inclusive: bool = True,
) -> float:
    """Coerce a finite float and enforce optional hard bounds."""
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if minimum is not None:
        bad = result < minimum if minimum_inclusive else result <= minimum
        if bad:
            op = ">=" if minimum_inclusive else ">"
            raise ValueError(f"{name} must be {op} {minimum}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return result


def bounded_sequence(
    values: Any,
    *,
    name: str,
    minimum: int = 0,
    maximum: int = MAX_ARRAY_ITEMS,
) -> list[Any]:
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{name} must be an array")
    size = len(values)
    if size < minimum or size > maximum:
        raise ValueError(f"{name} length must be between {minimum} and {maximum}; got {size}")
    return list(values)


def enforce_result_cells(*dimensions: int, name: str = "requested result") -> None:
    cells = 1
    for raw in dimensions:
        dim = int(raw)
        if dim < 0:
            raise ValueError(f"{name} dimension cannot be negative")
        cells *= dim
        if cells > MAX_RESULT_CELLS:
            raise ValueError(
                f"{name} would contain {cells} numeric cells, exceeding hard safety limit "
                f"{MAX_RESULT_CELLS}"
            )


def enforce_finite_values(values: Iterable[Any], *, name: str) -> None:
    for index, value in enumerate(values):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{name}[{index}] must be numeric") from exc
        if not math.isfinite(number):
            raise ValueError(f"{name}[{index}] must be finite")
