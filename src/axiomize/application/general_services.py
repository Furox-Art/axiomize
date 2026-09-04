"""Application-service façade for the versioned general model engine."""

from __future__ import annotations

from typing import Any

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
from axiomize.model_ir import MigrationApprovalRequired, ModelIR, migration_preview


def _raw_model(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = payload.get("model_ir", payload.get("model"))
    if not isinstance(candidate, dict):
        raise ValueError("request requires a model_ir (or model) JSON object")
    return candidate


def _load_model(payload: dict[str, Any]) -> ModelIR:
    raw = _raw_model(payload)
    return ModelIR.from_dict(raw, allow_migration=bool(payload.get("approve_migration", False)))


def model_plan_service(payload: dict[str, Any]) -> dict[str, Any]:
    """Plan model families from an idea or an execution plan from explicit IR."""
    raw = payload.get("model_ir", payload.get("model"))
    if isinstance(raw, dict):
        preview = migration_preview(raw)
        if preview["required"] and not bool(payload.get("approve_migration", False)):
            return {"status": "APPROVAL_REQUIRED", "action": "ir_migration", "migration": preview}
        model = _load_model(payload)
        points = int(payload.get("points", 1000))
        samples = int(payload.get("samples", 1))
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
    inferred = infer_domain(idea)
    domain = str(payload.get("domain", inferred["domain"]))
    signals = payload.get("signals", [])
    if isinstance(signals, dict):
        signals = [key for key, value in signals.items() if value]
    if not isinstance(signals, list):
        raise ValueError("signals must be an array or object")
    candidates = recommend_model_families(domain=domain, signals=signals, idea=idea)
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
    try:
        model = _load_model(payload)
    except MigrationApprovalRequired as exc:
        return {"status": "APPROVAL_REQUIRED", "action": "ir_migration", "migration": exc.preview}
    return {
        "model_ir": model.to_dict(),
        "validation": validate_model(model),
        "nondimensionalization": nondimensionalization_plan(model),
        "provenance": provenance_snapshot(model, seed=payload.get("seed"), data_hash=payload.get("data_hash")),
    }


def model_simulate_service(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        model = _load_model(payload)
    except MigrationApprovalRequired as exc:
        return {"status": "APPROVAL_REQUIRED", "action": "ir_migration", "migration": exc.preview}
    span = payload.get("t_span", [0.0, 1.0])
    if not isinstance(span, (list, tuple)) or len(span) != 2:
        raise ValueError("t_span must contain [start, stop]")
    result = simulate_model(
        model,
        t_span=(float(span[0]), float(span[1])),
        points=int(payload.get("points", 200)),
        parameter_overrides=payload.get("parameter_overrides"),
        seed=int(payload.get("seed", 0)),
        approve_heavy=bool(payload.get("approve_heavy", False)),
    )
    result["provenance"] = provenance_snapshot(model, seed=int(payload.get("seed", 0)), data_hash=payload.get("data_hash"))
    return result


def model_fit_service(payload: dict[str, Any]) -> dict[str, Any]:
    model = _load_model(payload)
    time = payload.get("time", payload.get("t"))
    observations = payload.get("observations")
    if not isinstance(time, list) or not isinstance(observations, dict):
        raise ValueError("fit requires time array and observations object")
    out = fit_ode_model(
        model,
        time=time,
        observations=observations,
        approve_heavy=bool(payload.get("approve_heavy", False)),
    )
    if out.get("covariance") is not None:
        residual_stds = [
            float(v.get("std", 0.0))
            for v in out.get("residual_diagnostics", {}).values()
            if isinstance(v, dict)
        ]
        out["uncertainty_components"] = split_uncertainty(
            residual_std=max(residual_stds) if residual_stds else None,
            parameter_covariance=out.get("covariance"),
        )
    out["provenance"] = provenance_snapshot(model, data_hash=payload.get("data_hash"))
    return out


def model_compare_service(payload: dict[str, Any]) -> dict[str, Any]:
    fits = payload.get("fits")
    if not isinstance(fits, dict):
        raise ValueError("compare requires fits object")
    return rank_model_fits(fits, criterion=str(payload.get("criterion", "bic")))


def model_repair_service(payload: dict[str, Any]) -> dict[str, Any]:
    model = _load_model(payload)
    supplied_validation = payload.get("validation")
    return repair_model(
        model,
        approve=bool(payload.get("approve_repair", False)),
        validation=supplied_validation if isinstance(supplied_validation, dict) else None,
    )


def model_export_service(payload: dict[str, Any]) -> dict[str, Any]:
    model = _load_model(payload)
    return export_model(model, format=str(payload.get("format", "json")))


def model_stability_service(payload: dict[str, Any]) -> dict[str, Any]:
    model = _load_model(payload)
    state = payload.get("state")
    if not isinstance(state, dict):
        raise ValueError("stability requires state object")
    return local_stability(model, state={k: float(v) for k, v in state.items()},
                           parameter_overrides=payload.get("parameter_overrides"))


def model_validity_service(payload: dict[str, Any]) -> dict[str, Any]:
    model = _load_model(payload)
    span = payload.get("t_span", [0.0, 1.0])
    values = payload.get("values")
    if not isinstance(values, list):
        raise ValueError("validity scan requires values array")
    return validity_scan(
        model,
        parameter=str(payload["parameter"]),
        values=[float(v) for v in values],
        t_span=(float(span[0]), float(span[1])),
        points=int(payload.get("points", 200)),
        approve_heavy=bool(payload.get("approve_heavy", False)),
    )


def model_discovery_service(payload: dict[str, Any]) -> dict[str, Any]:
    return discover_sparse_dynamics(
        time=payload["time"],
        state=payload["state"],
        degree=int(payload.get("degree", 2)),
        threshold=float(payload.get("threshold", 1e-4)),
        approve_heavy=bool(payload.get("approve_heavy", False)),
    )


def experiment_design_service(payload: dict[str, Any]) -> dict[str, Any]:
    model = _load_model(payload)
    times = payload.get("candidate_times")
    if not isinstance(times, list):
        raise ValueError("experiment design requires candidate_times array")
    return rank_experiment_times(
        model,
        parameter=str(payload["parameter"]),
        candidate_times=[float(v) for v in times],
        horizon=float(payload["horizon"]),
        delta_fraction=float(payload.get("delta_fraction", 0.01)),
        approve_heavy=bool(payload.get("approve_heavy", False)),
    )
