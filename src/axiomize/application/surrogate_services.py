"""Application service for validated surrogate/reduced-order modeling."""

from __future__ import annotations

from typing import Any

from axiomize.dimensional_engine import merge_dimension_checks
from axiomize.general_engine import validate_model
from axiomize.model_ir import MigrationApprovalRequired, ModelIR
from axiomize.surrogate import (
    evaluate_surrogate,
    fit_polynomial_surrogate,
    generate_and_fit_surrogate,
)


def _mode(payload: dict[str, Any]) -> str:
    explicit = payload.get("mode")
    if explicit is not None:
        mode = str(explicit).strip().lower()
        if mode not in {"fit", "generate", "evaluate"}:
            raise ValueError("surrogate mode must be fit, generate, or evaluate")
        return mode
    if isinstance(payload.get("surrogate"), dict) and isinstance(payload.get("inputs"), dict):
        return "evaluate"
    if isinstance(payload.get("training_data"), dict):
        return "fit"
    if isinstance(payload.get("model_ir", payload.get("model")), dict):
        return "generate"
    raise ValueError("cannot infer surrogate mode; provide mode=fit|generate|evaluate")


def _load_model(payload: dict[str, Any]) -> ModelIR | dict[str, Any]:
    raw = payload.get("model_ir", payload.get("model"))
    if not isinstance(raw, dict):
        raise ValueError("generate mode requires model_ir (or model)")
    try:
        return ModelIR.from_dict(raw, allow_migration=bool(payload.get("approve_migration", False)))
    except MigrationApprovalRequired as exc:
        return {"status": "APPROVAL_REQUIRED", "action": "ir_migration", "migration": exc.preview}


def model_surrogate_service(payload: dict[str, Any]) -> dict[str, Any]:
    """Fit, generate, or evaluate a scientifically guarded surrogate."""
    mode = _mode(payload)
    if mode == "evaluate":
        surrogate = payload.get("surrogate")
        inputs = payload.get("inputs")
        if not isinstance(surrogate, dict) or not isinstance(inputs, dict):
            raise ValueError("evaluate mode requires surrogate and inputs objects")
        return evaluate_surrogate(
            surrogate,
            inputs={str(k): float(v) for k, v in inputs.items()},
            allow_extrapolation=bool(payload.get("allow_extrapolation", False)),
            allow_unvalidated=bool(payload.get("allow_unvalidated", False)),
        )

    degree = int(payload.get("degree", 2))
    holdout_fraction = float(payload.get("holdout_fraction", 0.2))
    seed = int(payload.get("seed", 0))
    minimum_r2 = float(payload.get("minimum_r2", 0.95))
    maximum_nrmse = float(payload.get("maximum_nrmse", 0.10))

    if mode == "fit":
        training = payload.get("training_data")
        if not isinstance(training, dict):
            raise ValueError("fit mode requires training_data object")
        inputs = training.get("inputs")
        outputs = training.get("outputs")
        if not isinstance(inputs, dict) or not isinstance(outputs, dict):
            raise ValueError("training_data requires inputs and outputs objects")
        out = fit_polynomial_surrogate(
            inputs=inputs,
            outputs=outputs,
            degree=degree,
            ridge=float(payload.get("ridge", 1e-10)),
            holdout_fraction=holdout_fraction,
            seed=seed,
            minimum_r2=minimum_r2,
            maximum_nrmse=maximum_nrmse,
        )
        out["mode"] = "fit_from_supplied_data"
        return out

    loaded = _load_model(payload)
    if isinstance(loaded, dict):
        return loaded
    model = loaded
    validation = merge_dimension_checks(validate_model(model), model)
    if validation["status"] == "FAIL":
        return {"status": "FAIL", "stage": "pre_validation", "validation": validation}
    ranges = payload.get("parameter_ranges")
    if not isinstance(ranges, dict):
        raise ValueError("generate mode requires parameter_ranges object")
    span = payload.get("t_span", [0.0, 1.0])
    if not isinstance(span, (list, tuple)) or len(span) != 2:
        raise ValueError("t_span must contain [start, stop]")
    out = generate_and_fit_surrogate(
        model,
        parameter_ranges=ranges,
        output_specs=payload.get("output_specs"),
        t_span=(float(span[0]), float(span[1])),
        points=int(payload.get("points", 100)),
        samples=int(payload.get("samples", 32)),
        degree=degree,
        holdout_fraction=holdout_fraction,
        seed=seed,
        minimum_r2=minimum_r2,
        maximum_nrmse=maximum_nrmse,
        approve_heavy=bool(payload.get("approve_heavy", False)),
    )
    out["validation"] = validation
    out["mode"] = "generated_from_full_model"
    return out
