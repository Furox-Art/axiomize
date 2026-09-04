"""Regression tests for scientific input validation and fit diagnostics."""

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from axiomize.fitting.estimator import fit_curve, fit_logistic_curve, fit_sir_curve
from axiomize.tools.numerical.scipy_tool import final_size_numeric, solve_sir


class TestFitInputValidation:
    def test_rejects_non_finite_observations(self):
        with pytest.raises(ValueError, match="finite"):
            fit_curve(
                lambda tt, a: a * tt,
                np.array([0.0, 1.0, 2.0]),
                np.array([0.0, np.nan, 2.0]),
                p0=[1.0],
                param_names=["a"],
            )

    def test_rejects_parameter_name_mismatch(self):
        with pytest.raises(ValueError, match="param_names"):
            fit_curve(
                lambda tt, a: a * tt,
                np.array([0.0, 1.0, 2.0]),
                np.array([0.0, 1.0, 2.0]),
                p0=[1.0],
                param_names=["a", "extra"],
            )

    def test_degenerate_lag1_autocorrelation_is_finite(self):
        t = np.arange(4, dtype=float)
        y = np.array([0.0, 0.0, 0.0, 1.0])
        result = fit_curve(
            lambda tt, c: np.full_like(tt, c, dtype=float),
            t,
            y,
            p0=[0.0],
            param_names=["c"],
        )
        assert result.success is True
        assert np.isfinite(result.resid_autocorr)
        assert result.resid_autocorr == 0.0

    def test_time_series_fit_requires_increasing_time(self):
        with pytest.raises(ValueError, match="strictly increasing"):
            fit_logistic_curve(
                np.array([0.0, 2.0, 1.0]),
                np.array([1.0, 2.0, 3.0]),
            )

    def test_sir_fit_rejects_impossible_initial_population(self):
        with pytest.raises(ValueError, match="I0"):
            fit_sir_curve(
                np.array([0.0, 1.0, 2.0]),
                np.array([2.0, 3.0, 4.0]),
                N=10.0,
                I0=11.0,
            )


class TestSirInputValidation:
    @pytest.mark.parametrize(
        ("beta", "gamma", "I0", "N", "days", "message"),
        [
            (-0.1, 0.1, 1.0, 100.0, 10.0, "beta"),
            (0.1, -0.1, 1.0, 100.0, 10.0, "gamma"),
            (0.1, 0.1, -1.0, 100.0, 10.0, "I0"),
            (0.1, 0.1, 101.0, 100.0, 10.0, "I0"),
            (0.1, 0.1, 1.0, 0.0, 10.0, "N"),
            (0.1, 0.1, 1.0, 100.0, 0.0, "days"),
        ],
    )
    def test_solver_rejects_unphysical_domain(self, beta, gamma, I0, N, days, message):
        with pytest.raises(ValueError, match=message):
            solve_sir(beta, gamma, I0, N, days=days)

    def test_final_size_requires_positive_gamma(self):
        with pytest.raises(ValueError, match="gamma"):
            final_size_numeric(0.3, 0.0)

    def test_valid_solver_still_reports_finite_diagnostics(self):
        result = solve_sir(0.35, 0.12, 20.0, 10000.0, days=60.0)
        assert result.success is True
        assert np.isfinite(result.final_size)
        assert np.isfinite(result.max_conservation_error)
        assert np.isfinite(result.max_residual)
