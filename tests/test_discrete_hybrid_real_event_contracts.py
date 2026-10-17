"""True Gillespie discrete events and hybrid ODE event safeguards."""

from __future__ import annotations

import math

import pytest

from axiomize.advanced_family_engine import _simulate_discrete_event, _simulate_hybrid
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, VariableSpec


def des(cfg=None, *, initial=0.0):
    return ModelIR(
        name="events",
        domain="biology",
        family=ModelFamily.DISCRETE_EVENT,
        variables=[VariableSpec("n", initial=initial)],
        parameters=[],
        equations=[EquationSpec("n", "0", kind="event_state")],
        metadata={
            "discrete_event": cfg
            if cfg is not None
            else {
                "events": [{"name": "arrival", "rate": "10", "delta": {"n": 1.0}}],
                "max_events": 1000,
            }
        },
    )


def hybrid(cfg=None, *, initial=1.0, equation=True):
    return ModelIR(
        name="bouncing",
        domain="physics",
        family=ModelFamily.HYBRID,
        variables=[VariableSpec("x", initial=initial)],
        parameters=[],
        equations=[EquationSpec("x", "-1", kind="derivative")] if equation else [],
        metadata={
            "hybrid": cfg
            if cfg is not None
            else {
                "events": [{"name": "reset", "expression": "x", "direction": -1, "reset": {"x": "1"}}],
                "max_events_per_interval": 20,
            }
        },
    )


def execute(fn, m, span=(0.0, 2.0), points=12, seed=5):
    return fn(m, t_span=span, points=points, parameter_overrides=None, seed=seed)


def test_actual_gillespie_arrivals_are_seed_reproducible_not_mean_field_proxy():
    first = execute(_simulate_discrete_event, des())
    second = execute(_simulate_discrete_event, des())
    third = execute(_simulate_discrete_event, des(), seed=6)
    assert first == second
    assert first["status"] == "PASS"
    assert first["diagnostics"]["total_events"] > 0
    assert first["solver"]["method"] == "gillespie_event_queue"
    assert first["states"]["n"] != third["states"]["n"]


def test_discrete_event_zero_rate_does_not_invent_any_arrivals():
    cfg = {"events": [{"rate": "0", "delta": {"n": 1.0}}]}
    out = execute(_simulate_discrete_event, des(cfg))
    assert out["status"] == "PASS"
    assert out["diagnostics"]["total_events"] == 0
    assert set(out["states"]["n"]) == {0.0}


def test_discrete_event_hit_max_events_is_explicit_fail_with_observed_count():
    cfg = {"events": [{"rate": "1000", "delta": {"n": 1.0}}], "max_events": 2}
    out = execute(_simulate_discrete_event, des(cfg))
    assert out["status"] == "FAIL"
    assert out["diagnostics"]["total_events"] == 2
    assert out["diagnostics"]["max_events_reached"] is True


@pytest.mark.parametrize(
    ("cfg", "message"),
    [
        ("invalid", "metadata.discrete_event"),
        ({"events": []}, "requires metadata.discrete_event.events"),
        ({"events": [{}]}, "rate and delta mapping"),
        ({"events": [{"rate": "1", "delta": {"unknown": 1}}]}, "unknown state"),
        ({"events": [{"rate": "-1", "delta": {"n": 1}}]}, "rates must be finite and nonnegative"),
    ],
)
def test_event_model_rejects_invalid_rates_and_implicit_state_update(cfg, message):
    with pytest.raises(ValueError, match=message):
        execute(_simulate_discrete_event, des(cfg))


def test_discrete_event_initial_population_must_be_observed():
    with pytest.raises(ValueError, match="finite initial"):
        execute(_simulate_discrete_event, des(initial=None))


def test_hybrid_reset_events_use_numerical_root_not_inferred_time():
    out = execute(_simulate_hybrid, hybrid(), span=(0.0, 2.3), points=12)
    assert out["status"] == "PASS", out
    assert out["solver"]["method"] == "event_driven_piecewise_ode"
    assert len(out["events"]) >= 1
    assert out["events"][0]["name"] == "reset"
    assert out["events"][0]["time"] == pytest.approx(1.0, abs=1e-4)
    assert math.isfinite(out["states"]["x"][-1])


def test_hybrid_without_events_is_ordinary_continuous_ode_without_false_reset():
    out = execute(_simulate_hybrid, hybrid({"events": []}), span=(0.0, 0.5), points=6)
    assert out["status"] == "PASS", out
    assert out["events"] == []
    assert out["states"]["x"][-1] == pytest.approx(0.5, abs=1e-7)


@pytest.mark.parametrize(
    ("cfg", "message"),
    [
        ([], "metadata.hybrid"),
        ({"events": "bad"}, "hybrid.events must be an array"),
        ({"events": [{}]}, "requires expression"),
        ({"events": [{"expression": "x", "reset": []}]}, "reset must be an object"),
        ({"events": [{"expression": "x", "reset": {"other": "1"}}]}, "unknown states"),
    ],
)
def test_hybrid_event_definition_must_be_directly_specified(cfg, message):
    with pytest.raises(ValueError, match=message):
        execute(_simulate_hybrid, hybrid(cfg))


def test_hybrid_missing_derivative_cannot_be_replaced_with_reference_model():
    with pytest.raises(ValueError, match="missing derivative equations"):
        execute(_simulate_hybrid, hybrid(equation=False))


def test_hybrid_missing_initial_state_rejected():
    with pytest.raises(ValueError, match="finite initial"):
        execute(_simulate_hybrid, hybrid(initial=None))
