"""Sensitivity analysis (PHASE 5/12).

Local derivative-based indices plus a Monte Carlo screening based on
rank correlation. The global adapter slot accepts heavier methods
(e.g. SALib Sobol) later without changing this interface.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np


def local_sensitivity(func: Callable[[dict[str, float]], float],
                      params: dict[str, float],
                      rel_step: float = 1e-6) -> dict[str, float]:
    """Normalized local sensitivities (dY/Y)/(dp/p) at a point."""
    base = float(func(dict(params)))
    scale = abs(base) if base != 0 else 1.0
    out = {}
    for name, value in params.items():
        step = rel_step * max(abs(value), 1e-12)
        up = dict(params)
        up[name] = value + step
        deriv = (float(func(up)) - base) / step
        out[name] = deriv * (abs(value) / scale)
    return out


def mc_sensitivity(func: Callable[[dict[str, float]], float],
                   bounds: dict[str, tuple[float, float]],
                   n: int = 2000, seed: int = 0) -> dict[str, float]:
    """Screening indices from absolute Pearson correlation, normalized to 1."""
    rng = np.random.default_rng(seed)
    names = list(bounds.keys())
    cols = {name: rng.uniform(low, high, n) for name, (low, high) in bounds.items()}
    y = np.array([func({name: cols[name][i] for name in names}) for i in range(n)])
    weights = {}
    for name in names:
        x = cols[name]
        if np.std(x) == 0 or np.std(y) == 0:
            weights[name] = 0.0
        else:
            weights[name] = abs(float(np.corrcoef(x, y)[0, 1]))
    total = sum(weights.values()) or 1.0
    return {name: w / total for name, w in weights.items()}
