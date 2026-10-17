"""Advanced services must preserve explicit evidence, controls, and finite inputs."""

from __future__ import annotations

import math

import pytest

from axiomize.application.advanced_services import (
    _finite,
    _load,
    _span,
    model_bifurcation_service,
    model_numerical_verification_service,
    model_stopping_service,
    model_uncertainty_service,
)
from axiomize.model_ir import ModelIR


@pytest.fixture
def model() -> dict:
    return ModelIR.from_dict(
        {
            "schema_version": "1.0",
            "domain": "physics",
            "name": "differential-rate",
            "family": "ode",
            "independent_unit": "day",
            "variables": [{"name": "x", "unit": "dimensionless", "initial": 1.0}],
            "parameters": [{"name": "k", "unit": "1/day", "value": 0.5, "bounds": [0.0, 2.0]}],
            "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
        }
    ).to_dict()


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("not-numeric", "numeric"),
        (None, "numeric"),
        ({}, "numeric"),
        (math.inf, "finite"),
        (math.nan, "finite"),
        (-math.inf, "finite"),
    ],
)
def test_advanced_finite_scalar_refuses_invalid_measurement(value, message):
    with pytest.raises(ValueError, match=message):
        _finite(value, name="measurement")


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({}, "requires a model_ir"),
        ({"model": "text"}, "requires a model_ir"),
        ({"model_ir": None}, "requires a model_ir"),
    ],
)
def test_advanced_requires_structured_model_ir(raw, message):
    with pytest.raises(ValueError, match=message):
        _load(raw)


def test_legacy_ir_requires_explicit_migration_permission():
    legacy = {
        "name": "legacy",
        "domain": "physics",
        "model_family": "ode",
        "states": {"x": {"unit": "dimensionless", "initial": 1.0}},
        "parameters": [{"name": "k", "value": 1.0, "unit": "1/day"}],
        "rhs": {"x": "-k*x"},
        "independent_unit": "day",
    }
    pending = _load({"model_ir": legacy})
    assert isinstance(pending, dict)
    assert pending["status"] == "APPROVAL_REQUIRED"
    assert pending["action"] == "ir_migration"
    converted = _load({"model_ir": legacy, "approve_migration": True})
    assert isinstance(converted, ModelIR)
    assert converted.provenance[-1].action == "model_ir_migration"


@pytest.mark.parametrize(
    ("span", "message"),
    [
        ([1.0], "must contain"),
        ([0.0, 0.0], "strictly increasing"),
        ([2.0, 1.0], "strictly increasing"),
        ([0.0, math.inf], "finite"),
        ([math.nan, 1.0], "finite"),
        ("1,2", "must contain"),
    ],
)
def test_time_range_requires_finite_increasing_interval(span, message):
    with pytest.raises(ValueError, match=message):
        _span({"t_span": span})


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "history must be an array"),
        ({"history": [math.nan]}, "finite"),
        ({"history": [0.0, 1.0], "relative_tolerance": math.inf}, "finite"),
        ({"history": [0.0, 1.0], "absolute_tolerance": -1.0}, "non-negative"),
        ({"history": [0.0, 1.0], "patience": 0}, "patience"),
        ({"history": [0.0, 1.0], "budget_used": -1.0}, "budget_used"),
        ({"history": [0.0, 1.0], "budget_limit": -1.0}, "budget_limit"),
        ({"history": [0.0, 1.0], "uncertainty": -1.0}, "uncertainty"),
        ({"history": [0.0, 1.0], "uncertainty_target": -1.0}, "uncertainty_target"),
    ],
)
def test_stopping_service_rejects_invalid_convergence_claims(payload, message):
    with pytest.raises(ValueError, match=message):
        model_stopping_service(payload)


def test_stopping_service_reports_each_supplied_stop_criterion():
    out = model_stopping_service(
        {
            "history": [1.0, 1.0, 1.0, 1.0],
            "patience": 2,
            "budget_used": 100,
            "budget_limit": 100,
            "uncertainty": 0.01,
            "uncertainty_target": 0.05,
        }
    )
    assert out["decision"] == "STOP"
    assert set(out["reasons"]) == {"incremental_improvement", "compute_budget", "uncertainty_target"}


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({}, "parameter_uncertainty"),
        ({"parameter_uncertainty": {}}, "parameter_uncertainty"),
        (
            {"parameter_uncertainty": {"k": {"distribution": "fixed", "value": 0.5}}, "quantiles": [0.7, 0.3]},
            "quantiles",
        ),
        (
            {"parameter_uncertainty": {"k": {"distribution": "fixed", "value": 0.5}}, "quantiles": [0.0, 0.0]},
            "quantiles",
        ),
        ({"parameter_uncertainty": {"k": {"distribution": "fixed", "value": 0.5}}, "quantiles": [math.nan]}, "finite"),
        ({"parameter_uncertainty": {"k": {"distribution": "fixed", "value": 0.5}}, "samples": 0}, "samples"),
        ({"parameter_uncertainty": {"k": {"distribution": "fixed", "value": 0.5}}, "points": 1}, "points"),
        (
            {"parameter_uncertainty": {"k": {"distribution": "fixed", "value": 0.5}}, "t_span": [2.0, 1.0]},
            "strictly increasing",
        ),
    ],
)
def test_uncertainty_service_rejects_unbounded_or_unordered_stochastic_evidence(model, changes, message):
    with pytest.raises(ValueError, match=message):
        model_uncertainty_service({"model_ir": model, **changes})


def test_unapproved_uncertainty_sampling_is_not_fake_monte_carlo_success(model):
    result = model_uncertainty_service(
        {
            "model_ir": model,
            "parameter_uncertainty": {"k": {"distribution": "normal", "mean": 0.5, "std": 0.1}},
            "samples": 6,
            "points": 6,
        }
    )
    assert result["status"] == "APPROVAL_REQUIRED", result
    assert "states" not in result
    assert result["provenance"]
    assert result["validation"]["status"] != "FAIL"


def test_approved_small_uncertainty_run_is_reproducible(model):
    kwargs = {
        "model_ir": model,
        "parameter_uncertainty": {"k": {"distribution": "normal", "mean": 0.5, "std": 0.1}},
        "samples": 5,
        "points": 6,
        "seed": 7,
        "t_span": [0.0, 0.2],
        "approve_heavy": True,
    }
    one = model_uncertainty_service(kwargs)
    two = model_uncertainty_service(kwargs)
    assert one["status"] == two["status"] == "PASS"
    assert one["parameter_draw_summary"] == two["parameter_draw_summary"]
    assert one["states"]["x"]["mean"] == two["states"]["x"]["mean"]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"values": [0.3]}, "values length"),
        ({"values": [0.3, math.nan]}, "finite"),
        ({"values": [0.3, 0.4], "equilibrium_guess": []}, "equilibrium_guess"),
        ({"values": [0.3, 0.4], "equilibrium_guess": {"x": math.inf}}, "finite"),
    ],
)
def test_bifurcation_service_rejects_invalid_scans(model, changes, message):
    with pytest.raises(ValueError, match=message):
        model_bifurcation_service({"model_ir": model, "parameter": "k", **changes})


def test_bifurcation_requires_approval_and_keeps_provenance(model):
    out = model_bifurcation_service({"model_ir": model, "parameter": "k", "values": [0.3, 0.4]})
    assert out["status"] == "APPROVAL_REQUIRED"
    assert out["provenance"]
    assert out["validation"]["status"] != "FAIL"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"points": 1}, "points"),
        ({"tolerance": math.inf}, "finite"),
        ({"tolerance": 0}, "positive"),
        ({"tolerance": -1}, "positive"),
        ({"t_span": [0.0, math.nan]}, "finite"),
    ],
)
def test_refinement_service_never_accepts_invalid_numeric_claims(model, changes, message):
    with pytest.raises(ValueError, match=message):
        model_numerical_verification_service({"model_ir": model, **changes})


def test_refinement_is_explicitly_approval_gated(model):
    out = model_numerical_verification_service({"model_ir": model, "t_span": [0.0, 1.0], "points": 10})
    assert out["status"] == "APPROVAL_REQUIRED", out
    assert out["validation"]["status"] != "FAIL"
    assert out["provenance"]
