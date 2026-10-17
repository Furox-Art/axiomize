"""Reproducible agent/event experiments and honest Bayesian prior constraints."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.advanced_family_engine import (
    _log_prior,
    _simulate_agent_based,
    _simulate_discrete_event,
)
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, VariableSpec


def _model(family, *, variables, equations=(), metadata=None):
    return ModelIR(
        name="direct-stochastic",
        domain="biology",
        family=family,
        variables=list(variables),
        parameters=[],
        equations=list(equations),
        metadata=metadata or {},
    )


def _run(executor, m, *, seed=17):
    return executor(m, t_span=(0.0, 0.5), points=5, parameter_overrides=None, seed=seed)


def test_agent_derivative_update_is_explicit_euler_without_hidden_noise():
    m = _model(
        ModelFamily.AGENT_BASED,
        variables=[VariableSpec("x", initial=1.0, role="state")],
        equations=[EquationSpec("x", "-x", kind="derivative")],
        metadata={"agents": {"count": 3, "noise_std": 0.0}},
    )
    result = _run(_simulate_agent_based, m)
    assert result["status"] == "PASS", result
    values = np.asarray(result["states"]["x"])
    assert values.shape == (5, 3)
    np.testing.assert_allclose(values[:, 0], (1.0 - 0.125) ** np.arange(5), rtol=1e-12)
    np.testing.assert_allclose(values, np.repeat(values[:, [0]], 3, axis=1))
    assert result["diagnostics"]["finite"] is True


def test_agent_difference_and_bounds_are_applied_each_step():
    m = _model(
        ModelFamily.AGENT_BASED,
        variables=[VariableSpec("x", initial=1.0, role="state", bounds=(0.0, 3.0))],
        equations=[EquationSpec("x", "x+10", kind="update")],
        metadata={"agents": {"count": 2, "initial": {"x": [1.0, 2.0]}}},
    )
    result = _run(_simulate_agent_based, m)
    arr = np.asarray(result["states"]["x"])
    np.testing.assert_allclose(arr[0], [1.0, 2.0])
    np.testing.assert_allclose(arr[1:], np.full((4, 2), 3.0))


def test_agent_noise_reproduces_same_seed_and_differs_with_another_seed():
    m = _model(
        ModelFamily.AGENT_BASED,
        variables=[VariableSpec("x", initial=1.0)],
        equations=[EquationSpec("x", "x", kind="difference")],
        metadata={"agents": {"n_agents": 4, "noise_std": {"x": 0.2}}},
    )
    a = _run(_simulate_agent_based, m, seed=1)
    b = _run(_simulate_agent_based, m, seed=1)
    c = _run(_simulate_agent_based, m, seed=2)
    assert a["states"] == b["states"]
    assert a["states"] != c["states"]


@pytest.mark.parametrize(
    ("metadata", "variables", "equations", "error"),
    [
        (
            {"agents": "invalid"},
            [VariableSpec("x", initial=1.0)],
            [EquationSpec("x", "x", kind="update")],
            "metadata.agents",
        ),
        (
            {"agents": {"count": 0}},
            [VariableSpec("x", initial=1.0)],
            [EquationSpec("x", "x", kind="update")],
            "agent count",
        ),
        (
            {"agents": {"count": 1000001}},
            [VariableSpec("x", initial=1.0)],
            [EquationSpec("x", "x", kind="update")],
            "agent count",
        ),
        ({"agents": {"count": 2}}, [], [], "requires state variables"),
        ({"agents": {"count": 2}}, [VariableSpec("x", initial=1.0)], [], "missing update"),
        (
            {"agents": {"count": 2, "initial": []}},
            [VariableSpec("x", initial=1.0)],
            [EquationSpec("x", "x", kind="update")],
            "agents.initial",
        ),
        (
            {"agents": {"count": 2, "initial": {"x": [1.0]}}},
            [VariableSpec("x", initial=1.0)],
            [EquationSpec("x", "x", kind="update")],
            "must have length 2",
        ),
        (
            {"agents": {"count": 2, "noise_std": "bad"}},
            [VariableSpec("x", initial=1.0)],
            [EquationSpec("x", "x", kind="update")],
            "agents.noise_std",
        ),
    ],
)
def test_agent_input_validation_rejects_invalid_state_contracts(metadata, variables, equations, error):
    m = _model(ModelFamily.AGENT_BASED, variables=variables, equations=equations, metadata=metadata)
    with pytest.raises(ValueError, match=error):
        _run(_simulate_agent_based, m)


def test_discrete_event_zero_rate_does_not_invent_transitions():
    m = _model(
        ModelFamily.DISCRETE_EVENT,
        variables=[VariableSpec("s", initial=5.0)],
        metadata={"discrete_event": {"events": [{"name": "decrement", "rate": "0", "delta": {"s": -1.0}}]}},
    )
    result = _run(_simulate_discrete_event, m)
    assert result["status"] == "PASS", result
    np.testing.assert_allclose(result["states"]["s"], [5.0] * 5)
    assert result["diagnostics"]["total_events"] == 0
    assert result["diagnostics"]["event_counts"] == {"decrement": 0}


def test_discrete_event_event_bound_is_fail_closed_and_reproducible():
    m = _model(
        ModelFamily.DISCRETE_EVENT,
        variables=[VariableSpec("s", initial=5.0)],
        metadata={
            "discrete_event": {"events": [{"name": "step", "rate": "100000", "delta": {"s": "-1"}}], "max_events": 1}
        },
    )
    r1 = _run(_simulate_discrete_event, m, seed=1)
    r2 = _run(_simulate_discrete_event, m, seed=1)
    assert r1 == r2
    assert r1["status"] == "FAIL"
    assert r1["diagnostics"]["total_events"] == 1
    assert r1["diagnostics"]["max_events_reached"] is True
    assert r1["diagnostics"]["event_counts"] == {"step": 1}


@pytest.mark.parametrize(
    ("metadata", "variables", "error"),
    [
        ({"discrete_event": "bad"}, [VariableSpec("s", initial=1.0)], "metadata.discrete_event"),
        (
            {"discrete_event": {"events": []}},
            [VariableSpec("s", initial=1.0)],
            "requires metadata.discrete_event.events",
        ),
        ({"discrete_event": {"events": [{"rate": "1"}]}}, [VariableSpec("s", initial=1.0)], "needs rate and delta"),
        (
            {"discrete_event": {"events": [{"rate": "1", "delta": {"unknown": 1}}]}},
            [VariableSpec("s", initial=1.0)],
            "unknown state",
        ),
        (
            {"discrete_event": {"events": [{"rate": "-1", "delta": {"s": 1}}]}},
            [VariableSpec("s", initial=1.0)],
            "finite and nonnegative",
        ),
        ({"discrete_event": {"events": [{"rate": "1", "delta": {"s": 1}}]}}, [VariableSpec("s")], "finite initial"),
    ],
)
def test_discrete_event_rejects_unphysical_rates_and_incomplete_states(metadata, variables, error):
    m = _model(ModelFamily.DISCRETE_EVENT, variables=variables, metadata=metadata)
    with pytest.raises(ValueError, match=error):
        _run(_simulate_discrete_event, m)


@pytest.mark.parametrize(
    ("value", "prior", "bounds", "valid"),
    [
        (-2.0, None, (0.0, 10.0), False),
        (11.0, None, (0.0, 10.0), False),
        (2.0, None, (0.0, 10.0), True),
        (2.0, {"dist": "normal", "mu": 0.0, "sigma": 1.0}, None, True),
        (-1.0, {"dist": "halfnormal", "sigma": 1.0}, None, False),
        (1.0, {"dist": "uniform", "low": 0.0, "high": 2.0}, None, True),
        (3.0, {"dist": "uniform", "low": 0.0, "high": 2.0}, None, False),
        (-1.0, {"dist": "lognormal"}, None, False),
        (1.0, {"dist": "lognormal", "sigma": 1.0}, None, True),
    ],
)
def test_prior_density_respects_distribution_support(value, prior, bounds, valid):
    score = _log_prior(value, prior, bounds, center=1.0)
    assert math.isfinite(score) is valid


@pytest.mark.parametrize(
    "prior",
    [
        {"dist": "normal", "sigma": 0},
        {"dist": "lognormal", "sigma": 0},
        {"dist": "gamma", "shape": 1},
    ],
)
def test_invalid_or_unsupported_builtin_prior_is_rejected(prior):
    with pytest.raises(ValueError):
        _log_prior(1.0, prior, None, center=1.0)
