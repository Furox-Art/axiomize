"""Sensitivity analysis (PHASE 5/12).

Local derivative-based indices plus a Monte Carlo screening based on
correlation. Direct calls enforce finite inputs and hard sample/dimension limits.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

from axiomize.limits import MAX_SAMPLES, bounded_int

_MAX_SENSITIVITY_PARAMETERS = 64


def _finite(value, *, name):
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(out):
        raise ValueError(f"{name} must be finite")
    return out


def _validated_params(params):
    if not isinstance(params, dict) or not params or len(params) > _MAX_SENSITIVITY_PARAMETERS:
        raise ValueError(f"params must contain 1..{_MAX_SENSITIVITY_PARAMETERS} entries")
    return {str(name): _finite(value, name=f"params.{name}") for name, value in params.items()}


def local_sensitivity(func: Callable[[dict[str, float]], float],
                      params: dict[str, float],
                      rel_step: float = 1e-6) -> dict[str, float]:
    """Normalized local sensitivities (dY/Y)/(dp/p) at a point."""
    params = _validated_params(params)
    rel_step = _finite(rel_step, name="rel_step")
    if rel_step <= 0 or rel_step > 1:
        raise ValueError("rel_step must be in (0, 1]")
    base = _finite(func(dict(params)), name="base model output")
    scale = abs(base) if base != 0 else 1.0
    out = {}
    for name, value in params.items():
        step = rel_step * max(abs(value), 1e-12)
        up = dict(params)
        up[name] = value + step
        shifted = _finite(func(up), name=f"model output for {name}")
        deriv = (shifted - base) / step
        index = deriv * (abs(value) / scale)
        if not math.isfinite(index):
            raise ValueError(f"non-finite local sensitivity for {name}")
        out[name] = float(index)
    return out


def mc_sensitivity(func: Callable[[dict[str, float]], float],
                   bounds: dict[str, tuple[float, float]],
                   n: int = 2000, seed: int = 0) -> dict[str, float]:
    """Screening indices from absolute Pearson correlation, normalized to 1."""
    if not isinstance(bounds, dict) or not bounds or len(bounds) > _MAX_SENSITIVITY_PARAMETERS:
        raise ValueError(f"bounds must contain 1..{_MAX_SENSITIVITY_PARAMETERS} entries")
    n = bounded_int(n, name="sensitivity samples", minimum=2, maximum=MAX_SAMPLES)
    normalized = {}
    for name, raw in bounds.items():
        if not isinstance(raw, (tuple, list)) or len(raw) != 2:
            raise ValueError(f"bounds.{name} must be [low, high]")
        low = _finite(raw[0], name=f"bounds.{name}.low")
        high = _finite(raw[1], name=f"bounds.{name}.high")
        if high <= low:
            raise ValueError(f"bounds.{name} high must exceed low")
        normalized[str(name)] = (low, high)

    rng = np.random.default_rng(seed)
    names = list(normalized.keys())
    cols = {name: rng.uniform(low, high, n) for name, (low, high) in normalized.items()}
    y = np.empty(n, dtype=float)
    for i in range(n):
        y[i] = _finite(func({name: float(cols[name][i]) for name in names}), name=f"model output[{i}]")
    weights = {}
    for name in names:
        x = cols[name]
        if np.std(x) == 0 or np.std(y) == 0:
            weights[name] = 0.0
        else:
            value = abs(float(np.corrcoef(x, y)[0, 1]))
            weights[name] = value if math.isfinite(value) else 0.0
    total = sum(weights.values()) or 1.0
    return {name: float(weight / total) for name, weight in weights.items()}
