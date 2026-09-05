"""1D heat-equation reference solver (PHASE 6).

Explicit FTCS finite differences with an enforced CFL stability bound and hard
space/time work ceilings. Solves u_t = alpha u_xx on [0, L] with zero Dirichlet
boundaries and a sine initial condition.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from axiomize.limits import MAX_POINTS, MAX_RESULT_CELLS, bounded_int

MAX_FTCS_STEPS = 1_000_000
MAX_FTCS_WORK_UNITS = MAX_RESULT_CELLS


def _finite(value: Any, *, name: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(out):
        raise ValueError(f"{name} must be finite")
    return out


def heat_ftcs(alpha: float, length: float, nx: int, dt: float,
              t_end: float) -> dict[str, Any]:
    alpha = _finite(alpha, name="alpha")
    length = _finite(length, name="length")
    dt = _finite(dt, name="dt")
    t_end = _finite(t_end, name="t_end")
    nx = bounded_int(nx, name="nx", minimum=3, maximum=MAX_POINTS)
    if alpha < 0:
        raise ValueError("alpha must be non-negative")
    if length <= 0:
        raise ValueError("length must be positive")
    if dt <= 0:
        raise ValueError("dt must be positive")
    if t_end < 0:
        raise ValueError("t_end must be non-negative")
    raw_steps = t_end / dt
    if not math.isfinite(raw_steps) or raw_steps > MAX_FTCS_STEPS + 0.5:
        raise ValueError(f"FTCS step count exceeds hard limit {MAX_FTCS_STEPS}")
    steps = int(round(raw_steps))
    if steps < 0 or steps > MAX_FTCS_STEPS:
        raise ValueError(f"FTCS step count must be in 0..{MAX_FTCS_STEPS}")

    # Per-axis limits alone are insufficient: nx=200k and steps=1M would imply
    # ~2e11 vector-cell updates. Bound their product before allocating/iterating.
    work_units = nx * steps
    if work_units > MAX_FTCS_WORK_UNITS:
        raise ValueError(
            f"FTCS grid-time work {work_units} exceeds hard limit {MAX_FTCS_WORK_UNITS} cell-steps"
        )

    dx = length / (nx - 1)
    cfl = alpha * dt / dx ** 2
    if cfl > 0.5:
        bound = dx ** 2 / (2 * alpha) if alpha > 0 else math.inf
        raise ValueError(f"unstable: CFL={cfl:.3f} > 1/2 (need dt <= {bound:.2e})")
    x = np.linspace(0, length, nx)
    u = np.sin(np.pi * x / length)
    for _ in range(steps):
        u[1:-1] = u[1:-1] + cfl * (u[2:] - 2 * u[1:-1] + u[:-2])
    exact = np.sin(np.pi * x / length) * np.exp(-alpha * (np.pi / length) ** 2 * steps * dt)
    error = float(np.sqrt(np.mean((u - exact) ** 2)))
    if not math.isfinite(error):
        raise RuntimeError("FTCS produced a non-finite error metric")
    return {
        "l2_error": error,
        "cfl": float(cfl),
        "nx": nx,
        "steps": steps,
        "work_units": work_units,
    }
