"""Application-service façade for the versioned general model engine."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from axiomize.dimensional_engine import merge_dimension_checks
from axiomize.general_engine import (
    build_execution_plan,
    discover_sparse_dynamics,
    export_model,
    fit_ode_model,
    infer_domain,
    local_stability,
    nondimensionalization_plan,
    provenance_snapshot,
    rank_experiment_times,
    rank_model_fits,
    recommend_model_families,
    repair_model,
    simulate_model,
    split_uncertainty,
    validate_model,
    validity_scan,
)
from axiomize.limits import (
    MAX_ARRAY_ITEMS,
    MAX_POINTS,
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


def _raw_model(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = payload.get("model_ir", payload.get("model"))
    if not isinstance(candidate, dict):
        raise ValueError("request requires a model_ir (or model) JSON object")
    return candidate


def _load_model(payload: dict[str, Any]) -> ModelIR:
    return ModelIR.from_dict(_raw_model(payload), allow_migration=bool(payload.get("approve_migration", False)))


def _load_or_approval(payload: dict[str, Any]) -> tuple[ModelIR | None, dict[str, Any] | None]:
    try:
        return _load_model(payload), None
    except MigrationApprovalRequired as exc:
        return None, {"status": "APPROVAL_REQUIRED", "action": "ir_migration", "migration": exc.preview}


def _span(payload: dict[str, Any]) -> tuple[float, float]:
    span = payload.get("t_span", [0.0, 1.0])
    if not isinstance(span, (list, tuple)) or len(span) != 2:
        raise ValueError("t_span must contain [start, stop]")
    start = _finite(span[0], name="t_span[0]")
    stop = _finite(span[1], name="t_span[1]")
    if stop <= start:
        raise ValueError("t_span must be strictly increasing")
    return start, stop


def _points(payload: dict[str, Any], *, default: int = 200) -> int:
    return bounded_int(payload.get("points", default), name="points", minimum=2, maximum=MAX_POINTS)


def model_plan_service(payload: dict[str, Any]) -> dict[str, Any]:
    """Plan model families from an idea or an execution plan from explicit IR."""
    raw = payload.get("model_ir", payload.get("model"))
    if isinstance(raw, dict):
        model, approval = _load_or_approval(payload)
        if approval is not None:
            return approval
        assert model is not None
        points = bounded_int(payload.get("points", 1000), name="points", minimum=1, maximum=MAX_POINTS)
        samples = bounded_int(payload.get("samples", 1), name="samples", minimum=1, maximum=MAX_SAMPLES)
        action = str(payload.get("action", "simulate"))
        return {
            "status": "PASS",
            "model_ir": model.to_dict(),
            "plan": build_execution_plan(model, action=action, points=points, samples=samples),
            "nondimensionalization": nondimensionalization_plan(model),
            "provenance": provenance_snapshot(model, seed=payload.get("seed"), data_hash=payload.get("data_hash")),
        }

    idea = str(payload.get("idea", "")).strip()
    if not idea:
        raise ValueError("model planning requires either idea or model_ir")
    if len(idea) > 200_000:
        raise ValueError("idea exceeds hard text limit of 200000 characters")
    inferred = infer_domain(idea)
    domain = str(payload.get("domain", inferred["domain"]))
    signals = payload.get("signals", [])
    if isinstance(signals, dict):
        if len(signals) > 10_000:
            raise ValueError("signals object exceeds hard limit 10000")
        signals = [key for key, value in signals.items() if value]
    if not isinstance(signals, list) or len(signals) > 10_000:
        raise ValueError("signals must be an array/object with at most 10000 entries")
    candidates = recommend_model_families(domain=domain, signals=[str(v) for v in signals], idea=idea)
    return {
        "status": "NEEDS_MODEL_IR",
        "domain": {**inferred, "selected": domain},
        "candidate_families": candidates,
        "candidate_count": len(candidates),
        "next_contract": {
            "required": ["variables", "parameters", "equations", "units", "assumptions"],
            "note": "An agent/provider may propose 2-3 concrete models; deterministic execution starts only after explicit Model IR is supplied.",
        },
    }


def model_validate_service(payload: dict[str, Any]) -> dict[str, Any]:
    model, approval = _load_or_approval(payload)
    if approval is not None:
        return approval
    assert model is not None
    validation = merge_dimension_checks(validate_model(model), model)
    return {
        "status": validation["status"],
        "model_ir": model.to_dict(),
        "validation": validation,
        "nondimensionalization": nondimensionalization_plan(model),
        "provenance": provenance_snapshot(model, seed=payload.get("seed"), data_hash=payload.get("data_hash")),
    }


def model_simulate_service(payload: dict[str, Any]) -> dict[str, Any]:
    model, approval = _load_or_approval(payload)
    if approval is not None:
        return approval
    assert model is not None
    pre_validation = merge_dimension_checks(validate_model(model), model)
    if pre_validation["status"] == "FAIL":
        return {"status": "FAIL", "stage": "pre_validation", "validation": pre_validation,
                "model_ir": model.to_dict(),
                "provenance": provenance_snapshot(model, seed=payload.get("seed"), data_hash=payload.get("data_hash"))}
    result = simulate_model(
        model,
        t_span=_span(payload),
        points=_points(payload),
        parameter_overrides=payload.get("parameter_overrides"),
        seed=int(payload.get("seed", 0)),
        approve_heavy=bool(payload.get("approve_heavy", False)),
    )
    if isinstance(result.get("validation"), dict):
        result["validation"] = merge_dimension_checks(result["validation"], model)
        if result["validation"]["status"] == "FAIL":
            result["status"] = "FAIL"
    result["provenance"] = provenance_snapshot(model, seed=int(payload.get("seed", 0)), data_hash=payload.get("data_hash"))
    return result


def model_fit_service(payload: dict[str, Any]) -> dict[str, Any]:
    model, approval = _load_or_approval(payload)
    if approval is not None:
        return approval
    assert model is not None
    validation = merge_dimension_checks(validate_model(model), model)
    if validation["status"] == "FAIL":
        return {"status": "FAIL", "stage": "pre_validation", "validation": validation}
    time_raw = payload.get("time", payload.get("t"))
    observations = payload.get("observations")
    time = bounded_sequence(time_raw, name="time", minimum=2, maximum=MAX_ARRAY_ITEMS)
    if not isinstance(observations, dict) or not observations or len(observations) > 1000:
        raise ValueError("fit requires a non-empty observations object with at most 1000 series")
    time_arr = np.asarray(time, dtype=float)
    if not np.all(np.isfinite(time_arr)) or np.any(np.diff(time_arr) <= 0):
        raise ValueError("fit time values must be finite and strictly increasing")
    clean_observations: dict[str, list[float]] = {}
    for name, values in observations.items():
        seq = bounded_sequence(values, name=f"observations.{name}", minimum=2, maximum=MAX_ARRAY_ITEMS)
        if len(seq) != len(time):
            raise ValueError(f"observations.{name} length must equal time length")
        arr = np.asarray(seq, dtype=float)
        if not np.all(np.isfinite(arr)):
            raise ValueError(f"observations.{name} must contain only finite values")
        clean_observations[str(name)] = arr.tolist()
    out = fit_ode_model(model, time=time_arr.tolist(), observations=clean_observations,
                        approve_heavy=bool(payload.get("approve_heavy", False)))
    if out.get("covariance") is not None:
        residual_stds = [float(v.get("std", 0.0)) for v in out.get("residual_diagnostics", {}).values() if isinstance(v, dict)]
        out["uncertainty_components"] = split_uncertainty(
            residual_std=max(residual_stds) if residual_stds else None,
            parameter_covariance=out.get("covariance"),
        )
    out["validation"] = validation
    out["provenance"] = provenance_snapshot(model, data_hash=payload.get("data_hash"))
    return out


def model_compare_service(payload: dict[str, Any]) -> dict[str, Any]:
    fits = payload.get("fits")
    if not isinstance(fits, dict) or not fits or len(fits) > 1000:
        raise ValueError("compare requires a non-empty fits object with at most 1000 candidates")
    return rank_model_fits(fits, criterion=str(payload.get("criterion", "bic")))


def model_repair_service(payload: dict[str, Any]) -> dict[str, Any]:
    model, approval = _load_or_approval(payload)
    if approval is not None:
        return approval
    assert model is not None
    supplied_validation = payload.get("validation")
    return repair_model(model, approve=bool(payload.get("approve_repair", False)),
                        validation=supplied_validation if isinstance(supplied_validation, dict) else None)


def model_export_service(payload: dict[str, Any]) -> dict[str, Any]:
    model, approval = _load_or_approval(payload)
    if approval is not None:
        return approval
    assert model is not None
    return export_model(model, format=str(payload.get("format", "json")))


def model_stability_service(payload: dict[str, Any]) -> dict[str, Any]:
    model, approval = _load_or_approval(payload)
    if approval is not None:
        return approval
    assert model is not None
    state = payload.get("state")
    if not isinstance(state, dict) or len(state) > 1000:
        raise ValueError("stability requires state object with at most 1000 entries")
    clean_state = {str(k): _finite(v, name=f"state.{k}") for k, v in state.items()}
    return local_stability(model, state=clean_state, parameter_overrides=payload.get("parameter_overrides"))


def model_validity_service(payload: dict[str, Any]) -> dict[str, Any]:
    model, approval = _load_or_approval(payload)
    if approval is not None:
        return approval
    assert model is not None
    values = bounded_sequence(payload.get("values"), name="values", minimum=2, maximum=MAX_SCAN_VALUES)
    clean_values = [_finite(v, name="values") for v in values]
    return validity_scan(model, parameter=str(payload["parameter"]), values=clean_values,
                         t_span=_span(payload), points=_points(payload),
                         approve_heavy=bool(payload.get("approve_heavy", False)))


def model_discovery_service(payload: dict[str, Any]) -> dict[str, Any]:
    time = bounded_sequence(payload.get("time"), name="time", minimum=3, maximum=MAX_ARRAY_ITEMS)
    state = bounded_sequence(payload.get("state"), name="state", minimum=3, maximum=MAX_ARRAY_ITEMS)
    if len(time) != len(state):
        raise ValueError("discovery time and state lengths must match")
    degree = bounded_int(payload.get("degree", 2), name="degree", minimum=1, maximum=8)
    threshold = _finite(payload.get("threshold", 1e-4), name="threshold")
    if threshold < 0:
        raise ValueError("threshold must be non-negative")
    return discover_sparse_dynamics(time=[_finite(v, name="time") for v in time],
                                    state=[_finite(v, name="state") for v in state], degree=degree,
                                    threshold=threshold, approve_heavy=bool(payload.get("approve_heavy", False)))


def experiment_design_service(payload: dict[str, Any]) -> dict[str, Any]:
    model, approval = _load_or_approval(payload)
    if approval is not None:
        return approval
    assert model is not None
    times = bounded_sequence(payload.get("candidate_times"), name="candidate_times", minimum=1, maximum=MAX_SCAN_VALUES)
    clean_times = [_finite(v, name="candidate_times") for v in times]
    horizon = _finite(payload["horizon"], name="horizon")
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    delta_fraction = _finite(payload.get("delta_fraction", 0.01), name="delta_fraction")
    if delta_fraction <= 0 or delta_fraction > 1:
        raise ValueError("delta_fraction must be in (0, 1]")
    return rank_experiment_times(model, parameter=str(payload["parameter"]), candidate_times=clean_times,
                                 horizon=horizon, delta_fraction=delta_fraction,
                                 approve_heavy=bool(payload.get("approve_heavy", False)))
