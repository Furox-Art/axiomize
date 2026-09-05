"""SciPy numerical adapter (PHASE 1).

Wraps solve_ivp / brentq so a solver's ``success=True`` is never trusted alone:
every solution ships with conservation and residual checks. Direct calls also
enforce a finite physical/numerical domain to prevent pathological solver work.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np

from axiomize.tools.base import ScientificTool

_ALLOWED_METHODS = frozenset({"RK45", "RK23", "DOP853", "Radau", "BDF", "LSODA"})
_MAX_RATE_PER_DAY = 1e6
_MAX_POPULATION = 1e15
_MAX_DAYS = 1e9
_MIN_RTOL = 1e-14
_MIN_ATOL = 1e-16


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
    infection = beta * s * (i / n)
    return [-infection, infection - gamma * i, gamma * i]


def _validate_sir_parameters(
    beta: float,
    gamma: float,
    I0: float,
    N: float,
    days: float,
    rtol: float,
    atol: float,
) -> tuple[float, float, float, float, float, float, float]:
    try:
        beta_f = float(beta); gamma_f = float(gamma); i0_f = float(I0); n_f = float(N)
        days_f = float(days); rtol_f = float(rtol); atol_f = float(atol)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("SIR parameters must be numeric") from exc
    values = (beta_f, gamma_f, i0_f, n_f, days_f, rtol_f, atol_f)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("SIR parameters must be finite")
    if beta_f < 0 or beta_f > _MAX_RATE_PER_DAY:
        raise ValueError(f"beta must be in [0, {_MAX_RATE_PER_DAY:g}] per day")
    if gamma_f < 0 or gamma_f > _MAX_RATE_PER_DAY:
        raise ValueError(f"gamma must be in [0, {_MAX_RATE_PER_DAY:g}] per day")
    if n_f <= 0 or n_f > _MAX_POPULATION:
        raise ValueError(f"population N must be in (0, {_MAX_POPULATION:g}]")
    if not 0 <= i0_f <= n_f:
        raise ValueError("I0 must satisfy 0 <= I0 <= N")
    if days_f <= 0 or days_f > _MAX_DAYS:
        raise ValueError(f"days must be in (0, {_MAX_DAYS:g}]")
    if not _MIN_RTOL <= rtol_f <= 1:
        raise ValueError(f"rtol must be in [{_MIN_RTOL:g}, 1]")
    if not _MIN_ATOL <= atol_f <= 1:
        raise ValueError(f"atol must be in [{_MIN_ATOL:g}, 1]")
    return beta_f, gamma_f, i0_f, n_f, days_f, rtol_f, atol_f


def solve_sir(beta: float, gamma: float, I0: float, N: float,
              days: float = 180.0, method: str = "RK45",
              rtol: float = 1e-9, atol: float = 1e-11) -> OdeResult:
    from scipy.integrate import solve_ivp  # type: ignore[import-untyped]

    beta, gamma, I0, N, days, rtol, atol = _validate_sir_parameters(beta, gamma, I0, N, days, rtol, atol)
    method = str(method)
    if method not in _ALLOWED_METHODS:
        raise ValueError(f"method must be one of {sorted(_ALLOWED_METHODS)}")
    t_eval = np.linspace(0.0, days, 2000)
    sol = solve_ivp(
        _sir_rhs,
        (0.0, days),
        [N - I0, I0, 0.0],
        args=(beta, gamma, N),
        method=method,
        t_eval=t_eval,
        rtol=rtol,
        atol=atol,
    )
    y = np.asarray(sol.y, dtype=float)
    t = np.asarray(sol.t, dtype=float)
    if y.ndim != 2 or y.shape[0] != 3 or y.shape[1] == 0 or not np.all(np.isfinite(y)) or not np.all(np.isfinite(t)):
        return OdeResult(False, method, t, y, math.nan, math.inf, math.inf)

    conservation = float(np.max(np.abs(y[0] + y[1] + y[2] - N)))
    if y.shape[1] < 2:
        residual = math.inf
    else:
        dydt = np.gradient(y, t, axis=1)
        rhs = np.array([_sir_rhs(tt, y[:, k], beta, gamma, N) for k, tt in enumerate(t)]).T
        residual = float(np.max(np.abs(dydt - rhs)) / N)
    final_size = float(y[2][-1] / N)
    diagnostics_finite = all(math.isfinite(value) for value in (final_size, conservation, residual))
    return OdeResult(
        success=bool(sol.success and diagnostics_finite), method=method, t=t, y=y,
        final_size=final_size, max_conservation_error=conservation, max_residual=residual,
    )


def final_size_numeric(beta: float, gamma: float) -> float:
    """Final size via SciPy brentq on z = 1 - exp(-R0 z)."""
    beta_f, gamma_f, *_ = _validate_sir_parameters(beta, gamma, 0.0, 1.0, 1.0, 1e-9, 1e-11)
    if gamma_f <= 0:
        raise ValueError("gamma must be positive for final-size theory")
    r0 = beta_f / gamma_f
    if r0 <= 1:
        return 0.0
    from scipy.optimize import brentq  # type: ignore[import-untyped]
    return float(brentq(lambda z: z - (1 - np.exp(-r0 * z)), 1e-12, 1 - 1e-12))


class SciPyTool(ScientificTool):
    name: ClassVar[str] = "scipy"
    capabilities: ClassVar[list[str]] = ["ode_solve", "root_find", "optimize", "residual_check", "solver_agreement"]

    @classmethod
    def _probe_version(cls) -> str:
        import scipy  # type: ignore[import-untyped]
        return str(scipy.__version__)

    def validate_input(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise ValueError("scipy: payload must be an object")
        if payload.get("action", "solve_sir") == "solve_sir":
            for key in ("beta", "gamma", "N"):
                if key not in payload:
                    raise ValueError(f"scipy: solve_sir needs '{key}'")
            _validate_sir_parameters(
                payload["beta"], payload["gamma"], payload.get("I0", 10.0), payload["N"],
                payload.get("days", 180.0), payload.get("rtol", 1e-9), payload.get("atol", 1e-11),
            )
            if str(payload.get("method", "RK45")) not in _ALLOWED_METHODS:
                raise ValueError(f"scipy: method must be one of {sorted(_ALLOWED_METHODS)}")

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_input(payload)
        action = payload.get("action", "solve_sir")
        if action == "solve_sir":
            res = solve_sir(
                payload["beta"], payload["gamma"], payload.get("I0", 10.0), payload["N"],
                days=payload.get("days", 180.0), method=str(payload.get("method", "RK45")),
                rtol=payload.get("rtol", 1e-9), atol=payload.get("atol", 1e-11),
            )
            return {
                "success": res.success,
                "final_size": res.final_size,
                "max_conservation_error": res.max_conservation_error,
                "max_residual": res.max_residual,
            }
        raise ValueError(f"scipy: unknown action {action!r}")

    def metadata(self):  # type: ignore[override]
        return super().metadata()


def check_solver_agreement(first: OdeResult, second: OdeResult,
                           tolerance: float = 1e-3) -> tuple[bool, float]:
    try:
        tolerance = float(tolerance)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("tolerance must be numeric") from exc
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("tolerance must be finite and positive")
    if not math.isfinite(first.final_size) or not math.isfinite(second.final_size):
        return False, math.inf
    diff = abs(first.final_size - second.final_size)
    return diff < tolerance, diff
