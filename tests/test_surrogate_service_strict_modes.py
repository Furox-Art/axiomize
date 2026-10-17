"""Service-level surrogate selection and unverified extrapolation controls."""

from __future__ import annotations

import numpy as np
import pytest

from axiomize.application.surrogate_services import _load_model, _mode, model_surrogate_service
from axiomize.model_ir import ModelIR


def decay():
    return ModelIR.from_dict(
        {
            "schema_version": "1.0",
            "name": "decay",
            "domain": "physics",
            "family": "ode",
            "variables": [{"name": "x", "initial": 1.0}],
            "parameters": [{"name": "k", "value": 0.5, "bounds": [0.0, 1.0]}],
            "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
        }
    ).to_dict()


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"mode": "  FIT "}, "fit"),
        ({"mode": "generate"}, "generate"),
        ({"mode": "EVALUATE"}, "evaluate"),
        ({"training_data": {}}, "fit"),
        ({"model_ir": {}}, "generate"),
        ({"surrogate": {}, "inputs": {}}, "evaluate"),
    ],
)
def test_surrogate_mode_selection_is_stable_and_not_guessed(payload, expected):
    assert _mode(payload) == expected


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"mode": "fictitious"},
        {"mode": "fit-all"},
        {"surrogate": {}},
    ],
)
def test_unknown_surrogate_mode_is_rejected(payload):
    with pytest.raises(ValueError):
        _mode(payload)


def test_surrogate_generation_requires_structured_explicit_model():
    with pytest.raises(ValueError, match="requires model_ir"):
        _load_model({"model_ir": "implicit equation"})


def test_legacy_surrogate_model_migration_requires_approval():
    legacy = {
        "name": "legacy",
        "domain": "physics",
        "model_family": "ode",
        "states": {"x": 1.0},
        "rhs": {"x": "-x"},
    }
    out = _load_model({"model_ir": legacy})
    assert out["status"] == "APPROVAL_REQUIRED"
    assert out["action"] == "ir_migration"


@pytest.mark.parametrize(
    ("payload", "pattern"),
    [
        ({"mode": "fit"}, "training_data object"),
        ({"mode": "fit", "training_data": {}}, "inputs and outputs objects"),
        ({"mode": "fit", "training_data": {"inputs": [], "outputs": []}}, "inputs and outputs objects"),
        ({"mode": "evaluate"}, "surrogate and inputs objects"),
        ({"mode": "evaluate", "inputs": {}}, "surrogate and inputs objects"),
        ({"mode": "generate", "model_ir": decay()}, "parameter_ranges object"),
        ({"mode": "generate", "model_ir": decay(), "parameter_ranges": {"k": [0.2, 0.5]}, "t_span": [0.0]}, "t_span"),
    ],
)
def test_surrogate_routes_refuse_incomplete_scientific_contract(payload, pattern):
    with pytest.raises(ValueError, match=pattern):
        model_surrogate_service(payload)


def test_fit_surrogate_uses_direct_supplied_data_not_hidden_full_model():
    x = np.linspace(-1.0, 1.0, 30)
    out = model_surrogate_service(
        {
            "mode": "fit",
            "degree": 1,
            "training_data": {"inputs": {"k": x.tolist()}, "outputs": {"y": (2 * x + 1).tolist()}},
        }
    )
    assert out["mode"] == "fit_from_supplied_data"
    assert out["surrogate"]["validation"]["validated"] is True
    assert out["status"] == "PASS"


def test_generated_surrogate_runs_only_with_explicit_heavy_compute_approval():
    args = {
        "mode": "generate",
        "model_ir": decay(),
        "parameter_ranges": {"k": [0.2, 0.8]},
        "samples": 12,
        "points": 8,
        "degree": 1,
        "t_span": [0.0, 0.5],
    }
    no = model_surrogate_service(args)
    assert no["status"] == "APPROVAL_REQUIRED", no
    assert "surrogate" not in no
    yes = model_surrogate_service({**args, "approve_heavy": True})
    assert yes["mode"] == "generated_from_full_model"
    assert yes["validation"]["status"] != "FAIL"
    assert yes["status"] in {"PASS", "SURROGATE_REJECTED"}


def test_surrogate_evaluation_fails_closed_outside_training_domain():
    x = np.linspace(-1.0, 1.0, 30)
    fitted = model_surrogate_service(
        {
            "mode": "fit",
            "degree": 1,
            "training_data": {"inputs": {"k": x.tolist()}, "outputs": {"y": (2 * x + 1).tolist()}},
        }
    )
    surrogate = fitted["surrogate"]
    blocked = model_surrogate_service(
        {
            "mode": "evaluate",
            "surrogate": surrogate,
            "inputs": {"k": 4.0},
        }
    )
    assert blocked["status"] == "OUT_OF_DOMAIN"
    assert "predictions" not in blocked
    override = model_surrogate_service(
        {
            "mode": "evaluate",
            "surrogate": surrogate,
            "inputs": {"k": 4.0},
            "allow_extrapolation": True,
        }
    )
    assert override["status"] == "UNVERIFIED_EXTRAPOLATION"


def test_unvalidated_surrogate_never_passes_without_override():
    x = np.linspace(-1.0, 1.0, 30)
    fit = model_surrogate_service(
        {
            "mode": "fit",
            "degree": 1,
            "training_data": {"inputs": {"k": x.tolist()}, "outputs": {"y": (2 * x + 1).tolist()}},
        }
    )
    artifact = fit["surrogate"]
    artifact["validation"]["validated"] = False
    blocked = model_surrogate_service({"mode": "evaluate", "surrogate": artifact, "inputs": {"k": 0.0}})
    assert blocked["status"] == "SURROGATE_REJECTED"
    override = model_surrogate_service(
        {
            "mode": "evaluate",
            "surrogate": artifact,
            "inputs": {"k": 0.0},
            "allow_unvalidated": True,
        }
    )
    assert override["surrogate_validation"]["validated"] is False
