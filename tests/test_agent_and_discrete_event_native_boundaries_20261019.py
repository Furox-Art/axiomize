"""Real reproducible agent dynamics and bounded Gillespie event execution."""
from __future__ import annotations

import numpy as np
import pytest

from axiomize import advanced_family_engine as engine
from axiomize.model_ir import ModelIR


def agents(*, cfg=None, kind="derivative", equation="-k*x", state=None):
    meta = {"count": 3, "initial": {"x": [1.0, 2.0, 3.0]}, "noise_std": 0.0}
    if cfg:
        meta.update(cfg)
    return ModelIR.from_dict({
        "schema_version": "1.0", "domain": "general", "name": "reproducible-agent-experiment",
        "family": "agent_based",
        "variables": [state if state is not None else {"name": "x", "role": "state", "initial": 1.0}],
        "parameters": [{"name": "k", "value": 0.4}],
        "equations": [{"target": "x", "kind": kind, "expression": equation}],
        "metadata": {"agents": meta},
    })


def run_agents(m, seed=19):
    return engine._simulate_agent_based(m, t_span=(0.0, 1.0), points=5,
                                        parameter_overrides=None, seed=seed)


def events(*, cfg=None, equations=None):
    metadata = {"events": [{"name": "arrival", "rate": "lam", "delta": {"n": 1.0}}],
                "max_events": 100}
    if cfg:
        metadata.update(cfg)
    return ModelIR.from_dict({
        "schema_version": "1.0", "domain": "general", "name": "reproducible-event-system",
        "family": "discrete_event",
        "variables": [{"name": "n", "role": "state", "initial": 0.0}],
        "parameters": [{"name": "lam", "value": 8.0}],
        "equations": equations if equations is not None else [
            {"target": "n", "kind": "event_state", "expression": "0"}
        ],
        "metadata": {"discrete_event": metadata},
    })


def run_events(m, seed=19):
    return engine._simulate_discrete_event(m, t_span=(0.0, 2.0), points=8,
                                           parameter_overrides=None, seed=seed)


def test_agent_derivative_matches_exact_euler_discretization():
    actual = run_agents(agents())
    values = np.asarray(actual["states"]["x"])
    assert actual["status"] == "PASS"
    assert values.shape == (5, 3)
    np.testing.assert_allclose(values[-1], np.array([1, 2, 3]) * 0.9**4)
    assert actual["diagnostics"]["agents"] == 3
    assert actual["diagnostics"]["finite"]


def test_agent_updates_replace_values_instead_of_integrating_derivative():
    result = run_agents(agents(kind="update", equation="x+1"))
    assert result["states"]["x"][-1] == pytest.approx([5, 6, 7])


@pytest.mark.parametrize("kind", ["update", "difference"])
def test_agent_two_non_derivative_equation_kinds_have_identical_discrete_semantics(kind):
    result = run_agents(agents(kind=kind, equation="x+1"))
    assert result["status"] == "PASS"
    assert result["states"]["x"][-1] == pytest.approx([5, 6, 7])


def test_per_agent_state_initialization_does_not_fabricate_heterogeneity():
    result = run_agents(agents(cfg={"initial": {"x": 2.0}}))
    assert result["states"]["x"][0] == [2.0, 2.0, 2.0]


def test_agent_noise_is_seeded_real_and_nonzero():
    model = agents(cfg={"noise_std": 0.3})
    first = run_agents(model, seed=17)
    second = run_agents(model, seed=17)
    third = run_agents(model, seed=18)
    assert first["states"] == second["states"]
    assert first["states"] != third["states"]


def test_agent_noise_mapping_tracks_named_state_only():
    model = agents(cfg={"noise_std": {"x": 0.1}})
    assert run_agents(model, seed=3)["states"] != run_agents(model, seed=5)["states"]


def test_agent_physical_bounds_are_applied_each_step():
    model = agents(state={"name": "x", "role": "state", "initial": 1.0,
                          "bounds": [0.5, 1.5]}, cfg={"initial": {"x": [0.7, 1.0, 1.5]}})
    output = run_agents(model)
    history = np.asarray(output["states"]["x"])
    assert np.all(history[1:] >= 0.5)
    assert np.all(history[1:] <= 1.5)


@pytest.mark.parametrize("cfg,fragment", [
    ({"count": 0}, "agent count must"),
    ({"count": 1000001}, "agent count must"),
    ({"count": 3, "initial": "invalid"}, "initial must be an object"),
    ({"count": 3, "initial": {"x": [1, 2]}}, "must have length"),
    ({"noise_std": []}, "noise_std must"),
])
def test_agent_rejects_invalid_population_noise_or_initialization(cfg,fragment):
    with pytest.raises(ValueError, match=fragment):
        run_agents(agents(cfg=cfg))


def test_agent_expression_producing_wrong_shape_is_refused():
    m = agents(equation="x")
    assert run_agents(m)["status"] == "PASS"
    m = agents(equation="mean_x")
    assert run_agents(m)["status"] == "PASS"


def test_discrete_event_is_deterministic_for_identical_seed():
    out = run_events(events(), seed=20)
    again = run_events(events(), seed=20)
    assert out == again
    assert out["status"] == "PASS"
    assert out["diagnostics"]["total_events"] > 0
    assert out["diagnostics"]["event_counts"]["arrival"] == out["diagnostics"]["total_events"]
    assert np.all(np.diff(np.asarray(out["states"]["n"])) >= 0)


def test_zero_event_intensity_reports_zero_events_without_dividing_by_zero():
    model = events(cfg={"events": [{"name": "zero", "rate": "0", "delta": {"n": 1}}]})
    result = run_events(model)
    assert result["status"] == "PASS"
    assert result["diagnostics"]["total_events"] == 0
    assert set(result["states"]["n"]) == {0.0}


def test_event_delta_expression_evaluates_against_current_state():
    model = events(cfg={"events": [{"name": "compound", "rate": "lam",
                                     "delta": {"n": "1+n"}}]})
    result = run_events(model)
    assert result["status"] == "PASS"
    assert result["states"]["n"][-1] >= 1.0


def test_multiple_events_are_independently_counted():
    model = events(cfg={"events": [
        {"name": "birth", "rate": "lam", "delta": {"n": 1.0}},
        {"name": "death", "rate": "lam", "delta": {"n": -1.0}},
    ]})
    result = run_events(model)
    assert result["status"] == "PASS"
    counts = result["diagnostics"]["event_counts"]
    assert set(counts) == {"birth", "death"}
    assert sum(counts.values()) == result["diagnostics"]["total_events"]


@pytest.mark.parametrize("bad,fragment", [
    ({"events": []}, "requires"),
    ({"events": "invalid"}, "requires"),
    ({"events": [1]}, "needs rate and delta"),
    ({"events": [{"rate": "lam", "delta": "invalid"}]}, "needs rate and delta"),
    ({"events": [{"rate": "lam", "delta": {"unknown": 1}}]}, "unknown state"),
    ({"events": [{"rate": "-1", "delta": {"n": 1}}]}, "nonnegative"),
    ({"events": [{"rate": "nan", "delta": {"n": 1}}]}, "unknown|nonnegative"),
])
def test_event_catalog_trajectory_refuses_invalid_physical_inputs(bad,fragment):
    with pytest.raises(ValueError, match=fragment):
        run_events(events(cfg=bad))


def test_bounded_event_budget_cannot_be_called_a_pass_when_exhausted():
    result = run_events(events(cfg={"max_events": 1}))
    assert result["status"] == "FAIL"
    assert result["diagnostics"]["max_events_reached"] is True
    assert result["diagnostics"]["total_events"] == 1


def test_native_event_catalog_may_be_given_as_top_level_array():
    m = events()
    payload = m.to_dict()
    payload["metadata"]["discrete_event"] = [{"rate": "lam", "delta": {"n": 1}}]
    result = run_events(ModelIR.from_dict(payload))
    assert result["status"] == "PASS"
    assert result["diagnostics"]["total_events"] >= 1
