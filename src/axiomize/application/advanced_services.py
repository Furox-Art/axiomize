"""Application services for approval-gated advanced Model IR diagnostics."""

from __future__ import annotations

import math
from typing import Any

from axiomize.advanced_diagnostics import bifurcation_scan, propagate_parameter_uncertainty, stopping_decision
from axiomize.dimensional_engine import merge_dimension_checks
from axiomize.general_engine import numerical_refinement, provenance_snapshot, validate_model
from axiomize.limits import (
    MAX_ARRAY_ITEMS,
    MAX_POINTS,
    MAX_QUANTILES,
    MAX_SAMPLES,
    MAX_SCAN_VALUES,
    bounded_int,
    bounded_sequence,
)
from axiomize.model_ir import MigrationApprovalRequired, ModelIR


def _finite(value: Any, *, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _load(payload: dict[str, Any]) -> ModelIR | dict[str, Any]:
    raw = payload.get("model_ir", payload.get("model"))
    if not isinstance(raw, dict):
        raise ValueError("request requires a model_ir (or model) JSON object")
    try:
        return ModelIR.from_dict(raw, allow_migration=bool(payload.get("approve_migration", False)))
    except MigrationApprovalRequired as exc:
        return {"status": "APPROVAL_REQUIRED", "action": "ir_migration", "migration": exc.preview}


def _span(payload: dict[str, Any]) -> tuple[float, float]:
    span = payload.get("t_span", [0.0, 1.0])
    if not isinstance(span, (list, tuple)) or len(span) != 2:
        raise ValueError("t_span must contain [start, stop]")
    start = _finite(span[0], name="t_span[0]")
    stop = _finite(span[1], name="t_span[1]")
    if stop <= start:
        raise ValueError("t_span must be strictly increasing")
    return start, stop


def model_uncertainty_service(payload: dict[str, Any]) -> dict[str, Any]:
    loaded = _load(payload)
    if isinstance(loaded, dict):
        return loaded
    model = loaded
    validation = merge_dimension_checks(validate_model(model), model)
    if validation["status"] == "FAIL":
        return {"status": "FAIL", "stage": "pre_validation", "validation": validation}
    uncertainty = payload.get("parameter_uncertainty")
    if not isinstance(uncertainty, dict) or not uncertainty or len(uncertainty) > 2000:
        raise ValueError("parameter_uncertainty must contain 1..2000 parameters")
    quantiles_raw = bounded_sequence(payload.get("quantiles", [0.025, 0.5, 0.975]),
                                     name="quantiles", minimum=1, maximum=MAX_QUANTILES)
    quantiles = tuple(_finite(v, name="quantile") for v in quantiles_raw)
    if any(v < 0 or v > 1 for v in quantiles) or any(b <= a for a, b in zip(quantiles, quantiles[1:])):
        raise ValueError("quantiles must be strictly increasing values in [0, 1]")
    points = bounded_int(payload.get("points", 200), name="points", minimum=2, maximum=MAX_POINTS)
    samples = bounded_int(payload.get("samples", 200), name="samples", minimum=1, maximum=MAX_SAMPLES)
    out = propagate_parameter_uncertainty(
        model, t_span=_span(payload), parameter_uncertainty=uncertainty, points=points, samples=samples,
        seed=int(payload.get("seed", 0)), quantiles=quantiles,
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
    values_raw = bounded_sequence(payload.get("values"), name="values", minimum=2, maximum=MAX_SCAN_VALUES)
    values = [_finite(v, name="bifurcation value") for v in values_raw]
    guess = payload.get("equilibrium_guess")
    if guess is not None and (not isinstance(guess, dict) or len(guess) > 1000):
        raise ValueError("equilibrium_guess must be an object with at most 1000 entries")
    clean_guess = {str(k): _finite(v, name=f"equilibrium_guess.{k}") for k, v in guess.items()} if isinstance(guess, dict) else None
    out = bifurcation_scan(model, parameter=str(payload["parameter"]), values=values,
                           equilibrium_guess=clean_guess, approve_heavy=bool(payload.get("approve_heavy", False)))
    out["validation"] = validation
    out["provenance"] = provenance_snapshot(model, data_hash=payload.get("data_hash"))
    return out


def model_numerical_verification_service(payload: dict[str, Any]) -> dict[str, Any]:
    loaded = _load(payload)
    if isinstance(loaded, dict):
        return loaded
    model = loaded
    validation = merge_dimension_checks(validate_model(model), model)
    if validation["status"] == "FAIL":
        return {"status": "FAIL", "stage": "pre_validation", "validation": validation}
    points = bounded_int(payload.get("points", 200), name="points", minimum=2, maximum=MAX_POINTS)
    tolerance = _finite(payload.get("tolerance", 1e-3), name="tolerance")
    if tolerance <= 0:
        raise ValueError("tolerance must be positive")
    out = numerical_refinement(model, t_span=_span(payload), points=points,
                               parameter_overrides=payload.get("parameter_overrides"), seed=int(payload.get("seed", 0)),
                               tolerance=tolerance, approve_heavy=bool(payload.get("approve_heavy", False)))
    out["validation"] = validation
    out["provenance"] = provenance_snapshot(model, seed=int(payload.get("seed", 0)), data_hash=payload.get("data_hash"))
    return out


def model_stopping_service(payload: dict[str, Any]) -> dict[str, Any]:
    history_raw = bounded_sequence(payload.get("history"), name="history", minimum=1, maximum=MAX_ARRAY_ITEMS)
    history = [_finite(v, name="history") for v in history_raw]
    relative = _finite(payload.get("relative_tolerance", 1e-3), name="relative_tolerance")
    absolute = _finite(payload.get("absolute_tolerance", 1e-8), name="absolute_tolerance")
    if relative < 0 or absolute < 0:
        raise ValueError("stopping tolerances must be non-negative")
    patience = bounded_int(payload.get("patience", 3), name="patience", minimum=1, maximum=MAX_ARRAY_ITEMS)

    optional: dict[str, float | None] = {}
    for name in ("budget_used", "budget_limit", "uncertainty", "uncertainty_target"):
        optional[name] = None if payload.get(name) is None else _finite(payload[name], name=name)
    if optional["budget_used"] is not None and optional["budget_used"] < 0:
        raise ValueError("budget_used must be non-negative")
    if optional["budget_limit"] is not None and optional["budget_limit"] < 0:
        raise ValueError("budget_limit must be non-negative")
    if optional["uncertainty"] is not None and optional["uncertainty"] < 0:
        raise ValueError("uncertainty must be non-negative")
    if optional["uncertainty_target"] is not None and optional["uncertainty_target"] < 0:
        raise ValueError("uncertainty_target must be non-negative")
    return stopping_decision(history, relative_tolerance=relative, absolute_tolerance=absolute, patience=patience,
                             budget_used=optional["budget_used"], budget_limit=optional["budget_limit"],
                             uncertainty=optional["uncertainty"], uncertainty_target=optional["uncertainty_target"])
