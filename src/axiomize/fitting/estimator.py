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


def _diagnostics(y: np.ndarray, fitted: np.ndarray, k: int) -> tuple[float, float, float, float]:
    resid = y - fitted
    n = len(y)
    rss = max(float(np.sum(resid ** 2)), 1e-300)
    aic = n * math.log(rss / n) + 2 * k
    bic = n * math.log(rss / n) + k * math.log(n)
    ac = float(np.corrcoef(resid[:-1], resid[1:])[0, 1]) if n > 2 and np.std(resid) > 0 else 0.0
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    return rmse, aic, bic, ac


def fit_curve(model: Callable[..., np.ndarray], t: np.ndarray, y: np.ndarray,
              p0: list[float], param_names: list[str],
              bounds: tuple[list[float], list[float]] | None = None) -> FitResult:
    from scipy.optimize import curve_fit

    low = [-np.inf] * len(p0) if bounds is None else bounds[0]
    high = [np.inf] * len(p0) if bounds is None else bounds[1]
    try:
        popt, pcov = curve_fit(model, t, y, p0=p0, bounds=(low, high), maxfev=20000)
        perr = np.sqrt(np.diag(pcov))
        success = bool(np.all(np.isfinite(popt)))
    except (RuntimeError, ValueError):
        popt = np.array(p0, dtype=float)
        perr = np.full(len(p0), np.inf)
        success = False
    fitted = np.asarray(model(t, *popt), dtype=float)
    rmse, aic, bic, ac = _diagnostics(np.asarray(y, dtype=float), fitted, len(p0))
    ok = bool(success and np.all(np.isfinite([rmse, aic, bic])))
    return FitResult(
        params={name: (float(v), float(e)) for name, v, e in zip(param_names, popt, perr)},
        rmse=rmse, aic=aic, bic=bic, resid_autocorr=ac,
        success=ok,
        method="bounded_least_squares", n=len(y), k=len(p0))


def fit_logistic_curve(t: np.ndarray, y: np.ndarray) -> FitResult:
    y0 = max(float(y[0]), 1e-9)
    k_guess = float(np.clip(y.max() * 1.2, y0 * 1.01, y0 * 1e6))

    def model(tt: np.ndarray, r: float, k: float) -> np.ndarray:
        return k / (1 + (k / y0 - 1) * np.exp(-r * (tt - t[0])))

    return fit_curve(model, t, y, p0=[0.3, k_guess], param_names=["r", "K"],
                     bounds=([1e-4, y0], [10.0, y0 * 1e6]))


def fit_sir_curve(t: np.ndarray, y: np.ndarray, N: float, I0: float) -> FitResult:
    from axiomize.tools.numerical.scipy_tool import solve_sir

    span = float(t[-1] - t[0])
    dense = np.linspace(0, span, 2000)

    def model(tt: np.ndarray, beta: float, gamma: float) -> np.ndarray:
        res = solve_sir(beta, gamma, I0, N, days=span)
        return np.interp(np.asarray(tt) - t[0], dense, res.y[1])
    return fit_curve(model, t, y, p0=[0.4, 0.15], param_names=["beta", "gamma"],
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
