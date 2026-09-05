"""Application services for approval-gated advanced Model IR diagnostics."""

from __future__ import annotations

from typing import Any

from axiomize.advanced_diagnostics import (
    bifurcation_scan,
    propagate_parameter_uncertainty,
    stopping_decision,
)
from axiomize.dimensional_engine import merge_dimension_checks
from axiomize.general_engine import numerical_refinement, provenance_snapshot, validate_model
from axiomize.model_ir import MigrationApprovalRequired, ModelIR


def _load(payload: dict[str, Any]) -> ModelIR | dict[str, Any]:
    raw = payload.get("model_ir", payload.get("model"))
    if not isinstance(raw, dict):
        raise ValueError("request requires a model_ir (or model) JSON object")
    try:
        return ModelIR.from_dict(raw, allow_migration=bool(payload.get("approve_migration", False)))
    except MigrationApprovalRequired as exc:
        return {"status": "APPROVAL_REQUIRED", "action": "ir_migration", "migration": exc.preview}


def model_uncertainty_service(payload: dict[str, Any]) -> dict[str, Any]:
    loaded = _load(payload)
    if isinstance(loaded, dict):
        return loaded
    model = loaded
    validation = merge_dimension_checks(validate_model(model), model)
    if validation["status"] == "FAIL":
        return {"status": "FAIL", "stage": "pre_validation", "validation": validation}
    uncertainty = payload.get("parameter_uncertainty")
    if not isinstance(uncertainty, dict) or not uncertainty:
        raise ValueError("parameter_uncertainty must be a non-empty object")
    span = payload.get("t_span", [0.0, 1.0])
    if not isinstance(span, (list, tuple)) or len(span) != 2:
        raise ValueError("t_span must contain [start, stop]")
    quantiles = payload.get("quantiles", [0.025, 0.5, 0.975])
    if not isinstance(quantiles, list):
        raise ValueError("quantiles must be an array")
    out = propagate_parameter_uncertainty(
        model,
        t_span=(float(span[0]), float(span[1])),
        parameter_uncertainty=uncertainty,
        points=int(payload.get("points", 200)),
        samples=int(payload.get("samples", 200)),
        seed=int(payload.get("seed", 0)),
        quantiles=tuple(float(v) for v in quantiles),
        approve_heavy=bool(payload.get("approve_heavy", False)),
    )
    out["validation"] = validation
    out["provenance"] = provenance_snapshot(model, seed=int(payload.get("seed", 0)), data_hash=payload.get("data_hash"))
    return out


def model_bifurcation_service(payload: dict[str, Any]) -> dict[str, Any]:
    loaded = _load(payload)
    if isinstance(loaded, dict):
        return loaded
    model = loaded
    validation = merge_dimension_checks(validate_model(model), model)
    if validation["status"] == "FAIL":
        return {"status": "FAIL", "stage": "pre_validation", "validation": validation}
    values = payload.get("values")
    if not isinstance(values, list):
        raise ValueError("bifurcation scan requires values array")
    guess = payload.get("equilibrium_guess")
    if guess is not None and not isinstance(guess, dict):
        raise ValueError("equilibrium_guess must be an object")
    out = bifurcation_scan(
        model,
        parameter=str(payload["parameter"]),
        values=[float(v) for v in values],
        equilibrium_guess={k: float(v) for k, v in guess.items()} if isinstance(guess, dict) else None,
        approve_heavy=bool(payload.get("approve_heavy", False)),
    )
    out["validation"] = validation
    out["provenance"] = provenance_snapshot(model, data_hash=payload.get("data_hash"))
    return out


def model_numerical_verification_service(payload: dict[str, Any]) -> dict[str, Any]:
    """Run an explicit mesh/tolerance refinement study after scientific validation."""
    loaded = _load(payload)
    if isinstance(loaded, dict):
        return loaded
    model = loaded
    validation = merge_dimension_checks(validate_model(model), model)
    if validation["status"] == "FAIL":
        return {"status": "FAIL", "stage": "pre_validation", "validation": validation}
    span = payload.get("t_span", [0.0, 1.0])
    if not isinstance(span, (list, tuple)) or len(span) != 2:
        raise ValueError("t_span must contain [start, stop]")
    out = numerical_refinement(
        model,
        t_span=(float(span[0]), float(span[1])),
        points=int(payload.get("points", 200)),
        parameter_overrides=payload.get("parameter_overrides"),
        seed=int(payload.get("seed", 0)),
        tolerance=float(payload.get("tolerance", 1e-3)),
        approve_heavy=bool(payload.get("approve_heavy", False)),
    )
    out["validation"] = validation
    out["provenance"] = provenance_snapshot(model, seed=int(payload.get("seed", 0)), data_hash=payload.get("data_hash"))
    return out


def model_stopping_service(payload: dict[str, Any]) -> dict[str, Any]:
    history = payload.get("history")
    if not isinstance(history, list):
        raise ValueError("stopping decision requires history array")
    return stopping_decision(
        [float(v) for v in history],
        relative_tolerance=float(payload.get("relative_tolerance", 1e-3)),
        absolute_tolerance=float(payload.get("absolute_tolerance", 1e-8)),
        patience=int(payload.get("patience", 3)),
        budget_used=None if payload.get("budget_used") is None else float(payload["budget_used"]),
        budget_limit=None if payload.get("budget_limit") is None else float(payload["budget_limit"]),
        uncertainty=None if payload.get("uncertainty") is None else float(payload["uncertainty"]),
        uncertainty_target=None if payload.get("uncertainty_target") is None else float(payload["uncertainty_target"]),
    )
