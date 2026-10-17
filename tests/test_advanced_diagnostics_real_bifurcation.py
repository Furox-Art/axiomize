"""Actual stability transitions and Monte Carlo distribution support for advanced diagnostics."""

from __future__ import annotations

import numpy as np
import pytest

from axiomize.advanced_diagnostics import (
    _equilibrium_for_ode,
    _sample_parameter,
    bifurcation_scan,
    propagate_parameter_uncertainty,
    stopping_decision,
)
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, ParameterSpec, VariableSpec


def cubic():
    return ModelIR(
        name="cubic",
        domain="physics",
        family=ModelFamily.ODE,
        variables=[VariableSpec("x", initial=0.0)],
        parameters=[ParameterSpec("k", 0.0)],
        equations=[EquationSpec("x", "k*x-x**3")],
    )


@pytest.mark.parametrize(
    ("kind", "spec", "expected"),
    [
        ("fixed", {"distribution": "fixed", "value": 0.4}, 0.4),
        ("normal", {"distribution": "normal", "mean": 0.4, "std": 0.0}, 0.4),
    ],
)
def test_real_fixed_and_zero_variance_sampler(kind, spec, expected):
    rng = np.random.default_rng(5)
    values = _sample_parameter(rng, spec, baseline=1.0, bounds=None, samples=7)
    np.testing.assert_allclose(values, [expected] * 7)
    assert values.shape == (7,)


def test_uniform_parameter_distribution_respects_declared_interval():
    values = _sample_parameter(
        np.random.default_rng(5),
        {
            "distribution": "uniform",
            "low": 0.1,
            "high": 0.3,
        },
        baseline=0.2,
        bounds=None,
        samples=500,
    )
    assert 0.1 <= np.min(values) < np.max(values) <= 0.3


def test_sampler_clamps_values_to_declared_physical_bounds():
    values = _sample_parameter(
        np.random.default_rng(5),
        {"distribution": "normal", "mean": 100.0, "std": 0.0},
        baseline=1.0,
        bounds=(0.0, 2.0),
        samples=5,
    )
    np.testing.assert_allclose(values, [2.0] * 5)


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ({"distribution": "normal"}, "requires std"),
        ({"distribution": "normal", "std": -1.0}, "non-negative"),
        ({"distribution": "uniform"}, "requires low and high"),
        ({"distribution": "uniform", "low": 2.0, "high": 1.0}, "high must exceed"),
        ({"distribution": "madeup"}, "unsupported uncertainty distribution"),
        ({"distribution": "fixed", "value": float("nan")}, "finite numeric"),
    ],
)
def test_invalid_parameter_sampler_is_not_assumed_to_be_a_valid_distribution(spec, message):
    with pytest.raises(ValueError, match=message):
        _sample_parameter(np.random.default_rng(1), spec, baseline=0.0, bounds=None, samples=5)


def test_cubic_equilibrium_root_exact_for_declared_guess():
    eq = _equilibrium_for_ode(cubic(), parameter_values={"k": -0.3}, guess={"x": 0.0})
    assert eq == {"x": pytest.approx(0.0, abs=1e-10)}


def test_sign_change_in_linearized_stability_is_a_candidate_not_a_proven_bifurcation():
    result = bifurcation_scan(
        cubic(), parameter="k", values=[-0.5, 0.5], equilibrium_guess={"x": 0.0}, approve_heavy=True
    )
    assert result["status"] == "PASS", result
    assert [r["status"] for r in result["rows"]] == ["PASS", "PASS"]
    assert len(result["transition_candidates"]) == 1
    assert result["transition_candidates"][0]["between"] == [-0.5, 0.5]
    assert result["transition_candidates"][0]["classification"] == "local_stability_transition_candidate"
    assert "not proof" in result["interpretation"]


def test_actual_stability_scan_honors_approval_gate():
    blocked = bifurcation_scan(cubic(), parameter="k", values=[-0.2, 0.2])
    assert blocked["status"] == "APPROVAL_REQUIRED"
    assert "rows" not in blocked


def test_direct_uncertainty_sampling_keeps_seed_and_quantiles_in_evidence():
    model = ModelIR(
        name="decay",
        domain="physics",
        family=ModelFamily.ODE,
        variables=[VariableSpec("x", initial=1.0)],
        parameters=[ParameterSpec("k", 0.3, bounds=(0.0, 1.0))],
        equations=[EquationSpec("x", "-k*x")],
    )
    kwargs = dict(
        t_span=(0.0, 0.5),
        points=7,
        samples=4,
        seed=17,
        parameter_uncertainty={"k": {"distribution": "uniform", "low": 0.1, "high": 0.5}},
        quantiles=(0.1, 0.5, 0.9),
        approve_heavy=True,
    )
    a = propagate_parameter_uncertainty(model, **kwargs)
    b = propagate_parameter_uncertainty(model, **kwargs)
    assert a["status"] == "PASS", a
    assert a == b
    assert a["successful_samples"] == 4
    assert a["failed_samples"] == 0
    assert list(a["states"]["x"]["quantiles"]) == ["q0.1", "q0.5", "q0.9"]
    assert len(a["states"]["x"]["mean"]) == 7
    assert a["parameter_draw_summary"]["k"]["std"] > 0


def test_unsupported_uncertainty_family_never_silently_runs_a_fake_executor():
    unsupported = ModelIR(
        name="causal",
        domain="biology",
        family=ModelFamily.CAUSAL,
        variables=[VariableSpec("x", initial=1.0)],
        parameters=[],
        equations=[],
    )
    result = propagate_parameter_uncertainty(unsupported, t_span=(0.0, 1.0), parameter_uncertainty={}, samples=2)
    assert result["status"] == "TOOL_ROUTE_REQUIRED"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"samples": 1}, "at least 2"),
        ({"samples": 100001}, "hard safety limit"),
        ({"quantiles": (-0.1, 0.5)}, "probabilities"),
        ({"quantiles": (float("nan"),)}, "probabilities"),
        ({"quantiles": ()}, "probabilities"),
    ],
)
def test_uncertainty_refuses_invalid_probability_or_sample_requirements(kwargs, message):
    with pytest.raises(ValueError, match=message):
        propagate_parameter_uncertainty(
            cubic(), t_span=(0.0, 1.0), parameter_uncertainty={"k": {"distribution": "normal", "std": 0.1}}, **kwargs
        )


@pytest.mark.parametrize(
    ("series", "decision"),
    [
        ([1.0, 1.0, 1.0], "STOP"),
        ([1.0, 0.5, 0.3], "CONTINUE"),
    ],
)
def test_stopping_history_does_not_invent_missing_criteria(series, decision):
    out = stopping_decision(series, patience=2, absolute_tolerance=1e-10)
    assert out["decision"] == decision
    assert len(out["checks"]) == 1
    assert out["checks"][0]["criterion"] == "incremental_improvement"


def test_unmet_criteria_do_not_trigger_false_stop():
    out = stopping_decision(
        [1.0, 0.6, 0.3],
        patience=2,
        budget_used=2.0,
        budget_limit=10.0,
        uncertainty=0.5,
        uncertainty_target=0.1,
    )
    assert out["decision"] == "CONTINUE"
    assert out["reasons"] == []
    assert len(out["checks"]) == 3
