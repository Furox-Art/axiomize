"""Actual numerical error estimates cannot masquerade as model/data uncertainty."""

from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pytest

from axiomize.numerical_verification import (
    _approval_payload,
    _observed_order,
    _relative_errors,
    _richardson_error,
)


def test_exact_equal_high_magnitude_arrays_have_zero_error_without_overflow():
    large = np.full((4, 3), 1.0e308)
    assert _relative_errors(large, large) == (0.0, 0.0, 0.0)


def test_direct_relative_norms_match_analytic_finite_error():
    absolute, rel_rms, rel_max = _relative_errors(np.array([3.0, 4.0]), np.array([4.0, 6.0]))
    assert absolute == pytest.approx(math.sqrt(2.5))
    assert rel_rms == pytest.approx(math.sqrt(2.5 / 12.5))
    assert rel_max == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("reference", "candidate", "message"),
    [
        ([0.0, 1.0], [1.0], "shape mismatch"),
        ([], [], "non-empty finite arrays"),
        ([float("nan")], [0.0], "non-empty finite arrays"),
        ([float("inf")], [0.0], "non-empty finite arrays"),
    ],
)
def test_numeric_error_estimates_reject_mismatched_or_nonfinite_observations(reference, candidate, message):
    with pytest.raises(ValueError, match=message):
        _relative_errors(np.asarray(reference), np.asarray(candidate))


def test_perturbation_overflow_is_rejected_not_reported_as_zero_error():
    with pytest.raises(ValueError, match="difference overflowed"):
        _relative_errors(np.array([1.0e308]), np.array([-1.0e308]))


def test_relative_error_overflow_is_reported_not_cast_to_infinity():
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"), pytest.raises(
        ValueError, match="relative errors overflowed"
    ):
        _relative_errors(np.array([1.0e-300]), np.array([1.0e308]))


def test_exact_zero_baseline_uses_machine_epsilon_and_reports_nonzero_error():
    absolute, rel_rms, rel_max = _relative_errors(np.zeros(3), np.full(3, 1.0e-6))
    assert absolute == pytest.approx(1.0e-6)
    assert rel_rms > 0
    assert rel_max > 0


@pytest.mark.parametrize(
    ("errors", "ratios"),
    [
        ([], []),
        ([0.05], [2.0]),
        ([0.2, 0.1], []),
        ([0.0, 0.1], [2.0]),
        ([0.2, 0.0], [2.0]),
        ([0.2, 0.1], [1.0]),
        ([0.2, 0.1], [0.0]),
    ],
)
def test_convergence_order_unidentified_without_two_real_positive_errors(errors, ratios):
    assert _observed_order(errors, ratios) is None


def test_observed_second_order_is_derived_from_actual_refinement_ratios():
    assert _observed_order([0.04, 0.01], [2.0]) == pytest.approx(2.0)


@pytest.mark.parametrize(
    ("last", "order", "ratio"),
    [
        (1.0, None, 2.0),
        (1.0, 0.0, 2.0),
        (1.0, -1.0, 2.0),
        (1.0, 2.0, 1.0),
        (1.0, 2.0, 0.5),
    ],
)
def test_richardson_error_refuses_unidentifiable_order(last, order, ratio):
    assert _richardson_error(last, order, ratio) is None


def test_richardson_extrapolation_preserves_exact_error_formula():
    assert _richardson_error(0.03, 2.0, 2.0) == pytest.approx(0.01)


def test_approval_budget_is_explicit_and_does_not_automatically_execute_refinement():
    model = SimpleNamespace(family=SimpleNamespace(value="ode"))
    low = _approval_payload(model, study="solver_tolerance_refinement", runs=2, points=25, work_scale=2)
    medium = _approval_payload(model, study="solver_tolerance_refinement", runs=8, points=200, work_scale=100)
    high = _approval_payload(model, study="mesh_refinement", runs=100, points=200, work_scale=200)
    assert [x["cost"]["level"] for x in (low, medium, high)] == ["low", "medium", "high"]
    assert all(x["status"] == "APPROVAL_REQUIRED" for x in (low, medium, high))
    assert all(x["cost"]["requires_user_approval"] for x in (low, medium, high))
    assert low["uncertainty_separation"]["data"] == "not estimated by this study"


def test_cost_estimate_never_counts_less_than_one_simulation_or_two_points():
    model = SimpleNamespace(family=SimpleNamespace(value="ode"))
    out = _approval_payload(model, study="mesh_refinement", runs=0, points=1, work_scale=0)
    assert out["cost"]["estimated_work_units"] == 2
