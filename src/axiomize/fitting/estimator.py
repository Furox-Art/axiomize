"""Parameter fitting engine (PHASE 3).

Automatic method choice for small problems: bounded least squares via
``curve_fit`` with covariance-based standard errors, AIC/BIC diagnostics
and residual-autocorrelation flags. Model comparison ranks candidates by
BIC on the same data.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class FitResult:
    params: dict[str, tuple[float, float]]
    rmse: float
    aic: float
    bic: float
    resid_autocorr: float
    success: bool
    method: str
    n: int
    k: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "params": {k: {"value": v, "stderr": e} for k, (v, e) in self.params.items()},
            "rmse": self.rmse, "aic": self.aic, "bic": self.bic,
            "resid_autocorr": self.resid_autocorr, "success": self.success,
            "method": self.method, "n": self.n, "k": self.k,
        }


def _coerce_xy(
    t: np.ndarray,
    y: np.ndarray,
    *,
    require_increasing: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Return validated one-dimensional finite data arrays."""
    t_arr = np.asarray(t, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    if t_arr.ndim != 1 or y_arr.ndim != 1:
        raise ValueError("t and y must be one-dimensional")
    if len(t_arr) != len(y_arr):
        raise ValueError("t and y must have the same length")
    if len(t_arr) < 2:
        raise ValueError("at least two observations are required")
    if not np.all(np.isfinite(t_arr)) or not np.all(np.isfinite(y_arr)):
        raise ValueError("t and y must contain only finite values")
    if require_increasing and np.any(np.diff(t_arr) <= 0):
        raise ValueError("t must be strictly increasing")
    return t_arr, y_arr


def _validate_fit_spec(
    t: np.ndarray,
    p0: list[float],
    param_names: list[str],
    bounds: tuple[list[float], list[float]] | None,
) -> tuple[np.ndarray, np.ndarray]:
    if not p0:
        raise ValueError("p0 must contain at least one parameter")
    if len(param_names) != len(p0):
        raise ValueError("param_names must have the same length as p0")
    if len(set(param_names)) != len(param_names):
        raise ValueError("param_names must be unique")
    p0_arr = np.asarray(p0, dtype=float)
    if not np.all(np.isfinite(p0_arr)):
        raise ValueError("p0 must contain only finite values")
    if len(t) < len(p0):
        raise ValueError("number of observations must be at least the number of parameters")

    if bounds is None:
        low = np.full(len(p0), -np.inf, dtype=float)
        high = np.full(len(p0), np.inf, dtype=float)
    else:
        if len(bounds) != 2 or len(bounds[0]) != len(p0) or len(bounds[1]) != len(p0):
            raise ValueError("bounds must contain lower/upper arrays matching p0")
        low = np.asarray(bounds[0], dtype=float)
        high = np.asarray(bounds[1], dtype=float)
        if np.any(np.isnan(low)) or np.any(np.isnan(high)):
            raise ValueError("bounds must not contain NaN")
        if np.any(low > high):
            raise ValueError("each lower bound must be <= its upper bound")
        if np.any(p0_arr < low) or np.any(p0_arr > high):
            raise ValueError("initial parameters p0 must lie within bounds")
    return low, high


def _lag1_autocorrelation(resid: np.ndarray) -> float:
    """Lag-1 correlation with deterministic handling of degenerate slices."""
    if len(resid) <= 2:
        return 0.0
    left = resid[:-1]
    right = resid[1:]
    if not np.all(np.isfinite(left)) or not np.all(np.isfinite(right)):
        return 0.0
    if np.std(left) == 0.0 or np.std(right) == 0.0:
        return 0.0
    value = float(np.corrcoef(left, right)[0, 1])
    return value if math.isfinite(value) else 0.0


def _diagnostics(y: np.ndarray, fitted: np.ndarray, k: int) -> tuple[float, float, float, float]:
    resid = y - fitted
    n = len(y)
    rss = max(float(np.sum(resid ** 2)), 1e-300)
    aic = n * math.log(rss / n) + 2 * k
    bic = n * math.log(rss / n) + k * math.log(n)
    ac = _lag1_autocorrelation(resid)
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    return rmse, aic, bic, ac


def fit_curve(model: Callable[..., np.ndarray], t: np.ndarray, y: np.ndarray,
              p0: list[float], param_names: list[str],
              bounds: tuple[list[float], list[float]] | None = None) -> FitResult:
    from scipy.optimize import curve_fit

    t_arr, y_arr = _coerce_xy(t, y)
    low, high = _validate_fit_spec(t_arr, p0, param_names, bounds)
    try:
        popt, pcov = curve_fit(
            model,
            t_arr,
            y_arr,
            p0=p0,
            bounds=(low, high),
            maxfev=20000,
        )
        diag = np.diag(pcov)
        with np.errstate(invalid="ignore"):
            perr = np.sqrt(np.where(diag >= 0.0, diag, np.inf))
        perr = np.where(np.isfinite(perr), perr, np.inf)
        success = bool(np.all(np.isfinite(popt)))
    except (RuntimeError, ValueError, TypeError, FloatingPointError, OverflowError):
        popt = np.array(p0, dtype=float)
        perr = np.full(len(p0), np.inf)
        success = False

    try:
        fitted = np.asarray(model(t_arr, *popt), dtype=float)
    except (ValueError, TypeError, FloatingPointError, OverflowError):
        fitted = np.full_like(y_arr, np.nan, dtype=float)

    if fitted.shape != y_arr.shape or not np.all(np.isfinite(fitted)):
        rmse = aic = bic = math.inf
        ac = 0.0
        success = False
    else:
        rmse, aic, bic, ac = _diagnostics(y_arr, fitted, len(p0))
    ok = bool(success and np.all(np.isfinite([rmse, aic, bic])))
    return FitResult(
        params={name: (float(v), float(e)) for name, v, e in zip(param_names, popt, perr)},
        rmse=rmse, aic=aic, bic=bic, resid_autocorr=ac,
        success=ok,
        method="bounded_least_squares", n=len(y_arr), k=len(p0))


def fit_logistic_curve(t: np.ndarray, y: np.ndarray) -> FitResult:
    t_arr, y_arr = _coerce_xy(t, y, require_increasing=True)
    y0 = max(float(y_arr[0]), 1e-9)
    k_guess = float(np.clip(y_arr.max() * 1.2, y0 * 1.01, y0 * 1e6))

    def model(tt: np.ndarray, r: float, k: float) -> np.ndarray:
        return k / (1 + (k / y0 - 1) * np.exp(-r * (tt - t_arr[0])))

    return fit_curve(model, t_arr, y_arr, p0=[0.3, k_guess], param_names=["r", "K"],
                     bounds=([1e-4, y0], [10.0, y0 * 1e6]))


def fit_sir_curve(t: np.ndarray, y: np.ndarray, N: float, I0: float) -> FitResult:
    from axiomize.tools.numerical.scipy_tool import solve_sir

    t_arr, y_arr = _coerce_xy(t, y, require_increasing=True)
    if not math.isfinite(float(N)) or N <= 0:
        raise ValueError("N must be finite and positive")
    if not math.isfinite(float(I0)) or not 0 <= I0 <= N:
        raise ValueError("I0 must be finite and satisfy 0 <= I0 <= N")
    span = float(t_arr[-1] - t_arr[0])

    def model(tt: np.ndarray, beta: float, gamma: float) -> np.ndarray:
        res = solve_sir(beta, gamma, I0, N, days=span)
        return np.interp(np.asarray(tt) - t_arr[0], np.asarray(res.t), res.y[1])

    return fit_curve(model, t_arr, y_arr, p0=[0.4, 0.15], param_names=["beta", "gamma"],
                     bounds=([1e-4, 1e-4], [10.0, 10.0]))


def compare_fits(candidates: dict[str, FitResult]) -> dict[str, Any]:
    ok = {name: res for name, res in candidates.items() if res.success}
    if not ok:
        return {"ranking": [], "best": None, "reason": "all fits failed"}
    ranking = sorted(ok, key=lambda name: ok[name].bic)
    best = ranking[0]
    return {
        "ranking": ranking,
        "best": best,
        "bic": {name: ok[name].bic for name in ranking},
        "reason": f"lowest BIC ({ok[best].bic:.2f}); physical plausibility must still be checked",
    }
