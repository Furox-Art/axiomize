"""Fitting subpackage."""

from axiomize.fitting.estimator import (
    FitResult,
    compare_fits,
    fit_curve,
    fit_logistic_curve,
    fit_sir_curve,
)

__all__ = ["FitResult", "compare_fits", "fit_curve", "fit_logistic_curve", "fit_sir_curve"]
