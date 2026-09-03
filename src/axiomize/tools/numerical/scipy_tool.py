"""SciPy numerical adapter (PHASE 1).

Wraps solve_ivp / brentq so a solver's ``success=True`` is never trusted
alone: every solution ships with its conservation error and ODE residual.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np

from axiomize.tools.base import ScientificTool


@dataclass
class OdeResult:
    success: bool
    method: str
    t: Any
    y: Any
    final_size: float
    max_conservation_error: float
    max_residual: float


def _sir_rhs(_t: float, y: Any, beta: float, gamma: float, n: float) -> list[float]:
    s, i, _r = y
    return [-beta * s * i / n, beta * s * i / n - gamma * i, gamma * i]


def solve_sir(beta: float, gamma: float, I0: float, N: float,
              days: float = 180.0, method: str = "RK45",
              rtol: float = 1e-9, atol: float = 1e-11) -> OdeResult:
    from scipy.integrate import solve_ivp  # type: ignore[import-untyped]

    t_eval = np.linspace(0.0, days, 2000)
    sol = solve_ivp(_sir_rhs, (0.0, days), [N - I0, float(I0), 0.0],
                    args=(beta, gamma, float(N)), method=method,
                    t_eval=t_eval, rtol=rtol, atol=atol)
    y = sol.y
    conservation = float(np.max(np.abs(y[0] + y[1] + y[2] - N)))
    # Residual on a dense uniform grid with central differences, normalized
    # by N so the check is scale-invariant (per-capita defect).
    dydt = np.gradient(y, sol.t, axis=1)
    rhs = np.array([_sir_rhs(t, y[:, k], beta, gamma, float(N))
                    for k, t in enumerate(sol.t)]).T
    residual = float(np.max(np.abs(dydt - rhs)) / N)
    return OdeResult(success=bool(sol.success), method=method, t=sol.t, y=y,
                     final_size=float(y[2][-1] / N),
                     max_conservation_error=conservation, max_residual=residual)


def final_size_numeric(beta: float, gamma: float) -> float:
    """Final size via SciPy brentq on z = 1 - exp(-R0 z)."""
    r0 = beta / gamma
    if r0 <= 1:
        return 0.0
    from scipy.optimize import brentq  # type: ignore[import-untyped]

    return float(brentq(lambda z: z - (1 - np.exp(-r0 * z)), 1e-12, 1 - 1e-12))


class SciPyTool(ScientificTool):
    name: ClassVar[str] = "scipy"
    capabilities: ClassVar[list[str]] = ["ode_solve", "root_find", "optimize", "residual_check",
                    "solver_agreement"]

    @classmethod
    def _probe_version(cls) -> str:
        import scipy  # type: ignore[import-untyped]

        return str(scipy.__version__)

    def validate_input(self, payload: dict[str, Any]) -> None:
        if payload.get("action") == "solve_sir":
            for key in ("beta", "gamma", "N"):
                if key not in payload:
                    raise ValueError(f"scipy: solve_sir needs '{key}'")
            if payload["N"] <= 0:
                raise ValueError("scipy: population N must be positive")

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_input(payload)
        action = payload.get("action", "solve_sir")
        if action == "solve_sir":
            res = solve_sir(payload["beta"], payload["gamma"],
                            float(payload.get("I0", 10.0)), float(payload["N"]),
                            days=float(payload.get("days", 180.0)),
                            method=str(payload.get("method", "RK45")))
            return {"success": res.success, "final_size": res.final_size,
                    "max_conservation_error": res.max_conservation_error,
                    "max_residual": res.max_residual}
        raise ValueError(f"scipy: unknown action {action!r}")

    def metadata(self):  # type: ignore[override]
        return super().metadata()


def check_solver_agreement(first: OdeResult, second: OdeResult,
                           tolerance: float = 1e-3) -> tuple[bool, float]:
    diff = abs(first.final_size - second.final_size)
    return diff < tolerance, diff
