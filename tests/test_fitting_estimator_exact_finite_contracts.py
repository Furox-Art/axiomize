"""Real SciPy nonlinear fitting and error reporting without proxy successes."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.fitting.estimator import (
    FitResult,
    _coerce_xy,
    _diagnostics,
    _lag1_autocorrelation,
    _validate_fit_spec,
    compare_fits,
    fit_curve,
    fit_logistic_curve,
    fit_sir_curve,
)


@pytest.mark.parametrize(
    ("t", "y", "message"),
    [
        ([[0.0, 1.0], [1.0, 2.0]], [1.0, 2.0], "one-dimensional"),
        ([0.0, 1.0], [[1.0, 2.0], [3.0, 4.0]], "one-dimensional"),
        ([0.0, 1.0], [1.0], "same length"),
        ([0.0], [1.0], "at least two"),
        ([0.0, 1.0], [float("nan"), 2.0], "finite"),
        ([0.0, float("inf")], [1.0, 2.0], "finite"),
    ],
)
def test_direct_fit_requires_real_finite_paired_measurements(t, y, message):
    with pytest.raises(ValueError, match=message):
        _coerce_xy(np.asarray(t), np.asarray(y))


@pytest.mark.parametrize("t", [[0.0, 0.0, 1.0], [2.0, 1.0, 3.0]])
def test_timeseries_fitting_refuses_duplicate_or_reverse_time(t):
    with pytest.raises(ValueError, match="strictly increasing"):
        _coerce_xy(np.asarray(t), np.asarray([1.0, 2.0, 3.0]), require_increasing=True)


@pytest.mark.parametrize(
    ("p0", "names", "bounds", "message"),
    [
        ([], [], None, "at least one"),
        ([1.0], ["a", "b"], None, "same length"),
        ([1.0, 2.0], ["a", "a"], None, "must be unique"),
        ([float("nan")], ["a"], None, "only finite"),
        ([1.0, 2.0, 3.0], ["a", "b", "c"], None, "at least the number"),
        ([1.0], ["a"], ([0.0], [1.0, 2.0]), "matching p0"),
        ([1.0], ["a"], ([float("nan")], [2.0]), "must not contain NaN"),
        ([1.0], ["a"], ([2.0], [1.0]), "lower bound"),
        ([1.0], ["a"], ([1.1], [2.0]), "within bounds"),
    ],
)
def test_fit_parameters_and_bounds_are_not_silently_fixed(p0, names, bounds, message):
    with pytest.raises(ValueError, match=message):
        _validate_fit_spec(np.asarray([0.0, 1.0]), p0, names, bounds)


def test_explicit_unbounded_fit_is_recorded_with_real_infinite_constraints():
    low, high = _validate_fit_spec(np.asarray([0.0, 1.0]), [1.0], ["a"], None)
    assert low[0] == -math.inf
    assert high[0] == math.inf


@pytest.mark.parametrize(
    ("resid", "expected"),
    [
        ([0.0], 0.0),
        ([1.0, 2.0], 0.0),
        ([1.0, 1.0, 1.0, 1.0], 0.0),
        ([1.0, float("nan"), 2.0], 0.0),
    ],
)
def test_degenerate_autocorrelation_is_reported_as_nonidentifiable(resid, expected):
    assert _lag1_autocorrelation(np.asarray(resid)) == expected


def test_analytic_fit_error_metrics_have_explicit_rmse_aic_bic():
    y = np.asarray([1.0, 2.0, 3.0, 4.0])
    prediction = np.asarray([1.0, 2.0, 2.0, 4.0])
    rmse, aic, bic, ac = _diagnostics(y, prediction, k=1)
    assert rmse == pytest.approx(0.5)
    assert aic == pytest.approx(4 * math.log(0.25) + 2)
    assert bic == pytest.approx(4 * math.log(0.25) + math.log(4))
    assert math.isfinite(ac)


def test_real_linear_scipy_curve_fit_recovers_known_coefficients():
    t = np.linspace(0.0, 10.0, 30)
    y = 1.5 + 2.0 * t
    out = fit_curve(lambda x, a, b: a + b * x, t, y, [0.0, 1.0], ["intercept", "slope"])
    assert out.success is True
    assert out.params["intercept"][0] == pytest.approx(1.5, abs=1e-8)
    assert out.params["slope"][0] == pytest.approx(2.0, abs=1e-8)
    assert out.rmse < 1e-7
    assert out.to_dict()["params"]["slope"]["stderr"] >= 0


def test_nonconverged_scipy_optimization_cannot_be_reported_as_success(monkeypatch):
    from scipy import optimize

    def broken(*a, **kw):
        raise RuntimeError("no convergence")

    monkeypatch.setattr(optimize, "curve_fit", broken)
    t = np.linspace(0.0, 1.0, 5)
    y = np.asarray([1.0, 2.0, 3.0, 4.0, 5.0])
    result = fit_curve(lambda x, a: a * x, t, y, [1.0], ["a"])
    assert result.success is False
    assert result.params["a"][0] == 1.0
    assert result.params["a"][1] == math.inf


def test_nonfinite_model_prediction_is_a_failed_fit_even_when_optimizer_reports_success(monkeypatch):
    from scipy import optimize

    monkeypatch.setattr(optimize, "curve_fit", lambda *a, **kw: (np.asarray([1.0]), np.asarray([[0.01]])))
    out = fit_curve(
        lambda x, a: np.full_like(x, np.nan), np.asarray([0.0, 1.0, 2.0]), np.asarray([1.0, 2.0, 3.0]), [1.0], ["a"]
    )
    assert out.success is False
    assert math.isinf(out.rmse)


def test_model_exception_after_optimizer_returns_is_recorded_as_failure(monkeypatch):
    from scipy import optimize

    monkeypatch.setattr(optimize, "curve_fit", lambda *a, **kw: (np.asarray([1.0]), np.asarray([[0.01]])))

    def broken(x, a):
        raise ValueError("invalid physical prediction")

    out = fit_curve(broken, np.asarray([0.0, 1.0, 2.0]), np.asarray([1.0, 2.0, 3.0]), [1.0], ["a"])
    assert out.success is False
    assert out.bic == math.inf


@pytest.mark.parametrize(
    ("n", "i0", "pattern"),
    [
        (-1.0, 1.0, "N must be finite"),
        (float("nan"), 1.0, "N must be finite"),
        (10.0, -1.0, "I0 must be finite"),
        (10.0, 11.0, "I0 must be finite"),
    ],
)
def test_sir_fit_rejects_unphysical_population_and_seed(n, i0, pattern):
    with pytest.raises(ValueError, match=pattern):
        fit_sir_curve(np.asarray([0.0, 1.0, 2.0]), np.asarray([1.0, 2.0, 3.0]), n, i0)


def test_logistic_fit_real_synthetic_growth_is_a_solved_not_guessed_result():
    t = np.linspace(0.0, 10.0, 30)
    expected = 100.0 / (1.0 + 9.0 * np.exp(-0.5 * t))
    out = fit_logistic_curve(t, expected)
    assert out.success is True
    assert out.params["r"][0] == pytest.approx(0.5, abs=0.02)
    assert out.params["K"][0] == pytest.approx(100.0, abs=2.0)


def test_bic_comparison_does_not_promote_failed_fit_to_winner():
    failed = FitResult({}, math.inf, math.inf, math.inf, 0.0, False, "none", 10, 1)
    accepted = FitResult({}, 0.2, 1.0, 2.0, 0.0, True, "real", 10, 1)
    assert compare_fits({"failed": failed, "valid": accepted})["best"] == "valid"
    assert compare_fits({"failed": failed})["best"] is None


def test_bic_comparison_orders_only_successful_candidates():
    good = FitResult({}, 0.2, 1.0, 2.0, 0.0, True, "real", 10, 1)
    better = FitResult({}, 0.1, 1.0, 1.0, 0.0, True, "real", 10, 1)
    out = compare_fits({"a": good, "b": better})
    assert out["ranking"] == ["b", "a"]
    assert "physical plausibility" in out["reason"]
