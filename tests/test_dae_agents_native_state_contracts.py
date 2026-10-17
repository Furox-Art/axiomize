"""Actual semi-explicit DAE constraint residuals and seeded agent dynamics."""

from __future__ import annotations

import numpy as np
import pytest

from axiomize.advanced_family_engine import _simulate_agent_based, _simulate_dae
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, VariableSpec


def dae(*, have_diff=True, have_algebraic=True, algebraic_equation=True, initial=1.0):
    vars = []
    eq = []
    if have_diff:
        vars.append(VariableSpec("x", initial=initial))
        eq.append(EquationSpec("x", "-z", kind="derivative"))
    if have_algebraic:
        vars.append(VariableSpec("z", role="latent", initial=1.0))
    if algebraic_equation:
        eq.append(EquationSpec("", "z-2*x", kind="residual"))
    return ModelIR(
        name="index1",
        domain="physics",
        family=ModelFamily.DAE,
        variables=vars,
        parameters=[],
        equations=eq,
    )


def agents(cfg=None, *, has_state=True, equation=True, initial=1.0):
    return ModelIR(
        name="agents",
        domain="biology",
        family=ModelFamily.AGENT_BASED,
        variables=[VariableSpec("x", initial=initial)] if has_state else [],
        parameters=[],
        equations=[EquationSpec("x", "-x", kind="derivative")] if equation else [],
        metadata={"agents": cfg if cfg is not None else {"count": 4, "noise_std": 0.0}},
    )


def execute(fn, model, *, points=10, seed=7, span=(0.0, 0.5)):
    return fn(model, t_span=span, points=points, parameter_overrides=None, seed=seed)


def test_real_dae_index_one_residual_stays_small_under_numerical_integration():
    out = execute(_simulate_dae, dae())
    assert out["status"] == "PASS", out
    assert out["solver"]["dae_form"] == "semi_explicit_index_1"
    x = np.asarray(out["states"]["x"])
    z = np.asarray(out["states"]["z"])
    np.testing.assert_allclose(z, 2 * x, rtol=1e-5, atol=1e-5)
    assert out["diagnostics"]["max_algebraic_residual"] < 1e-6


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"have_diff": False}, "both differential and algebraic"),
        ({"have_algebraic": False}, "both differential and algebraic"),
        ({"algebraic_equation": False}, "one residual per algebraic"),
        ({"initial": None}, "finite initial"),
    ],
)
def test_index_one_dae_refuses_unsupported_or_underdetermined_structure(kwargs, message):
    with pytest.raises(ValueError, match=message):
        execute(_simulate_dae, dae(**kwargs))


def test_seeded_agent_derivative_euler_update_matches_exact_discrete_recursion():
    m = agents()
    out = execute(_simulate_agent_based, m, points=6)
    assert out["status"] == "PASS"
    expected = np.array([1.0 - 0.1] * 4)
    np.testing.assert_allclose(out["states"]["x"][1], expected, atol=1e-12)
    assert out["diagnostics"]["agents"] == 4
    assert out["diagnostics"]["steps"] == 5


def test_agent_fixed_seed_reproduces_independent_noise_draws():
    cfg = {"count": 4, "noise_std": 0.2}
    first = execute(_simulate_agent_based, agents(cfg), seed=21)
    second = execute(_simulate_agent_based, agents(cfg), seed=21)
    third = execute(_simulate_agent_based, agents(cfg), seed=22)
    assert first == second
    assert first["states"]["x"] != third["states"]["x"]


@pytest.mark.parametrize(
    ("cfg", "message"),
    [
        ([], "metadata.agents"),
        ({"count": 0}, "agent count"),
        ({"count": 1000001}, "agent count"),
        ({"count": 3, "initial": []}, "agents.initial"),
        ({"count": 3, "initial": {"x": [1.0, 2.0]}}, "must have length"),
        ({"count": 3, "noise_std": []}, "noise_std must be"),
    ],
)
def test_agent_model_rejects_invalid_population_or_noise_contracts(cfg, message):
    with pytest.raises(ValueError, match=message):
        execute(_simulate_agent_based, agents(cfg))


def test_agent_state_requires_direct_initial_observation():
    with pytest.raises(ValueError, match="needs an initial value"):
        execute(_simulate_agent_based, agents({"count": 2}, initial=None))


def test_agent_model_rejects_implicit_hidden_state_invention():
    with pytest.raises(ValueError, match="requires state variables"):
        execute(_simulate_agent_based, agents(has_state=False))


def test_agent_model_requires_explicit_dynamics():
    with pytest.raises(ValueError, match="missing update/derivative"):
        execute(_simulate_agent_based, agents(equation=False))


def test_agent_time_span_reversed_is_not_auto_corrected():
    with pytest.raises(ValueError, match="t_span must be increasing"):
        execute(_simulate_agent_based, agents(), span=(1.0, 0.0))
