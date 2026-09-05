from __future__ import annotations

import math

import pytest

from axiomize.application.advanced_services import model_numerical_verification_service
from axiomize.general_engine import simulate_model
from axiomize.model_ir import ModelIR


def _model(payload: dict) -> ModelIR:
    return ModelIR.from_dict({"schema_version": "1.0", "domain": "general", **payload})


def _pde() -> ModelIR:
    return _model({
        "name": "verified-reaction-diffusion",
        "family": "pde",
        "variables": [{"name": "u", "initial": 1.0}],
        "parameters": [{"name": "k", "value": 0.5}],
        "equations": [{"target": "u", "expression": "-k*u", "kind": "derivative"}],
        "metadata": {
            "pde": {
                "grid_points": 9,
                "space_span": [0.0, 1.0],
                "diffusion": {"u": 0.1},
                "boundary_conditions": {
                    "u": {
                        "left": {"type": "neumann", "value": 0.0},
                        "right": {"type": "neumann", "value": 0.0},
                    }
                },
            }
        },
    })


def _dae() -> ModelIR:
    return _model({
        "name": "verified-index1-dae",
        "family": "dae",
        "variables": [
            {"name": "x", "initial": 1.0},
            {"name": "z", "initial": 1.0, "role": "latent"},
        ],
        "parameters": [{"name": "k", "value": 1.0}],
        "equations": [
            {"target": "x", "expression": "-z", "kind": "derivative"},
            {"target": "", "expression": "z-k*x", "kind": "residual"},
        ],
    })


def test_pde_simulation_surfaces_approval_for_mesh_refinement() -> None:
    out = simulate_model(_pde(), t_span=(0.0, 1.0), points=21)
    assert out["status"] == "PASS"
    verification = out["numerical_verification"]
    assert verification["status"] == "APPROVAL_REQUIRED"
    assert verification["study"] == "mesh_refinement"
    assert verification["cost"]["requires_user_approval"] is True
    assert out["diagnostics"]["discretization_error"] == "pending explicit approval for numerical refinement"


def test_approved_pde_mesh_refinement_converges_and_separates_uncertainty() -> None:
    out = simulate_model(_pde(), t_span=(0.0, 1.0), points=21, approve_heavy=True)
    assert out["status"] == "PASS"
    verification = out["numerical_verification"]
    assert verification["status"] == "PASS"
    assert verification["converged"] is True
    assert len(verification["levels"]) >= 2
    assert math.isfinite(float(verification["estimated_numerical_error"]))
    assert float(verification["estimated_numerical_error"]) < 1e-5
    separated = verification["uncertainty_separation"]
    assert isinstance(separated["numerical"], float)
    assert "separate" in separated["parameter"]
    assert "separate" in separated["data"]
    assert "separate" in separated["model_structural"]


def test_approved_dae_tolerance_refinement_converges() -> None:
    out = simulate_model(_dae(), t_span=(0.0, 1.0), points=25, approve_heavy=True)
    assert out["status"] == "PASS"
    assert out["states"]["x"][-1] == pytest.approx(math.exp(-1.0), rel=5e-3)
    verification = out["numerical_verification"]
    assert verification["study"] == "solver_tolerance_refinement"
    assert verification["status"] == "PASS"
    assert verification["converged"] is True
    assert float(verification["estimated_numerical_error"]) < 1e-3


def test_explicit_service_is_approval_gated() -> None:
    payload = {
        "model_ir": _pde().to_dict(),
        "t_span": [0.0, 1.0],
        "points": 21,
        "tolerance": 1e-3,
    }
    blocked = model_numerical_verification_service(payload)
    assert blocked["status"] == "APPROVAL_REQUIRED"
    approved = model_numerical_verification_service({**payload, "approve_heavy": True})
    assert approved["status"] == "PASS"
    assert approved["study"] == "mesh_refinement"
    assert approved["validation"]["status"] == "PASS"
    assert "provenance" in approved


def test_non_discretized_family_uses_reproducibility_verification() -> None:
    algebraic = _model({
        "name": "algebraic-verification",
        "family": "algebraic",
        "variables": [{"name": "y", "initial": 1.0}],
        "parameters": [],
        "equations": [{"target": "y", "expression": "1", "kind": "algebraic"}],
    })
    payload = {"model_ir": algebraic.to_dict(), "points": 20, "tolerance": 1e-12}
    blocked = model_numerical_verification_service(payload)
    assert blocked["status"] == "APPROVAL_REQUIRED"
    assert blocked["study"] == "same_seed_reproducibility"
    approved = model_numerical_verification_service({**payload, "approve_heavy": True})
    assert approved["status"] == "PASS"
    assert approved["study"] == "same_seed_reproducibility"
    assert approved["converged"] is True
    assert float(approved["estimated_numerical_error"]) <= 1e-12
