"""Validated reduced-order / surrogate modeling for expensive scientific runs.

Surrogates are never silently substituted for the source scientific model.  A
surrogate must expose its training domain, holdout error and acceptance status.
Generating training observations from a full Model IR is explicitly
approval-gated because it multiplies full-model evaluations.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from typing import Any

import numpy as np

from axiomize.general_engine import estimate_compute, provenance_snapshot, simulate_model
from axiomize.model_ir import ModelIR

SURROGATE_SCHEMA_VERSION = "1.0"


def _finite_vector(values: Any, *, name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1 or arr.size == 0 or not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must be a non-empty finite 1D numeric array")
    return arr


def _validate_training_data(
    inputs: dict[str, Any], outputs: dict[str, Any]
) -> tuple[list[str], list[str], np.ndarray, np.ndarray]:
    if not isinstance(inputs, dict) or not inputs:
        raise ValueError("training inputs must be a non-empty object")
    if not isinstance(outputs, dict) or not outputs:
        raise ValueError("training outputs must be a non-empty object")
    input_names = sorted(str(name) for name in inputs)
    output_names = sorted(str(name) for name in outputs)
    if len(set(input_names)) != len(input_names) or len(set(output_names)) != len(output_names):
        raise ValueError("training input/output names must be unique")

    x_cols = [_finite_vector(inputs[name], name=f"inputs[{name}]") for name in input_names]
    y_cols = [_finite_vector(outputs[name], name=f"outputs[{name}]") for name in output_names]
    lengths = {arr.size for arr in x_cols + y_cols}
    if len(lengths) != 1:
        raise ValueError("all training input/output arrays must have the same length")
    n = lengths.pop()
    if n < 8:
        raise ValueError("surrogate fitting requires at least 8 observations")
    if len(input_names) > 12:
        raise ValueError("native polynomial surrogate supports at most 12 inputs")
    return input_names, output_names, np.column_stack(x_cols), np.column_stack(y_cols)


def _feature_powers(n_inputs: int, degree: int) -> list[tuple[int, ...]]:
    if degree < 1 or degree > 3:
        raise ValueError("degree must be between 1 and 3")
    powers: list[tuple[int, ...]] = [tuple(0 for _ in range(n_inputs))]
    for total_degree in range(1, degree + 1):
        for combination in itertools.combinations_with_replacement(range(n_inputs), total_degree):
            power = [0] * n_inputs
            for index in combination:
                power[index] += 1
            powers.append(tuple(power))
    return powers


def _design_matrix(x_scaled: np.ndarray, powers: list[tuple[int, ...]]) -> np.ndarray:
    columns: list[np.ndarray] = []
    for power in powers:
        column = np.ones(x_scaled.shape[0], dtype=float)
        for index, exponent in enumerate(power):
            if exponent:
                column *= x_scaled[:, index] ** exponent
        columns.append(column)
    return np.column_stack(columns)


def _metrics(observed: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    observed = np.asarray(observed, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    residual = observed - predicted
    rmse = float(np.sqrt(np.mean(residual ** 2)))
    mae = float(np.mean(np.abs(residual)))
    max_abs = float(np.max(np.abs(residual)))
    span = float(np.max(observed) - np.min(observed))
    scale = span if span > 1e-15 else max(float(np.std(observed)), abs(float(np.mean(observed))), 1.0)
    nrmse = rmse / scale
    centered = observed - np.mean(observed)
    tss = float(np.sum(centered ** 2))
    sse = float(np.sum(residual ** 2))
    r2 = 1.0 - sse / tss if tss > 1e-30 else (1.0 if sse <= 1e-24 else 0.0)
    return {"rmse": rmse, "nrmse": float(nrmse), "mae": mae, "max_abs": max_abs, "r2": float(r2)}


def fit_polynomial_surrogate(
    *,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    degree: int = 2,
    ridge: float = 1e-10,
    holdout_fraction: float = 0.2,
    seed: int = 0,
    minimum_r2: float = 0.95,
    maximum_nrmse: float = 0.10,
) -> dict[str, Any]:
    """Fit a polynomial response surface with an explicit untouched holdout set."""
    input_names, output_names, x, y = _validate_training_data(inputs, outputs)
    if ridge < 0:
        raise ValueError("ridge must be non-negative")
    if not 0.1 <= holdout_fraction <= 0.5:
        raise ValueError("holdout_fraction must be in [0.1, 0.5]")
    if not -1.0 <= minimum_r2 <= 1.0:
        raise ValueError("minimum_r2 must be in [-1, 1]")
    if maximum_nrmse < 0:
        raise ValueError("maximum_nrmse must be non-negative")

    n = x.shape[0]
    holdout_n = max(2, int(round(n * holdout_fraction)))
    if n - holdout_n < 5:
        holdout_n = n - 5
    if holdout_n < 2:
        raise ValueError("not enough observations for a separate holdout set")

    rng = np.random.default_rng(seed)
    order = rng.permutation(n)
    holdout_idx = np.sort(order[:holdout_n])
    train_idx = np.sort(order[holdout_n:])
    x_train, x_holdout = x[train_idx], x[holdout_idx]
    y_train, y_holdout = y[train_idx], y[holdout_idx]

    mean = np.mean(x_train, axis=0)
    scale = np.std(x_train, axis=0, ddof=1)
    if np.any(scale <= 1e-14):
        bad = [input_names[i] for i, value in enumerate(scale) if value <= 1e-14]
        raise ValueError(f"surrogate inputs need variation; near-constant inputs: {bad}")
    x_train_scaled = (x_train - mean) / scale
    x_holdout_scaled = (x_holdout - mean) / scale

    powers = _feature_powers(len(input_names), degree)
    if len(powers) >= len(train_idx):
        raise ValueError(
            f"surrogate is underdetermined: {len(powers)} polynomial terms but only {len(train_idx)} training observations"
        )
    phi_train = _design_matrix(x_train_scaled, powers)
    phi_holdout = _design_matrix(x_holdout_scaled, powers)

    gram = phi_train.T @ phi_train
    regularizer = np.eye(gram.shape[0], dtype=float) * ridge
    regularizer[0, 0] = 0.0
    rhs = phi_train.T @ y_train
    try:
        coefficients = np.linalg.solve(gram + regularizer, rhs)
    except np.linalg.LinAlgError:
        coefficients = np.linalg.lstsq(gram + regularizer, rhs, rcond=None)[0]

    train_prediction = phi_train @ coefficients
    holdout_prediction = phi_holdout @ coefficients
    training_metrics = {
        output_names[i]: _metrics(y_train[:, i], train_prediction[:, i])
        for i in range(len(output_names))
    }
    holdout_metrics = {
        output_names[i]: _metrics(y_holdout[:, i], holdout_prediction[:, i])
        for i in range(len(output_names))
    }
    checks = []
    for output in output_names:
        metric = holdout_metrics[output]
        passed = metric["r2"] >= minimum_r2 and metric["nrmse"] <= maximum_nrmse
        checks.append({
            "output": output,
            "status": "PASS" if passed else "FAIL",
            "r2": metric["r2"],
            "minimum_r2": float(minimum_r2),
            "nrmse": metric["nrmse"],
            "maximum_nrmse": float(maximum_nrmse),
        })
    validated = all(check["status"] == "PASS" for check in checks)

    dataset_payload = {
        "inputs": {name: np.asarray(inputs[name], dtype=float).tolist() for name in input_names},
        "outputs": {name: np.asarray(outputs[name], dtype=float).tolist() for name in output_names},
    }
    dataset_hash = hashlib.sha256(
        json.dumps(dataset_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    artifact = {
        "schema_version": SURROGATE_SCHEMA_VERSION,
        "kind": "polynomial_response_surface",
        "degree": int(degree),
        "input_names": input_names,
        "output_names": output_names,
        "normalization": {"mean": mean.tolist(), "scale": scale.tolist()},
        "feature_powers": [list(power) for power in powers],
        "coefficients": coefficients.tolist(),
        "training_domain": {
            input_names[i]: [float(np.min(x[:, i])), float(np.max(x[:, i]))]
            for i in range(len(input_names))
        },
        "training_rows": int(len(train_idx)),
        "holdout_rows": int(len(holdout_idx)),
        "dataset_sha256": dataset_hash,
        "validation": {
            "validated": bool(validated),
            "method": "seeded_untouched_holdout",
            "seed": int(seed),
            "holdout_fraction": float(holdout_n / n),
            "thresholds": {"minimum_r2": float(minimum_r2), "maximum_nrmse": float(maximum_nrmse)},
            "checks": checks,
            "train_metrics": training_metrics,
            "holdout_metrics": holdout_metrics,
        },
        "use_policy": {
            "may_replace_full_model": False,
            "in_domain_prediction_requires_validation": True,
            "out_of_domain_prediction_blocked_by_default": True,
        },
    }
    return {
        "status": "PASS",
        "surrogate": artifact,
        "validation_status": "PASS" if validated else "FAIL",
        "qualified_for_acceleration": bool(validated),
        "detail": (
            "surrogate passed untouched holdout thresholds; it remains an approximation and does not replace source-model validation"
            if validated
            else "surrogate fit completed but failed holdout acceptance thresholds; do not use it as a full-model substitute"
        ),
    }


def evaluate_surrogate(
    surrogate: dict[str, Any],
    *,
    inputs: dict[str, float],
    allow_extrapolation: bool = False,
    allow_unvalidated: bool = False,
) -> dict[str, Any]:
    """Evaluate a saved surrogate only inside its validated domain by default."""
    if not isinstance(surrogate, dict) or surrogate.get("schema_version") != SURROGATE_SCHEMA_VERSION:
        raise ValueError("unsupported or missing surrogate schema_version")
    if surrogate.get("kind") != "polynomial_response_surface":
        raise ValueError("unsupported surrogate kind")
    validation = surrogate.get("validation", {})
    if not bool(validation.get("validated", False)) and not allow_unvalidated:
        return {
            "status": "SURROGATE_REJECTED",
            "detail": "surrogate did not pass its holdout acceptance thresholds",
            "validation": validation,
        }

    input_names = list(surrogate["input_names"])
    missing = [name for name in input_names if name not in inputs]
    extra = sorted(set(inputs) - set(input_names))
    if missing or extra:
        raise ValueError(f"surrogate input mismatch; missing={missing}, extra={extra}")
    x = np.asarray([[float(inputs[name]) for name in input_names]], dtype=float)
    if not np.all(np.isfinite(x)):
        raise ValueError("surrogate inputs must be finite")

    violations = []
    for i, name in enumerate(input_names):
        low, high = surrogate["training_domain"][name]
        value = float(x[0, i])
        if value < float(low) or value > float(high):
            violations.append({"input": name, "value": value, "training_range": [float(low), float(high)]})
    if violations and not allow_extrapolation:
        return {
            "status": "OUT_OF_DOMAIN",
            "detail": "prediction blocked outside the surrogate training domain",
            "violations": violations,
        }

    mean = np.asarray(surrogate["normalization"]["mean"], dtype=float)
    scale = np.asarray(surrogate["normalization"]["scale"], dtype=float)
    powers = [tuple(int(v) for v in power) for power in surrogate["feature_powers"]]
    coefficients = np.asarray(surrogate["coefficients"], dtype=float)
    phi = _design_matrix((x - mean) / scale, powers)
    predicted = (phi @ coefficients)[0]
    predictions = {
        name: float(predicted[i]) for i, name in enumerate(surrogate["output_names"])
    }
    return {
        "status": "UNVERIFIED_EXTRAPOLATION" if violations else "PASS",
        "predictions": predictions,
        "in_training_domain": not bool(violations),
        "domain_violations": violations,
        "surrogate_validation": validation,
    }


def _latin_hypercube(
    ranges: dict[str, tuple[float, float]], *, samples: int, seed: int
) -> tuple[list[str], np.ndarray]:
    if samples < 8 or samples > 2000:
        raise ValueError("surrogate generation samples must be between 8 and 2000")
    names = sorted(ranges)
    rng = np.random.default_rng(seed)
    x = np.empty((samples, len(names)), dtype=float)
    strata = (np.arange(samples, dtype=float) + rng.random(samples)) / samples
    for j, name in enumerate(names):
        low, high = ranges[name]
        if not math.isfinite(low) or not math.isfinite(high) or high <= low:
            raise ValueError(f"invalid finite parameter range for {name}: [{low}, {high}]")
        coordinates = strata[rng.permutation(samples)]
        x[:, j] = low + coordinates * (high - low)
    return names, x


def _validate_parameter_ranges(model: ModelIR, raw: dict[str, Any]) -> dict[str, tuple[float, float]]:
    if not isinstance(raw, dict) or not raw:
        raise ValueError("parameter_ranges must be a non-empty object")
    by_name = {p.name: p for p in model.parameters}
    unknown = sorted(set(raw) - set(by_name))
    if unknown:
        raise ValueError(f"parameter_ranges references unknown parameters: {unknown}")
    ranges: dict[str, tuple[float, float]] = {}
    for name, bounds in raw.items():
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
            raise ValueError(f"parameter_ranges[{name}] must be [low, high]")
        low, high = float(bounds[0]), float(bounds[1])
        declared = by_name[name].bounds
        if declared is not None:
            declared_low, declared_high = declared
            if declared_low is not None and low < float(declared_low):
                raise ValueError(f"parameter range for {name} falls below Model IR bound")
            if declared_high is not None and high > float(declared_high):
                raise ValueError(f"parameter range for {name} exceeds Model IR bound")
        ranges[name] = (low, high)
    return ranges


def _output_specs(model: ModelIR, raw: Any) -> list[dict[str, str]]:
    state_names = [v.name for v in model.variables if v.role == "state"]
    if raw is None:
        if not state_names:
            raise ValueError("source model has no state outputs; output_specs are required")
        return [{"name": f"{state}__final", "state": state, "metric": "final"} for state in state_names]
    if not isinstance(raw, list) or not raw:
        raise ValueError("output_specs must be a non-empty array")
    result = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each output spec must be an object")
        state = str(item.get("state", ""))
        metric = str(item.get("metric", "final")).lower()
        name = str(item.get("name", f"{state}__{metric}"))
        if state not in state_names:
            raise ValueError(f"output spec references unknown state: {state}")
        if metric not in {"final", "mean", "min", "max", "integral"}:
            raise ValueError(f"unsupported output metric: {metric}")
        if name in seen:
            raise ValueError(f"duplicate surrogate output name: {name}")
        seen.add(name)
        result.append({"name": name, "state": state, "metric": metric})
    return result


def _extract_output(result: dict[str, Any], spec: dict[str, str]) -> float:
    states = result.get("states")
    if not isinstance(states, dict) or spec["state"] not in states:
        raise ValueError(f"simulation result lacks state {spec['state']!r}")
    values = _finite_vector(states[spec["state"]], name=f"states[{spec['state']}]")
    metric = spec["metric"]
    if metric == "final":
        return float(values[-1])
    if metric == "mean":
        return float(np.mean(values))
    if metric == "min":
        return float(np.min(values))
    if metric == "max":
        return float(np.max(values))
    time = _finite_vector(result.get("time"), name="time")
    if time.shape != values.shape:
        raise ValueError("integral output requires time/state arrays of equal length")
    return float(np.trapezoid(values, time))


def generate_and_fit_surrogate(
    model: ModelIR,
    *,
    parameter_ranges: dict[str, Any],
    output_specs: Any = None,
    t_span: tuple[float, float] = (0.0, 1.0),
    points: int = 100,
    samples: int = 32,
    degree: int = 2,
    holdout_fraction: float = 0.2,
    seed: int = 0,
    minimum_r2: float = 0.95,
    maximum_nrmse: float = 0.10,
    approve_heavy: bool = False,
) -> dict[str, Any]:
    """Generate full-model training data then fit/validate a surrogate.

    This path always requires explicit approval because it launches multiple
    full-model simulations, even when the coarse estimate is otherwise small.
    """
    ranges = _validate_parameter_ranges(model, parameter_ranges)
    specs = _output_specs(model, output_specs)
    cost = estimate_compute(model, action="surrogate_training", points=points, samples=samples)
    cost = dict(cost)
    cost["requires_user_approval"] = True
    cost["full_model_runs"] = int(samples)
    cost["reason"] = "surrogate training requires multiple full scientific-model evaluations"
    if not approve_heavy:
        return {
            "status": "APPROVAL_REQUIRED",
            "action": "surrogate_training_data_generation",
            "cost": cost,
            "parameter_ranges": {name: list(bounds) for name, bounds in ranges.items()},
            "output_specs": specs,
        }

    names, design = _latin_hypercube(ranges, samples=samples, seed=seed)
    generated_inputs: dict[str, list[float]] = {name: [] for name in names}
    generated_outputs: dict[str, list[float]] = {spec["name"]: [] for spec in specs}
    failures: list[dict[str, Any]] = []

    for row_index, row in enumerate(design):
        overrides = {name: float(row[j]) for j, name in enumerate(names)}
        result = simulate_model(
            model,
            t_span=t_span,
            points=points,
            parameter_overrides=overrides,
            seed=seed + row_index,
            approve_heavy=True,
        )
        if result.get("status") != "PASS":
            failures.append({
                "sample": row_index,
                "parameters": overrides,
                "status": result.get("status"),
                "stage": result.get("stage"),
            })
            continue
        try:
            extracted = {spec["name"]: _extract_output(result, spec) for spec in specs}
        except ValueError as exc:
            failures.append({
                "sample": row_index,
                "parameters": overrides,
                "status": "OUTPUT_EXTRACTION_FAIL",
                "detail": str(exc),
            })
            continue
        for name in names:
            generated_inputs[name].append(overrides[name])
        for output_name, value in extracted.items():
            generated_outputs[output_name].append(value)

    successful = len(next(iter(generated_inputs.values()))) if generated_inputs else 0
    minimum_success = max(8, len(names) + 5)
    if successful < minimum_success:
        return {
            "status": "FAIL",
            "stage": "training_data_generation",
            "successful_runs": successful,
            "failed_runs": len(failures),
            "minimum_successful_runs": minimum_success,
            "failures": failures[:50],
            "cost": cost,
        }

    fitted = fit_polynomial_surrogate(
        inputs=generated_inputs,
        outputs=generated_outputs,
        degree=degree,
        holdout_fraction=holdout_fraction,
        seed=seed,
        minimum_r2=minimum_r2,
        maximum_nrmse=maximum_nrmse,
    )
    fitted["source_model"] = {
        "name": model.name,
        "family": model.family.value,
        "schema_version": model.schema_version,
    }
    fitted["sampling"] = {
        "method": "latin_hypercube",
        "seed": int(seed),
        "requested_runs": int(samples),
        "successful_runs": int(successful),
        "failed_runs": int(len(failures)),
        "success_fraction": float(successful / samples),
        "failures": failures[:50],
        "parameter_ranges": {name: list(bounds) for name, bounds in ranges.items()},
        "output_specs": specs,
    }
    fitted["cost"] = cost
    fitted["provenance"] = provenance_snapshot(model, seed=seed, data_hash=fitted["surrogate"]["dataset_sha256"])
    fitted["surrogate"]["source_model"] = fitted["source_model"]
    fitted["surrogate"]["sampling"] = fitted["sampling"]
    fitted["surrogate"]["provenance"] = fitted["provenance"]
    return fitted
