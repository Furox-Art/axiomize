"""Scientific refinement error and observed-order estimators remain explicit."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, VariableSpec
from axiomize.numerical_verification import (
    _approval_payload,
    _observed_order,
    _relative_errors,
    _richardson_error,
)


def model():
    return ModelIR(
        name="refinement",
        domain="physics",
        family=ModelFamily.ODE,
        variables=[VariableSpec("x", initial=1.0)],
        parameters=[],
        equations=[EquationSpec("x", "-x")],
    )


@pytest.mark.parametrize(
    ("reference", "candidate", "expected"),
    [
        ([1.0, 1.0], [1.0, 1.0], 0.0),
        ([1.0, 1.0], [2.0, 2.0], 1.0),
        ([1.0, 1.0], [1.0, 2.0], math.sqrt(0.5)),
    ],
)
def test_refinement_absolute_rms_agrees_with_exact_analytic_arrays(reference, candidate, expected):
    abs_l2, rel_l2, rel_inf = _relative_errors(np.asarray(reference), np.asarray(candidate))
    assert abs_l2 == pytest.approx(expected)
    assert rel_l2 == pytest.approx(expected)
    assert rel_inf >= 0.0


def test_refinement_extreme_finite_data_stays_finite_for_identical_models():
    enormous = np.asarray([1e308, 1e308])
    assert _relative_errors(enormous, enormous) == (0.0, 0.0, 0.0)


@pytest.mark.parametrize(
    ("a", "b", "pattern"),
    [
        ([1.0, 2.0], [1.0], "shape mismatch"),
        ([], [], "non-empty finite"),
        ([float("nan")], [1.0], "non-empty finite"),
        ([1.0], [float("inf")], "non-empty finite"),
        ([1e308], [-1e308], "difference overflowed"),
    ],
)
def test_refinement_comparison_refuses_invalid_or_overflowed_evidence(a, b, pattern):
    with pytest.raises(ValueError, match=pattern):
        _relative_errors(np.asarray(a), np.asarray(b))


@pytest.mark.parametrize(
    ("errors", "ratios", "expected"),
    [
        ([1.0, 0.25], [2.0], 2.0),
        ([0.01, 0.005], [2.0], 1.0),
        ([0.01, 0.01], [2.0], 0.0),
    ],
)
def test_observed_convergence_order_is_log_error_ratio(errors, ratios, expected):
    assert _observed_order(errors, ratios) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("errors", "ratios"),
    [
        ([], []),
        ([1.0], [2.0]),
        ([1.0, 0.0], [2.0]),
        ([0.0, 1.0], [2.0]),
        ([1.0, 0.5], [1.0]),
    ],
)
def test_order_cannot_be_inferred_from_missing_or_degenerate_refinements(errors, ratios):
    assert _observed_order(errors, ratios) is None


@pytest.mark.parametrize(
    ("difference", "order", "ratio", "expected"),
    [
        (0.2, 1.0, 2.0, 0.2),
        (0.3, 2.0, 2.0, 0.1),
    ],
)
def test_richardson_extrapolation_matches_known_order_error(difference, order, ratio, expected):
    assert _richardson_error(difference, order, ratio) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("order", "ratio"),
    [
        (None, 2.0),
        (0.0, 2.0),
        (-1.0, 2.0),
        (1.0, 1.0),
        (1.0, 0.5),
    ],
)
def test_unidentifiable_richardson_error_stays_unverified(order, ratio):
    assert _richardson_error(0.1, order, ratio) is None


@pytest.mark.parametrize(
    ("runs", "points", "work_scale", "cost_level"),
    [
        (1, 5, 1, "low"),
        (10, 100, 100, "medium"),
        (100, 200, 100, "high"),
    ],
)
def test_refinement_approval_estimates_runtime_cost_without_running_models(runs, points, work_scale, cost_level):
    proposal = _approval_payload(
        model(),
        study="solver_tolerance_refinement",
        runs=runs,
        points=points,
        work_scale=work_scale,
    )
    assert proposal["status"] == "APPROVAL_REQUIRED"
    assert proposal["cost"]["level"] == cost_level
    assert proposal["cost"]["requires_user_approval"] is True
    assert proposal["uncertainty_separation"]["parameter"] == "not estimated by this study"
