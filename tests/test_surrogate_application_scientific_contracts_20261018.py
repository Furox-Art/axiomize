"""End-to-end surrogate service routing, validation and non-fabrication."""
from __future__ import annotations

import numpy as np
import pytest

from axiomize.application import surrogate_services as service
from axiomize.model_ir import ModelFamily
from axiomize.scientific_stress import _models


def physical_ode():
    return _models()[ModelFamily.ODE].to_dict()


def observed_training():
    x = np.linspace(-1.0, 1.0, 24)
    return {"inputs": {"x": x.tolist()}, "outputs": {"y": (1.0 + 2*x + 0.5*x*x).tolist()}}


@pytest.mark.parametrize("payload, expected", [
    ({"mode": " FIT "}, "fit"),
    ({"mode": "generate"}, "generate"),
    ({"mode": "evaluate"}, "evaluate"),
    ({"training_data": {"inputs": {}, "outputs": {}}}, "fit"),
    ({"surrogate": {}, "inputs": {}}, "evaluate"),
    ({"model_ir": {}}, "generate"),
])
def test_surrogate_mode_is_inferred_only_from_declared_evidence(payload, expected):
    assert service._mode(payload) == expected


@pytest.mark.parametrize("payload", [
    {}, {"mode": "guess"}, {"inputs": {"x": 1}},
    {"training_data": None},
])
def test_ambiguous_surrogate_routes_are_refused(payload):
    with pytest.raises(ValueError, match="cannot infer|must be fit"):
        service._mode(payload)


def test_real_surrogate_fit_and_evaluation_are_grounded_in_supplied_data():
    fit = service.model_surrogate_service({
        "mode": "fit", "training_data": observed_training(),
        "degree": 2, "seed": 9,
    })
    assert fit["status"] == "PASS"
    assert fit["mode"] == "fit_from_supplied_data"
    result = service.model_surrogate_service({
        "mode": "evaluate", "surrogate": fit["surrogate"], "inputs": {"x": 0.3},
    })
    assert result["status"] == "PASS"
    assert result["predictions"]["y"] == pytest.approx(1 + 2*0.3 + 0.5*0.3**2, abs=1e-6)


def test_surrogate_extrapolation_is_not_implicitly_authorized():
    fit = service.model_surrogate_service({"training_data": observed_training(), "degree": 2})
    extrapolated = service.model_surrogate_service({
        "mode": "evaluate", "surrogate": fit["surrogate"], "inputs": {"x": 100.0},
    })
    assert extrapolated["status"] != "PASS"


@pytest.mark.parametrize("payload, expected", [
    ({"mode": "evaluate"}, "evaluate mode requires"),
    ({"mode": "evaluate", "surrogate": [], "inputs": {}}, "evaluate mode requires"),
    ({"mode": "fit"}, "fit mode requires"),
    ({"mode": "fit", "training_data": []}, "fit mode requires"),
    ({"mode": "fit", "training_data": {"inputs": []}}, "requires inputs and outputs"),
    ({"mode": "generate"}, "generate mode requires"),
    ({"mode": "generate", "model_ir": physical_ode()}, "parameter_ranges"),
])
def test_surrogate_service_rejects_missing_required_data(payload, expected):
    with pytest.raises(ValueError, match=expected):
        service.model_surrogate_service(payload)


def test_surrogate_generation_retains_cost_approval_gate():
    result = service.model_surrogate_service({
        "mode": "generate", "model_ir": physical_ode(),
        "parameter_ranges": {"k": [0.5, 1.5]},
        "samples": 16, "points": 12,
    })
    assert result["status"] == "APPROVAL_REQUIRED"
    assert result["cost"]["requires_user_approval"] is True
    assert result["mode"] == "generated_from_full_model"


def test_unverified_physical_constraints_block_surrogate_generation():
    model = physical_ode()
    model["constraints"] = [{"name": "inconsistent_state", "expression": "x", "relation": "ge",
                            "threshold": 10.0, "scientific_basis": "stated physical bound"}]
    result = service.model_surrogate_service({
        "mode": "generate", "model_ir": model,
        "parameter_ranges": {"k": [0.1, 1.0]},
    })
    assert result["status"] == "FAIL"
    assert result["stage"] == "pre_validation"


@pytest.mark.parametrize("span", [
    [], [0.0], [0.0, 1.0, 2.0], "invalid",
])
def test_surrogate_generation_refuses_incomplete_time_domain(span):
    with pytest.raises(ValueError, match="t_span must contain"):
        service.model_surrogate_service({
            "mode": "generate", "model_ir": physical_ode(),
            "parameter_ranges": {"k": [0.1, 1.0]}, "t_span": span,
        })


def test_legacy_model_migration_requires_approval():
    legacy = {
        "name": "legacy-surrogate", "domain": "physics", "model_family": "ode",
        "states": {"x": {"initial": 1.0}},
        "parameters": [{"name": "k", "value": 1.0}], "rhs": {"x": "-k*x"},
    }
    out = service.model_surrogate_service({"mode": "generate", "model_ir": legacy})
    assert out["status"] == "APPROVAL_REQUIRED"
    assert out["action"] == "ir_migration"
    assert out["migration"]["required"]


def test_surrogate_mode_does_not_accept_unknown_explicit_action():
    with pytest.raises(ValueError, match="mode must be"):
        service.model_surrogate_service({"mode": "causal-inference"})
