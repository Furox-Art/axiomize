"""Numerically grounded stop criteria and bounded uncertainty sampling contracts."""

from __future__ import annotations

import numpy as np
import pytest

from axiomize.advanced_diagnostics import _sample_parameter, stopping_decision


def test_stopping_decision_with_insufficient_history_does_not_invent_convergence():
    result = stopping_decision([3.0, 2.0], patience=3)
    assert result["decision"] == "CONTINUE"
    assert result["checks"][0]["status"] == "INSUFFICIENT_DATA"
    assert result["reasons"] == []


def test_stopping_decision_convergence_requires_all_recent_changes():
    converged = stopping_decision([1.0, 1.0, 1.0, 1.0], patience=3)
    assert converged["decision"] == "STOP"
    assert "incremental_improvement" in converged["reasons"]
    not_converged = stopping_decision([5.0, 4.0, 3.0, 2.0], patience=3)
    assert not_converged["decision"] == "CONTINUE"
    assert not_converged["checks"][0]["status"] == "CONTINUE"


@pytest.mark.parametrize("patience", [0, -1])
def test_patience_zero_or_negative_is_rejected(patience):
    with pytest.raises(ValueError, match="patience"):
        stopping_decision([1.0], patience=patience)


@pytest.mark.parametrize("options", [{"relative_tolerance": -0.1}, {"absolute_tolerance": -0.1}])
def test_negative_tolerances_are_rejected(options):
    with pytest.raises(ValueError, match="tolerances"):
        stopping_decision([1.0], **options)


@pytest.mark.parametrize("history", [[float("nan")], [float("inf")], [[1.0, 2.0]]])
def test_nonfinite_or_nonvector_history_is_rejected(history):
    with pytest.raises(ValueError, match="finite 1D"):
        stopping_decision(history)


def test_budget_stop_activates_at_exact_limit_and_tracks_fraction():
    state = stopping_decision([], budget_used=20, budget_limit=20)
    assert state["decision"] == "STOP"
    budget = next(c for c in state["checks"] if c["criterion"] == "compute_budget")
    assert budget["fraction"] == 1.0
    assert "compute_budget" in state["reasons"]


def test_budget_below_limit_does_not_stop():
    state = stopping_decision([], budget_used=2, budget_limit=20)
    assert state["decision"] == "CONTINUE"
    assert "compute_budget" not in state["reasons"]


def test_missing_budget_used_cannot_be_assumed():
    with pytest.raises(ValueError, match="budget_used"):
        stopping_decision([], budget_limit=3)


@pytest.mark.parametrize("limit", [0, -2])
def test_invalid_budget_limit_refused(limit):
    with pytest.raises(ValueError, match="budget_limit must be positive"):
        stopping_decision([], budget_used=0, budget_limit=limit)


def test_uncertainty_below_target_is_sufficient_to_stop():
    state = stopping_decision([], uncertainty=0.01, uncertainty_target=0.03)
    assert state["decision"] == "STOP"
    assert "uncertainty_target" in state["reasons"]


def test_uncertainty_above_target_does_not_stop():
    state = stopping_decision([], uncertainty=0.04, uncertainty_target=0.03)
    assert state["decision"] == "CONTINUE"


def test_missing_uncertainty_cannot_be_assumed():
    with pytest.raises(ValueError, match="uncertainty is required"):
        stopping_decision([], uncertainty_target=0.03)


def test_negative_uncertainty_target_is_refused():
    with pytest.raises(ValueError, match="uncertainty_target"):
        stopping_decision([], uncertainty=0, uncertainty_target=-1)


def _draw(spec, bounds=None, baseline=10, samples=4):
    return _sample_parameter(np.random.default_rng(18), spec, baseline, bounds, samples)


def test_fixed_distribution_yields_deterministic_baseline():
    assert np.array_equal(_draw({"distribution": "fixed"}), np.full(4, 10.0))
    assert np.array_equal(_draw({"kind": "fixed", "value": 9.0}), np.full(4, 9.0))


def test_zero_variance_normal_is_fixed_at_mean():
    assert np.array_equal(_draw({"distribution": "normal", "std": 0, "mean": 4.5}), np.full(4, 4.5))


def test_normal_missing_or_negative_std_is_refused():
    with pytest.raises(ValueError, match="requires std"):
        _draw({"distribution": "normal"})
    with pytest.raises(ValueError, match="non-negative"):
        _draw({"distribution": "normal", "std": -2})


def test_uniform_draws_remain_inside_declared_interval():
    draws = _draw({"distribution": "uniform", "low": 1, "high": 2}, samples=100)
    assert np.all((draws >= 1) & (draws <= 2))


def test_uniform_requires_both_bounds_and_strict_order():
    with pytest.raises(ValueError, match="requires low and high"):
        _draw({"distribution": "uniform", "low": 1})
    with pytest.raises(ValueError, match="high must exceed low"):
        _draw({"distribution": "uniform", "low": 2, "high": 2})


def test_unknown_distribution_is_not_silently_coerced():
    with pytest.raises(ValueError, match="unsupported uncertainty distribution"):
        _draw({"distribution": "made-up"})


def test_fixed_sample_clamped_to_explicit_parameter_bounds():
    assert np.array_equal(_draw({"distribution": "fixed", "value": -5}, bounds=(0, 3)), np.zeros(4))
    assert np.array_equal(_draw({"distribution": "fixed", "value": 20}, bounds=(0, 3)), np.full(4, 3.0))
