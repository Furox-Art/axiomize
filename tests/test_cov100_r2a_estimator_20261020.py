"""Round-2 coverage hardening for ``axiomize.fitting.estimator``.

Drives the public fitting entry points with deterministic data and asserts the
typed refusals plus the failure-diagnostic contract (infinite information
criteria, zero autocorrelation, success=False) instead of optimistic output.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.fitting.estimator import (
    FitResult,
    _lag1_autocorrelation,
    compare_fits,
    fit_curve,
    fit_sir_curve,
)


def _linear(t: np.ndarray, a: float) -> np.ndarray:
    return a * np.asarray(t, dtype=float)


@pytest.mark.parametrize(
    ("t", "y", "p0", "names", "match"),
    [
        ([[1.0, 2.0], [3.0, 4.0]], [1.0, 2.0], [1.0], ["a"], "one-dimensional"),
        ([1.0, 2.0, 3.0], [1.0, 2.0], [1.0], ["a"], "same length"),
        ([1.0], [1.0], [1.0], ["a"], "at least two observations"),
    ],
)
def test_fit_curve_refuses_malformed_data(
    t: object, y: object, p0: list[float], names: list[str], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        fit_curve(_linear, t, y, p0, names)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("p0", "names", "bounds", "match"),
    [
        ([], [], None, "p0 must contain at least one parameter"),
        ([1.0, 2.0], ["a", "a"], None, "param_names must be unique"),
        ([math.nan], ["a"], None, "p0 must contain only finite values"),
        ([1.0, 2.0, 3.0, 4.0], ["a", "b", "c", "d"], None, "at least the number of parameters"),
        ([1.0, 2.0], ["a", "b"], ([0.0], [1.0]), "lower/upper arrays matching p0"),
        ([1.0, 2.0], ["a", "b"], ([math.nan, 0.0], [1.0, 1.0]), "must not contain NaN"),
        ([1.0, 2.0], ["a", "b"], ([2.0, 0.0], [1.0, 1.0]), "lower bound must be <="),
        ([1.5, 0.5], ["a", "b"], ([0.0, 0.0], [1.0, 1.0]), "must lie within bounds"),
    ],
)
def test_fit_curve_refuses_invalid_fit_specification(
    p0: list[float],
    names: list[str],
    bounds: tuple[list[float], list[float]] | None,
    match: str,
) -> None:
    def two_parameter(t, a, b):
        return a * np.asarray(t, dtype=float) + b

    with pytest.raises(ValueError, match=match):
        fit_curve(two_parameter, np.array([0.0, 1.0, 2.0]), np.array([0.0, 1.0, 2.0]),
                  p0, names, bounds)


def test_fit_curve_reports_failure_when_the_model_raises() -> None:
    def broken(t: np.ndarray, a: float) -> np.ndarray:
        raise ValueError("model cannot evaluate")

    result = fit_curve(broken, np.array([0.0, 1.0, 2.0, 3.0]),
                       np.array([1.0, 2.0, 3.0, 4.0]), [1.0], ["a"])
    assert result.success is False
    assert result.params["a"] == (1.0, math.inf)
    assert result.rmse == math.inf
    assert result.aic == math.inf
    assert result.bic == math.inf
    assert result.resid_autocorr == 0.0
    assert result.method == "bounded_least_squares"
    assert (result.n, result.k) == (4, 1)


def test_two_point_fit_has_zero_lag_one_autocorrelation() -> None:
    result = fit_curve(_linear, np.array([1.0, 2.0]), np.array([2.0, 4.0]), [1.0], ["a"])
    assert result.success is True
    assert result.params["a"][0] == pytest.approx(2.0)
    assert result.rmse == pytest.approx(0.0, abs=1e-12)
    assert result.resid_autocorr == 0.0


def test_lag1_autocorrelation_ignores_non_finite_series() -> None:
    assert _lag1_autocorrelation(np.array([1.0, math.nan, 2.0])) == 0.0
    assert _lag1_autocorrelation(np.array([1.0, 2.0])) == 0.0
    # A deterministic alternating series keeps the real correlation path intact.
    assert _lag1_autocorrelation(np.array([1.0, -1.0, 1.0, -1.0])) == pytest.approx(-1.0)


def test_fit_sir_curve_refuses_non_positive_population() -> None:
    t = np.array([0.0, 1.0, 2.0])
    y = np.array([1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="N must be finite and positive"):
        fit_sir_curve(t, y, 0.0, 1.0)
    with pytest.raises(ValueError, match="N must be finite and positive"):
        fit_sir_curve(t, y, math.inf, 1.0)


def test_compare_fits_reports_all_failed_candidates() -> None:
    failed = FitResult(
        params={"a": (1.0, math.inf)}, rmse=math.inf, aic=math.inf, bic=math.inf,
        resid_autocorr=0.0, success=False, method="bounded_least_squares", n=3, k=1,
    )
    outcome = compare_fits({"first": failed, "second": failed})
    assert outcome == {"ranking": [], "best": None, "reason": "all fits failed"}
