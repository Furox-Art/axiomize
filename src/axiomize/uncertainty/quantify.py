"""Uncertainty quantification (PHASE 4).

The six uncertainty classes are tracked separately and never folded
into a single unjustified number.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from axiomize.fitting.estimator import FitResult


def confidence_intervals(fit: FitResult, alpha: float = 0.05) -> dict[str, tuple[float, float]]:
    from scipy.stats import norm

    z = float(norm.ppf(1 - alpha / 2))
    return {name: (value - z * err, value + z * err)
            for name, (value, err) in fit.params.items()}


def propagate(func: Callable[[dict[str, float]], float],
              params: dict[str, tuple[float, float]],
              n: int = 5000, seed: int = 0) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    names = list(params.keys())
    columns = {name: rng.normal(value, max(err, 1e-12), n)
               for name, (value, err) in params.items()}
    draws = np.array([func({name: columns[name][i] for name in names})
                      for i in range(n)], dtype=float)
    return {"mean": float(np.mean(draws)), "std": float(np.std(draws)),
            "p5": float(np.percentile(draws, 5)),
            "p95": float(np.percentile(draws, 95))}


@dataclass
class UncertaintyReport:
    parameter: dict[str, Any] = field(default_factory=dict)
    measurement: dict[str, Any] = field(default_factory=dict)
    model: dict[str, Any] = field(default_factory=dict)
    numerical: dict[str, Any] = field(default_factory=dict)
    structural: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"parameter": self.parameter, "measurement": self.measurement,
                "model": self.model, "numerical": self.numerical,
                "structural": self.structural, "data": self.data}
