"""1D heat-equation reference solver (PHASE 6).

Explicit FTCS finite differences with an enforced CFL stability bound.
Solves u_t = alpha u_xx on [0, L] with zero Dirichlet boundaries and a
sine initial condition, whose analytic solution is known exactly - so
convergence is verifiable, not asserted.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def heat_ftcs(alpha: float, length: float, nx: int, dt: float,
              t_end: float) -> dict[str, Any]:
    dx = length / (nx - 1)
    cfl = alpha * dt / dx ** 2
    if cfl > 0.5:
        raise ValueError(
            f"unstable: CFL={cfl:.3f} > 1/2 (need dt <= dx^2/(2*alpha)={dx ** 2 / (2 * alpha):.2e})")
    x = np.linspace(0, length, nx)
    u = np.sin(np.pi * x / length)
    steps = round(t_end / dt)
    for _ in range(steps):
        u[1:-1] = u[1:-1] + cfl * (u[2:] - 2 * u[1:-1] + u[:-2])
    exact = np.sin(np.pi * x / length) * np.exp(-alpha * (np.pi / length) ** 2 * steps * dt)
    return {"l2_error": float(np.sqrt(np.mean((u - exact) ** 2))),
            "cfl": cfl, "nx": nx, "steps": steps}
