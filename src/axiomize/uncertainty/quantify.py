"""Uncertainty quantification (PHASE 4).

The uncertainty classes are tracked separately and never folded into a single
unjustified number. Direct propagation calls enforce finite parameters and hard
sampling ceilings.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from axiomize.fitting.estimator import FitResult
from axiomize.limits import MAX_MODEL_PARAMETERS, MAX_SAMPLES, bounded_int, enforce_result_cells


def confidence_intervals(fit: FitResult, alpha: float = 0.05) -> dict[str, tuple[float, float]]:
    from scipy.stats import norm

    try:
        alpha = float(alpha)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("alpha must be numeric") from exc
    if not math.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("alpha must be finite and in (0, 1)")
    if len(fit.params) > MAX_MODEL_PARAMETERS:
        raise ValueError(f"fit parameter count exceeds hard limit {MAX_MODEL_PARAMETERS}")
    z = float(norm.ppf(1 - alpha / 2))
    intervals = {}
    for name, (value, err) in fit.params.items():
        value = float(value)
        err = float(err)
        if not math.isfinite(value) or not math.isfinite(err) or err < 0:
            raise ValueError(f"parameter {name!r} requires finite value and non-negative finite stderr")
        intervals[name] = (value - z * err, value + z * err)
    return intervals


def propagate(func: Callable[[dict[str, float]], float],
              params: dict[str, tuple[float, float]],
              n: int = 5000, seed: int = 0) -> dict[str, float]:
    if not isinstance(params, dict) or not params or len(params) > MAX_MODEL_PARAMETERS:
        raise ValueError(f"params must contain 1..{MAX_MODEL_PARAMETERS} entries")
    n = bounded_int(n, name="uncertainty samples", minimum=2, maximum=MAX_SAMPLES)
    enforce_result_cells(n, len(params), name="uncertainty parameter draws")
    normalized = {}
    for name, pair in params.items():
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError(f"params.{name} must be [value, stderr]")
        value, err = float(pair[0]), float(pair[1])
        if not math.isfinite(value) or not math.isfinite(err) or err < 0:
            raise ValueError(f"params.{name} requires finite value and non-negative stderr")
        normalized[str(name)] = (value, err)

    rng = np.random.default_rng(seed)
    names = list(normalized.keys())
    columns = {
        name: rng.normal(value, max(err, 1e-12), n)
        for name, (value, err) in normalized.items()
    }
    draws = np.empty(n, dtype=float)
    for i in range(n):
        value = float(func({name: float(columns[name][i]) for name in names}))
        if not math.isfinite(value):
            raise ValueError(f"uncertainty model output[{i}] is non-finite")
        draws[i] = value
    return {
        "mean": float(np.mean(draws)),
        "std": float(np.std(draws)),
        "p5": float(np.percentile(draws, 5)),
        "p95": float(np.percentile(draws, 95)),
    }


@dataclass
class UncertaintyReport:
    parameter: dict[str, Any] = field(default_factory=dict)
    measurement: dict[str, Any] = field(default_factory=dict)
    model: dict[str, Any] = field(default_factory=dict)
    numerical: dict[str, Any] = field(default_factory=dict)
    structural: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "measurement": self.measurement,
            "model": self.model,
            "numerical": self.numerical,
            "structural": self.structural,
            "data": self.data,
        }
