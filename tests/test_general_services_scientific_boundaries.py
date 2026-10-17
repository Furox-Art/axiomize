"""Service guards for finite observations, explicit IR, and approval-gated science."""

from __future__ import annotations

import math

import pytest

from axiomize.application.general_services import (
    _finite,
    _points,
    _raw_model,
    _span,
    experiment_design_service,
    model_compare_service,
    model_discovery_service,
    model_fit_service,
    model_plan_service,
    model_simulate_service,
    model_stability_service,
    model_validity_service,
)
from axiomize.model_ir import ModelIR


@pytest.fixture
def model() -> dict:
    return ModelIR.from_dict(
        {
            "schema_version": "1.0",
            "name": "decay",
            "domain": "physics",
            "family": "ode",
            "variables": [{"name": "x", "initial": 1.0}],
            "parameters": [{"name": "k", "value": 0.5, "bounds": [0.1, 1.0]}],
            "equations": [{"target": "x", "kind": "derivative", "expression": "-k*x"}],
        }
    ).to_dict()


@pytest.mark.parametrize(("value", "expected"), [(0, 0.0), ("1.5", 1.5), (-2, -2.0)])
def test_finite_converts_valid_numeric_scalar(value, expected):
    assert _finite(value, name="example") == pytest.approx(expected)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, {}, None, "unknown"])
def test_finite_refuses_non_numbers_and_nonfinite_observations(value):
    with pytest.raises(ValueError, match="must be (finite|numeric)"):
        _finite(value, name="measurement")


def test_raw_model_requires_explicit_structured_scientific_ir():
    with pytest.raises(ValueError, match="requires a model_ir"):
        _raw_model({"idea": "maybe an oscillator"})


@pytest.mark.parametrize(
    ("span", "message"),
    [
        ([1.0], "must contain"),
        ("1,2", "must contain"),
        ([0.0, 0.0], "strictly increasing"),
        ([2.0, 1.0], "strictly increasing"),
        ([0.0, math.inf], "finite"),
        ([math.nan, 2.0], "finite"),
    ],
)
def test_time_span_requires_real_strictly_increasing_bounds(span, message):
    with pytest.raises(ValueError, match=message):
        _span({"t_span": span})


@pytest.mark.parametrize("points", [0, 1, -1, math.nan])
def test_sampling_resolution_never_degenerates_to_single_point(points):
    with pytest.raises(ValueError):
        _points({"points": points})


@pytest.mark.parametrize(
    ("idea", "signals", "status"),
    [
        ("brain imaging", ["network"], "NEEDS_MODEL_IR"),
        ("chemical kinetics", {"reaction": True, "noise": False}, "NEEDS_MODEL_IR"),
    ],
)
def test_scientific_idea_is_planning_only_not_a_fabricated_model(idea, signals, status):
    plan = model_plan_service({"idea": idea, "signals": signals})
    assert plan["status"] == status
    assert "model_ir" not in plan
    assert plan["next_contract"]["required"]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "either idea or model_ir"),
        ({"idea": " "}, "either idea or model_ir"),
        ({"idea": "x", "signals": "bad"}, "signals must be"),
        ({"idea": "x", "signals": {"k": True} | {str(i): True for i in range(10001)}}, "signals object exceeds"),
    ],
)
def test_planning_rejects_unusable_ideas_and_invalid_signals(payload, message):
    with pytest.raises(ValueError, match=message):
        model_plan_service(payload)


def test_valid_ode_service_runs_actual_decay_not_a_stub(model):
    out = model_simulate_service({"model_ir": model, "points": 6, "t_span": [0.0, 0.4]})
    assert out["status"] == "PASS", out
    assert out["states"]["x"][-1] == pytest.approx(math.exp(-0.2), abs=0.01)
    assert out["provenance"]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"observations": {}, "time": [0, 1, 2]}, "non-empty observations"),
        ({"observations": {"x": [1, 2]}, "time": [0, 1, 2]}, "length must equal"),
        ({"observations": {"x": [1, float("nan"), 3]}, "time": [0, 1, 2]}, "only finite"),
        ({"observations": {"x": [1, 2, 3]}, "time": [0, 1, 1]}, "strictly increasing"),
        ({"observations": {"x": [1, 2, 3]}, "time": [0, 2, 1]}, "strictly increasing"),
    ],
)
def test_parameter_fit_never_accepts_inconsistent_scientific_samples(model, changes, message):
    with pytest.raises(ValueError, match=message):
        model_fit_service({"model_ir": model, **changes})


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("state", [], "requires state object"),
        ("state", {"x": float("nan")}, "must be finite"),
    ],
)
def test_local_stability_requires_finite_named_state(model, key, value, message):
    with pytest.raises(ValueError, match=message):
        model_stability_service({"model_ir": model, key: value})


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"values": [0.3]}, "values length must be between"),
        ({"values": [0.3, float("nan")]}, "finite"),
        ({"values": [0.3, 0.5], "t_span": [2, 1]}, "strictly increasing"),
    ],
)
def test_validity_scan_requires_explicit_bounded_finite_domain(model, changes, message):
    with pytest.raises(ValueError, match=message):
        model_validity_service({"model_ir": model, "parameter": "k", **changes})


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"time": [0.0, 1.0, 2.0, 3.0], "state": [1.0, 2.0, 3.0]}, "lengths must match"),
        ({"time": [0.0, 1.0, 2.0], "state": [1.0, 2.0, 3.0], "degree": 0}, "degree"),
        ({"time": [0.0, 1.0, 2.0], "state": [1.0, 2.0, 3.0], "threshold": -1}, "non-negative"),
    ],
)
def test_sparse_discovery_never_silently_repairs_invalid_scientific_series(changes, message):
    with pytest.raises(ValueError, match=message):
        model_discovery_service(changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"candidate_times": [0.1, 0.2], "horizon": 0}, "positive"),
        ({"candidate_times": [0.1, 0.2], "horizon": 1.0, "delta_fraction": 0}, "delta_fraction"),
        ({"candidate_times": [0.1, 0.2], "horizon": 1.0, "delta_fraction": 2}, "delta_fraction"),
        ({"candidate_times": [0.1, float("inf")], "horizon": 1.0}, "finite"),
    ],
)
def test_experiment_design_refuses_invalid_budget_or_future_times(model, changes, message):
    with pytest.raises(ValueError, match=message):
        experiment_design_service({"model_ir": model, "parameter": "k", **changes})


def test_model_comparison_requires_actual_candidates():
    with pytest.raises(ValueError, match="non-empty fits"):
        model_compare_service({"fits": {}})
