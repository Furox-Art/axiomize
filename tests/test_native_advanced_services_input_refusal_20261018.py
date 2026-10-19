"""Real approval-gated scientific service validation and native execution.

Uses declared Model IR only; external scientific evidence is not fabricated.
"""
from __future__ import annotations

import pytest

from axiomize.application import advanced_services as services
from axiomize.model_ir import ModelFamily
from axiomize.scientific_stress import _models


def physical_ode():
    return _models()[ModelFamily.ODE].to_dict()


def request(**fields):
    return {"model_ir": physical_ode(), "points": 15, **fields}


def uncertainty(**fields):
    return request(**{"parameter_uncertainty": {"k": {"distribution": "fixed", "value": 1.0}},
                      "samples": 4, **fields})


def bifurcation(**fields):
    return request(**{"parameter": "k", "values": [0.5, 1.0], **fields})


def numerical(**fields):
    return request(**{"tolerance": 0.001, **fields})


@pytest.mark.parametrize("fn,payload,expected_method", [
    (services.model_uncertainty_service, uncertainty(), "cost"),
    (services.model_bifurcation_service, bifurcation(), "cost"),
    (services.model_numerical_verification_service, numerical(), "study"),
])
def test_real_scientific_services_require_approval_before_repeated_work(fn, payload, expected_method):
    outcome = fn(payload)
    assert outcome["status"] == "APPROVAL_REQUIRED"
    assert expected_method in outcome
    assert outcome["validation"]["status"] == "PASS"
    assert "provenance" in outcome


@pytest.mark.parametrize("fn,payload", [
    (services.model_uncertainty_service, uncertainty(approve_heavy=True)),
    (services.model_bifurcation_service, bifurcation(approve_heavy=True)),
    (services.model_numerical_verification_service, numerical(approve_heavy=True)),
])
def test_authorized_native_scientific_services_execute_with_explicit_provenance(fn, payload):
    result = fn(payload)
    assert result["status"] == "PASS", result
    assert result["validation"]["status"] == "PASS"
    assert result["provenance"]
    assert result["provenance"]["model_family"] == "ode"
    if fn is services.model_uncertainty_service:
        assert result["successful_samples"] == 4
        assert result["failed_samples"] == 0
    elif fn is services.model_bifurcation_service:
        assert all(row["stability"]["max_real_part"] < 0 for row in result["rows"])
    else:
        assert result["converged"] is True


@pytest.mark.parametrize("fn", [
    services.model_uncertainty_service,
    services.model_bifurcation_service,
    services.model_numerical_verification_service,
])
def test_missing_model_is_refused_before_native_tool_invocation(fn):
    with pytest.raises(ValueError, match="requires a model_ir"):
        fn({})


@pytest.mark.parametrize("value, match", [
    ([], "contain"),
    ([1.0], "contain"),
    ([1.0, float("nan")], "finite"),
    ([2, 1], "strictly increasing"),
    ([1, 1], "strictly increasing"),
])
def test_native_time_span_is_explicit_finite_and_increasing(value, match):
    with pytest.raises(ValueError, match=match):
        services._span({"t_span": value})


@pytest.mark.parametrize("bad, match", [
    (None, "contain 1..2000"),
    ({}, "contain 1..2000"),
    ([1], "contain 1..2000"),
])
def test_uncertainty_contract_requires_a_declared_distribution(bad, match):
    with pytest.raises(ValueError, match=match):
        services.model_uncertainty_service(request(parameter_uncertainty=bad))


@pytest.mark.parametrize("quantiles, match", [
    ([0.5, 0.5], "strictly increasing"),
    ([0.9, 0.2], "strictly increasing"),
    ([-0.1, 0.5], "strictly increasing"),
    ([0.5, 1.1], "strictly increasing"),
    (["invalid", 0.5], "numeric"),
])
def test_uncertainty_quantiles_must_be_finite_and_ordered(quantiles, match):
    with pytest.raises(ValueError, match=match):
        services.model_uncertainty_service(uncertainty(quantiles=quantiles))


@pytest.mark.parametrize("values, match", [
    ([0.5], "length"),
    ([0.5, float("inf")], "finite"),
    ("invalid", "array"),
])
def test_scan_rejects_incomplete_or_nonfinite_parameter_ranges(values, match):
    with pytest.raises(ValueError, match=match):
        services.model_bifurcation_service(bifurcation(values=values))


def test_unknown_equilibrium_guess_cannot_hide_invalid_numbers():
    with pytest.raises(ValueError, match="must be finite"):
        services.model_bifurcation_service(bifurcation(equilibrium_guess={"x": float("nan")}))
    with pytest.raises(ValueError, match="equilibrium_guess must be an object"):
        services.model_bifurcation_service(bifurcation(equilibrium_guess=["x"]))


def test_numerical_refinement_rejects_zero_or_nonfinite_tolerance():
    for value, expected in [(0.0, "positive"), (-1.0, "positive"),
                            (float("nan"), "finite")]:
        with pytest.raises(ValueError, match=expected):
            services.model_numerical_verification_service(numerical(tolerance=value))


def test_early_validation_failure_never_runs_scientific_diagnostics():
    m = physical_ode()
    m["constraints"] = [{
        "name": "impossible_initial",
        "expression": "x", "relation": "ge", "threshold": 10.0,
        "scientific_basis": "initial state must exceed stated threshold",
    }]
    result = services.model_numerical_verification_service({"model_ir": m})
    assert result["status"] == "FAIL"
    assert result["stage"] == "pre_validation"


@pytest.mark.parametrize("history, expected", [
    ([1.0, 1.0, 1.0, 1.0], "STOP"),
    ([1.0, 0.8, 0.6, 0.4], "CONTINUE"),
])
def test_stopping_decision_reflects_real_convergence_history(history, expected):
    result = services.model_stopping_service({"history": history})
    assert result["decision"] == expected
    assert result["checks"]


@pytest.mark.parametrize("field, value, error", [
    ("relative_tolerance", -1, "non-negative"),
    ("absolute_tolerance", -1, "non-negative"),
    ("patience", 0, "between"),
    ("budget_used", -1, "non-negative"),
    ("budget_limit", -1, "non-negative"),
    ("uncertainty", -1, "non-negative"),
    ("uncertainty_target", -1, "non-negative"),
    ("budget_used", float("nan"), "finite"),
])
def test_stopping_contract_refuses_invalid_decision_boundary(field, value, error):
    with pytest.raises(ValueError, match=error):
        services.model_stopping_service({"history": [1, 1, 1], field: value})


def test_stopping_decision_with_reached_budget_is_explicit():
    result = services.model_stopping_service(
        {"history": [1.0, 0.7, 0.4, 0.1], "budget_used": 10, "budget_limit": 10}
    )
    assert result["decision"] == "STOP"
    assert "budget" in " ".join(result["reasons"])


@pytest.mark.parametrize("fn", [
    services.model_uncertainty_service,
    services.model_bifurcation_service,
    services.model_numerical_verification_service,
])
def test_legacy_ir_requires_explicit_schema_migration_approval(fn):
    legacy = {
        "name": "legacy", "domain": "physics", "model_family": "ode",
        "states": {"x": {"initial": 1.0}},
        "parameters": [{"name": "k", "value": 1.0}],
        "rhs": {"x": "-k*x"},
    }
    result = fn({"model_ir": legacy})
    assert result["status"] == "APPROVAL_REQUIRED"
    assert result["action"] == "ir_migration"
    assert result["migration"]["required"] is True


@pytest.mark.parametrize("fn", [
    services.model_uncertainty_service,
    services.model_bifurcation_service,
    services.model_numerical_verification_service,
])
def test_failed_initial_scientific_constraint_blocks_every_diagnostic(fn):
    model = physical_ode()
    model["constraints"] = [{
        "name": "impossible_state", "expression": "x",
        "relation": "ge", "threshold": 9.0,
        "scientific_basis": "declared initial lower bound",
    }]
    result = fn({"model_ir": model})
    assert result["status"] == "FAIL"
    assert result["stage"] == "pre_validation"
    assert any(row["status"] == "FAIL" for row in result["validation"]["scientific_constraints"])
