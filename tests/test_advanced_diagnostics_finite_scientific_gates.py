"""Scientific termination and Monte-Carlo input contracts must fail closed."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.advanced_diagnostics import (
    _sample_parameter,
    bifurcation_scan,
    propagate_parameter_uncertainty,
    stopping_decision,
)
from axiomize.model_ir import ModelIR


def _simple_ode() -> ModelIR:
    return ModelIR.from_dict(
        {
            "schema_version": "1.0",
            "domain": "general",
            "name": "simple-decay",
            "family": "ode",
            "variables": [{"name": "x", "initial": 1.0}],
            "parameters": [{"name": "rate", "value": 0.5}],
            "equations": [{"target": "x", "expression": "-rate*x", "kind": "derivative"}],
        }
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"relative_tolerance": math.nan},
        {"relative_tolerance": math.inf},
        {"relative_tolerance": -1},
        {"absolute_tolerance": -0.1},
        {"absolute_tolerance": math.nan},
        {"absolute_tolerance": math.inf},
        {"patience": True},
        {"patience": 1.5},
        {"patience": 0},
        {"budget_limit": 1.0},
        {"budget_limit": 0, "budget_used": 1.0},
        {"budget_limit": math.nan, "budget_used": 1.0},
        {"budget_limit": math.inf, "budget_used": 1.0},
        {"budget_limit": 1.0, "budget_used": math.nan},
        {"budget_limit": 1.0, "budget_used": -1.0},
        {"uncertainty_target": 0.1},
        {"uncertainty_target": math.nan, "uncertainty": 0.1},
        {"uncertainty_target": math.inf, "uncertainty": 0.1},
        {"uncertainty_target": -1.0, "uncertainty": 0.1},
        {"uncertainty_target": 0.1, "uncertainty": math.nan},
        {"uncertainty_target": 0.1, "uncertainty": -1.0},
    ],
)
def test_stopping_gate_rejects_invalid_metrics(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        stopping_decision([2.0, 1.0, 1.0, 1.0], **kwargs)


def test_stopping_gate_has_explicit_insufficient_data_and_continue() -> None:
    early = stopping_decision([1.0], patience=2)
    assert early["decision"] == "CONTINUE"
    assert early["checks"][0]["status"] == "INSUFFICIENT_DATA"
    continuing = stopping_decision(
        [3.0, 2.0, 1.0, 0.0],
        budget_limit=100.0,
        budget_used=5.0,
        uncertainty_target=0.1,
        uncertainty=1.0,
        patience=2,
    )
    assert continuing["decision"] == "CONTINUE"
    assert set(check["status"] for check in continuing["checks"]) == {"CONTINUE"}


def test_stopping_gate_reports_which_configured_criteria_satisfied() -> None:
    result = stopping_decision(
        [1.0, 1.0, 1.0, 1.0],
        patience=2,
        budget_used=100,
        budget_limit=100,
        uncertainty=0.03,
        uncertainty_target=0.05,
    )
    assert result["decision"] == "STOP"
    assert result["reasons"] == ["incremental_improvement", "compute_budget", "uncertainty_target"]
    assert all(row["status"] == "STOP" for row in result["checks"])


@pytest.mark.parametrize("history", [[math.inf], [math.nan], [[1.0]], [1, 2, math.nan]])
def test_stopping_gate_rejects_unusable_history(history: object) -> None:
    with pytest.raises(ValueError, match="history must be"):
        stopping_decision(history)


def test_stopping_gate_rejects_numerically_overflowed_difference() -> None:
    with pytest.raises(ValueError, match="comparison overflowed"):
        stopping_decision([1e308, -1e308], patience=1)


@pytest.mark.parametrize(
    "spec",
    [
        {"distribution": "normal"},
        {"distribution": "normal", "std": -1.0},
        {"distribution": "normal", "std": math.nan},
        {"distribution": "normal", "std": math.inf},
        {"distribution": "normal", "mean": math.nan, "std": 1.0},
        {"distribution": "uniform", "low": 1.0},
        {"distribution": "uniform", "low": 1.0, "high": 1.0},
        {"distribution": "uniform", "low": 1.0, "high": math.inf},
        {"distribution": "fixed", "value": math.nan},
        {"distribution": "laplace", "scale": 1.0},
    ],
)
def test_sampling_never_produces_nonfinite_probabilistic_draws(spec: dict) -> None:
    with pytest.raises(ValueError):
        _sample_parameter(np.random.default_rng(4), spec, 1.0, None, 3)


def test_sampling_is_seed_reproducible_and_respects_finite_bounds() -> None:
    rng_a = np.random.default_rng(9)
    rng_b = np.random.default_rng(9)
    spec = {"distribution": "normal", "mean": 0.0, "std": 100.0}
    one = _sample_parameter(rng_a, spec, 0.0, (-1.0, 1.0), 50)
    two = _sample_parameter(rng_b, spec, 0.0, (-1.0, 1.0), 50)
    np.testing.assert_array_equal(one, two)
    assert np.max(one) <= 1.0 and np.min(one) >= -1.0
    fixed = _sample_parameter(
        np.random.default_rng(3),
        {"distribution": "fixed", "value": 0.3},
        0.3,
        None,
        5,
    )
    assert np.all(fixed == 0.3)
    uniform = _sample_parameter(
        np.random.default_rng(3),
        {"distribution": "uniform", "low": 1.0, "high": 3.0},
        2.0,
        None,
        20,
    )
    assert np.all((uniform >= 1.0) & (uniform <= 3.0))


@pytest.mark.parametrize("bounds", [(math.nan, 2), (0, math.inf)])
def test_sampling_rejects_invalid_parameter_bounds(bounds: tuple) -> None:
    with pytest.raises(ValueError, match="bound"):
        _sample_parameter(
            np.random.default_rng(1),
            {"distribution": "fixed", "value": 1},
            1.0,
            bounds,
            3,
        )


@pytest.mark.parametrize("samples", [1, 100001])
def test_monte_carlo_rejects_invalid_sample_count(samples: int) -> None:
    with pytest.raises(ValueError, match="samples"):
        propagate_parameter_uncertainty(
            _simple_ode(),
            t_span=(0, 0.2),
            parameter_uncertainty={},
            samples=samples,
        )


@pytest.mark.parametrize("quantiles", [[], [-0.1], [1.1], [math.nan]])
def test_monte_carlo_rejects_invalid_quantile_specification(
    quantiles: list[float],
) -> None:
    with pytest.raises(ValueError, match="quantiles"):
        propagate_parameter_uncertainty(
            _simple_ode(),
            t_span=(0, 0.2),
            parameter_uncertainty={},
            samples=2,
            quantiles=tuple(quantiles),
        )


def test_monte_carlo_unapproved_computation_reports_cost_not_fabricated_result() -> None:
    report = propagate_parameter_uncertainty(
        _simple_ode(),
        t_span=(0, 0.2),
        parameter_uncertainty={"rate": {"distribution": "normal", "std": 0.1}},
        points=6,
        samples=3,
        approve_heavy=False,
    )
    assert report["status"] == "APPROVAL_REQUIRED"
    assert "states" not in report


def test_monte_carlo_small_approved_ode_is_seed_deterministic() -> None:
    model = _simple_ode()
    kwargs = dict(
        t_span=(0.0, 0.2),
        points=6,
        samples=3,
        seed=12,
        parameter_uncertainty={"rate": {"distribution": "normal", "std": 0.1}},
        approve_heavy=True,
    )
    first = propagate_parameter_uncertainty(model, **kwargs)
    second = propagate_parameter_uncertainty(model, **kwargs)
    assert first["status"] == second["status"] == "PASS"
    assert first["successful_samples"] == 3 and first["failed_samples"] == 0
    assert first["parameter_draw_summary"] == second["parameter_draw_summary"]
    assert first["states"]["x"]["mean"] == pytest.approx(second["states"]["x"]["mean"])
    assert len(first["states"]["x"]["mean"]) == 6


def test_bifurcation_requires_approval_and_multiple_values() -> None:
    model = _simple_ode()
    with pytest.raises(ValueError, match="at least two"):
        bifurcation_scan(model, parameter="rate", values=[0.1])
    result = bifurcation_scan(model, parameter="rate", values=[0.1, 0.2])
    assert result["status"] == "APPROVAL_REQUIRED"


def test_bifurcation_scan_rejects_unknown_parameter_when_approved() -> None:
    with pytest.raises(ValueError, match="unknown parameter"):
        bifurcation_scan(
            _simple_ode(),
            parameter="absent",
            values=[0.1, 0.2],
            approve_heavy=True,
        )
