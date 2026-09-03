"""scientific-computing-system integrations (PHASE 7).

The SCS packages are reference/cross-validation backends behind this
adapter - never forced, always probed. If neither is installed the
adapter says TOOL_UNAVAILABLE instead of faking agreement.
"""

from __future__ import annotations

import importlib.util
from typing import Any

import numpy as np

from axiomize.validation.cross import CrossResult, compare_values, unavailable


def scs_probe() -> dict[str, bool]:
    return {
        "cds": importlib.util.find_spec("cds") is not None,
        "cds2": importlib.util.find_spec("cds2") is not None,
    }


def solve_sir_cds(beta: float, gamma: float, I0: float, N: float,
                  days: float = 60.0, dt: float = 0.05) -> dict[str, Any]:
    """SIR integration with the zero-dependency ``cds`` backend."""
    from cds.diffeq import solve_system

    def rhs(t: float, y: list[float]) -> list[float]:
        s, i, _r = y
        return [-beta * s * i / N, beta * s * i / N - gamma * i, gamma * i]

    times, states = solve_system(rhs, 0.0, [N - I0, float(I0), 0.0], days, dt)
    arr = np.array(states)
    return {"t": times, "final_size": float(arr[-1, 2] / N)}


def cross_validate_sir(beta: float, gamma: float, I0: float, N: float,
                       days: float = 60.0, tolerance: float = 2e-2) -> CrossResult:
    """scipy (primary) vs cds (independent verification) on final size."""
    from axiomize.tools.numerical.scipy_tool import solve_sir

    if not scs_probe()["cds"]:
        return unavailable("scientific-computing-system")
    primary = solve_sir(beta, gamma, I0, N, days=days).final_size
    verification = solve_sir_cds(beta, gamma, I0, N, days=days)["final_size"]
    return compare_values(primary, verification, tolerance, name="sir_final_size(cds)")
