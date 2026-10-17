"""Native core numerics checked against analytic models and explicit proxies."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.general_engine_core import (
    _simulate_sde,
    _solve_algebraic,
    discover_sparse_dynamics,
    local_stability,
    nondimensionalization_plan,
    rank_experiment_times,
    split_uncertainty,
)
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, ParameterSpec, VariableSpec


def ode(*, growth: bool = False) -> ModelIR:
    return ModelIR(
        name="linear-stability",
        domain="physics",
        family=ModelFamily.ODE,
        variables=[VariableSpec("x", initial=1.0)],
        parameters=[ParameterSpec("k", 0.5)],
        equations=[EquationSpec("x", "k*x" if growth else "-k*x")],
    )


def test_linearized_stability_eigenvalue_matches_exact_rate():
    stable = local_stability(ode(), state={"x": 1.0})
    unstable = local_stability(ode(growth=True), state={"x": 1.0})
    assert stable["jacobian"] == [[-0.5]]
    assert stable["classification"] == "stable"
    assert stable["max_real_part"] == pytest.approx(-0.5)
    assert unstable["classification"] == "unstable"
    assert unstable["max_real_part"] == pytest.approx(0.5)


def test_linearization_refuses_non_ode_families():
    model = ModelIR(
        name="stochastic",
        domain="physics",
        family=ModelFamily.STOCHASTIC,
        variables=[VariableSpec("x", initial=1.0)],
        parameters=[],
        equations=[EquationSpec("x", "-x")],
    )
    with pytest.raises(ValueError, match="requires an ODE"):
        local_stability(model, state={"x": 1.0})


def test_separating_aleatoric_from_epistemic_uncertainty_never_merges_them():
    out = split_uncertainty(residual_std=0.3, parameter_covariance=[[4.0, 0.0], [0.0, 9.0]])
    assert out["aleatoric"]["estimate"] == pytest.approx(0.3)
    assert out["epistemic"]["estimate"] == pytest.approx(math.sqrt(13))
    assert "separately" in out["note"]


def test_unknown_uncertainty_component_is_not_fabricated_from_other_component():
    assert split_uncertainty()["aleatoric"]["estimate"] is None
    assert split_uncertainty()["epistemic"]["estimate"] is None
    assert split_uncertainty(residual_std=0.2)["epistemic"]["estimate"] is None


def test_nondimensionalization_is_only_proposed_never_auto_applied():
    model = ModelIR(
        name="multiscale",
        domain="physics",
        family=ModelFamily.ODE,
        variables=[VariableSpec("small", initial=1e-7), VariableSpec("large", initial=1e5)],
        parameters=[],
        equations=[EquationSpec("small", "0"), EquationSpec("large", "0")],
    )
    plan = nondimensionalization_plan(model)
    assert plan["recommended"] is True
    assert plan["dynamic_range"] == pytest.approx(1e12)
    assert plan["applied"] is False
    assert plan["variable_scales"] == {"small": 1e-7, "large": 1e5}


def test_nondimensionalization_returns_finite_default_for_zero_state():
    model = ModelIR(
        name="zero",
        domain="physics",
        family=ModelFamily.ODE,
        variables=[VariableSpec("x", initial=0.0)],
        parameters=[],
        equations=[EquationSpec("x", "0")],
    )
    plan = nondimensionalization_plan(model)
    assert plan["recommended"] is False
    assert plan["variable_scales"]["x"] == 1.0


def test_stochastic_ode_with_zero_noise_is_deterministic_euler_exact():
    m = ModelIR(
        name="zero-noise",
        domain="physics",
        family=ModelFamily.STOCHASTIC,
        variables=[VariableSpec("x", initial=1.0)],
        parameters=[],
        equations=[EquationSpec("x", "-x")],
        metadata={"diffusion": {"x": 0.0}},
    )
    out = _simulate_sde(m, t_span=(0.0, 0.4), points=5, parameter_overrides=None, seed=7)
    assert out["status"] == "PASS", out
    assert out["solver"]["method"] == "euler_maruyama"
    np.testing.assert_allclose(out["states"]["x"], 0.9 ** np.arange(5), atol=1e-12)


def test_stochastic_noise_is_seeded_and_changes_with_seed():
    m = ModelIR(
        name="noisy",
        domain="physics",
        family=ModelFamily.STOCHASTIC,
        variables=[VariableSpec("x", initial=1.0)],
        parameters=[],
        equations=[EquationSpec("x", "0")],
        metadata={"diffusion": {"x": 0.1}},
    )
    kwargs = dict(t_span=(0.0, 1.0), points=11, parameter_overrides=None)
    one = _simulate_sde(m, seed=4, **kwargs)
    two = _simulate_sde(m, seed=4, **kwargs)
    three = _simulate_sde(m, seed=5, **kwargs)
    assert one["states"] == two["states"]
    assert one["states"] != three["states"]


@pytest.mark.parametrize(
    ("extra", "span", "pattern"),
    [
        ({"diffusion": "bad"}, (0.0, 1.0), "metadata.diffusion"),
        ({"diffusion": {}}, (1.0, 0.0), "t_span must be increasing"),
    ],
)
def test_stochastic_solver_rejects_invalid_dynamics_contract(extra, span, pattern):
    m = ModelIR(
        name="invalid",
        domain="physics",
        family=ModelFamily.STOCHASTIC,
        variables=[VariableSpec("x", initial=1.0)],
        parameters=[],
        equations=[EquationSpec("x", "0")],
        metadata=extra,
    )
    with pytest.raises(ValueError, match=pattern):
        _simulate_sde(m, t_span=span, points=5, parameter_overrides=None, seed=7)


@pytest.mark.parametrize(
    ("times", "states", "degree", "pattern"),
    [
        ([0.0, 1.0], [0.0, 1.0], 2, "at least 5"),
        ([0.0, 1.0, 2.0, 3.0, 3.0], [0.0, 1.0, 2.0, 3.0, 4.0], 2, "increasing"),
        ([0.0, 1.0, 2.0, 3.0, 4.0], [0.0, 1.0, 2.0, 3.0, 4.0], 0, "degree"),
        ([0.0, 1.0, 2.0, 3.0, 4.0], [0.0, 1.0, 2.0, 3.0, 4.0], 6, "degree"),
    ],
)
def test_sparse_discovery_requires_identifiable_time_series(times, states, degree, pattern):
    with pytest.raises(ValueError, match=pattern):
        discover_sparse_dynamics(time=times, state=states, degree=degree, approve_heavy=True)


def test_sparse_dynamics_returns_real_derivative_proxy_not_a_law_claim():
    time = np.linspace(0.0, 1.0, 30)
    states = 1.0 + 2.0 * time
    out = discover_sparse_dynamics(
        time=time.tolist(), state=states.tolist(), degree=1, threshold=0.001, approve_heavy=True
    )
    assert out["status"] == "PASS", out
    assert out["scientific_status"] == "UNVERIFIED"
    assert out["rmse_derivative"] < 1e-10
    assert len(out["candidate_terms"]) == 1
    assert out["candidate_terms"][0]["term"] == "1"
    assert out["candidate_terms"][0]["coefficient"] == pytest.approx(2.0, abs=1e-10)


def test_experimental_time_design_rank_matches_analytic_decay_sensitivity():
    out = rank_experiment_times(ode(), parameter="k", candidate_times=[0.0, 1.0, 2.0], horizon=2.0, approve_heavy=True)
    assert out["status"] == "PASS", out
    assert out["metric"].endswith("Fisher-information proxy)")
    assert [r["time"] for r in out["ranked_tests"]] == [2.0, 1.0, 0.0]
    assert out["ranked_tests"][-1]["information_proxy"] < 1e-14


def test_experimental_design_never_creates_missing_parameter_baseline():
    with pytest.raises(ValueError, match="needs a baseline"):
        rank_experiment_times(ode(), parameter="absent", candidate_times=[0.0, 1.0], horizon=2.0, approve_heavy=True)


def test_analytic_algebraic_equilibrium_solves_declared_residual():
    m = ModelIR(
        name="equilibrium",
        domain="mathematics",
        family=ModelFamily.ALGEBRAIC,
        variables=[VariableSpec("x", initial=2.0)],
        parameters=[],
        equations=[EquationSpec("", "x*x-4", kind="residual")],
    )
    out = _solve_algebraic(m, parameter_overrides=None)
    assert out["status"] == "PASS", out
    assert out["solver"]["method"] == "nsolve"
    assert out["states"]["x"] == pytest.approx(2.0)
