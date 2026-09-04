"""SciPy numerical adapter (PHASE 1).

Wraps solve_ivp / brentq so a solver's ``success=True`` is never trusted
alone: every solution ships with its conservation error and ODE residual.
"""

from __future__ import annotations

import math
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


def _validate_sir_parameters(
    beta: float,
    gamma: float,
    I0: float,
    N: float,
    days: float,
    rtol: float,
    atol: float,
) -> tuple[float, float, float, float, float, float, float]:
    """Validate the physical and numerical domain of an SIR solve."""
    try:
        beta_f = float(beta)
        gamma_f = float(gamma)
        i0_f = float(I0)
        n_f = float(N)
        days_f = float(days)
        rtol_f = float(rtol)
        atol_f = float(atol)
    except (TypeError, ValueError) as exc:
        raise ValueError("SIR parameters must be numeric") from exc

    values = (beta_f, gamma_f, i0_f, n_f, days_f, rtol_f, atol_f)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("SIR parameters must be finite")
    if beta_f < 0:
        raise ValueError("transmission rate beta must be non-negative")
    if gamma_f < 0:
        raise ValueError("recovery rate gamma must be non-negative")
    if n_f <= 0:
        raise ValueError("population N must be positive")
    if not 0 <= i0_f <= n_f:
        raise ValueError("I0 must satisfy 0 <= I0 <= N")
    if days_f <= 0:
        raise ValueError("days must be positive")
    if rtol_f <= 0 or atol_f <= 0:
        raise ValueError("rtol and atol must be positive")
    return beta_f, gamma_f, i0_f, n_f, days_f, rtol_f, atol_f


def solve_sir(beta: float, gamma: float, I0: float, N: float,
              days: float = 180.0, method: str = "RK45",
              rtol: float = 1e-9, atol: float = 1e-11) -> OdeResult:
    from scipy.integrate import solve_ivp  # type: ignore[import-untyped]

    beta, gamma, I0, N, days, rtol, atol = _validate_sir_parameters(
        beta, gamma, I0, N, days, rtol, atol
    )
    t_eval = np.linspace(0.0, days, 2000)
    sol = solve_ivp(_sir_rhs, (0.0, days), [N - I0, I0, 0.0],
                    args=(beta, gamma, N), method=method,
                    t_eval=t_eval, rtol=rtol, atol=atol)
    y = np.asarray(sol.y, dtype=float)
    t = np.asarray(sol.t, dtype=float)

    if y.ndim != 2 or y.shape[0] != 3 or y.shape[1] == 0:
        return OdeResult(
            success=False,
            method=method,
            t=t,
            y=y,
            final_size=math.nan,
            max_conservation_error=math.inf,
            max_residual=math.inf,
        )

    conservation = float(np.max(np.abs(y[0] + y[1] + y[2] - N)))
    # Residual on a dense uniform grid with central differences, normalized
    # by N so the check is scale-invariant (per-capita defect).
    if y.shape[1] < 2:
        residual = math.inf
    else:
        dydt = np.gradient(y, t, axis=1)
        rhs = np.array([_sir_rhs(tt, y[:, k], beta, gamma, N)
                        for k, tt in enumerate(t)]).T
        residual = float(np.max(np.abs(dydt - rhs)) / N)

    final_size = float(y[2][-1] / N)
    diagnostics_finite = all(
        math.isfinite(value) for value in (final_size, conservation, residual)
    )
    return OdeResult(success=bool(sol.success and diagnostics_finite), method=method, t=t, y=y,
                     final_size=final_size,
                     max_conservation_error=conservation, max_residual=residual)


def final_size_numeric(beta: float, gamma: float) -> float:
    """Final size via SciPy brentq on z = 1 - exp(-R0 z)."""
    try:
        beta_f = float(beta)
        gamma_f = float(gamma)
    except (TypeError, ValueError) as exc:
        raise ValueError("beta and gamma must be numeric") from exc
    if not math.isfinite(beta_f) or not math.isfinite(gamma_f):
        raise ValueError("beta and gamma must be finite")
    if beta_f < 0:
        raise ValueError("beta must be non-negative")
    if gamma_f <= 0:
        raise ValueError("gamma must be positive for final-size theory")

    r0 = beta_f / gamma_f
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
            _validate_sir_parameters(
                payload["beta"],
                payload["gamma"],
                payload.get("I0", 10.0),
                payload["N"],
                payload.get("days", 180.0),
                payload.get("rtol", 1e-9),
                payload.get("atol", 1e-11),
            )

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_input(payload)
        action = payload.get("action", "solve_sir")
        if action == "solve_sir":
            res = solve_sir(payload["beta"], payload["gamma"],
                            float(payload.get("I0", 10.0)), float(payload["N"]),
                            days=float(payload.get("days", 180.0)),
                            method=str(payload.get("method", "RK45")),
                            rtol=float(payload.get("rtol", 1e-9)),
                            atol=float(payload.get("atol", 1e-11)))
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
