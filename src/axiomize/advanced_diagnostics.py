"""Advanced deterministic diagnostics for the general Model IR engine.

These routines implement approval-gated uncertainty propagation, an ODE
bifurcation/stability scan, and explicit stopping criteria. They deliberately
return structured evidence instead of silently deciding that a model is good.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from axiomize.general_engine import (
    _parameter_values,
    _sympy_expression,
    estimate_compute,
    local_stability,
    simulate_model,
)
from axiomize.model_ir import ModelFamily, ModelIR


def _finite_scalar(value: Any, name: str, *, non_negative: bool = False) -> float:
    """Reject non-finite inputs before they can satisfy a scientific gate."""
    if isinstance(value, (bool, str, bytes)):
        raise ValueError(f"{name} must be a finite numeric value")
    try:
        numeric = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite numeric value") from exc
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be a finite numeric value")
    if non_negative and numeric < 0:
        raise ValueError(f"{name} must be non-negative")
    return numeric


def stopping_decision(
    history: list[float],
    *,
    relative_tolerance: float = 1e-3,
    absolute_tolerance: float = 1e-8,
    patience: int = 3,
    budget_used: float | None = None,
    budget_limit: float | None = None,
    uncertainty: float | None = None,
    uncertainty_target: float | None = None,
) -> dict[str, Any]:
    """Apply visible, deterministic convergence/budget stopping criteria.

    ``history`` is a sequence of objective/error/score values where smaller
    successive changes indicate convergence. No criterion is invented when the
    caller has not supplied enough information.
    """
    if isinstance(patience, bool) or not isinstance(patience, int) or patience < 1:
        raise ValueError("patience must be an integer at least 1")
    relative_tolerance = _finite_scalar(relative_tolerance, "relative_tolerance", non_negative=True)
    absolute_tolerance = _finite_scalar(absolute_tolerance, "absolute_tolerance", non_negative=True)
    values = np.asarray(history, dtype=float)
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError("history must be a finite 1D sequence")

    checks: list[dict[str, Any]] = []
    converged = False
    if values.size >= patience + 1:
        previous = values[-patience - 1 : -1]
        current = values[-patience:]
        with np.errstate(over="ignore", invalid="ignore"):
            delta = np.abs(current - previous)
            scale = np.maximum(np.abs(previous), np.abs(current))
            threshold = absolute_tolerance + relative_tolerance * scale
        if not np.all(np.isfinite(delta)) or not np.all(np.isfinite(threshold)):
            raise ValueError("stopping comparison overflowed")
        converged = bool(np.all(delta <= threshold))
        checks.append(
            {
                "criterion": "incremental_improvement",
                "status": "STOP" if converged else "CONTINUE",
                "patience": int(patience),
                "max_recent_change": float(np.max(delta)),
                "max_recent_threshold": float(np.max(threshold)),
            }
        )
    else:
        checks.append(
            {
                "criterion": "incremental_improvement",
                "status": "INSUFFICIENT_DATA",
                "required_history": int(patience + 1),
                "available_history": int(values.size),
            }
        )

    budget_exhausted = False
    if budget_limit is not None:
        if budget_used is None:
            raise ValueError("budget_used is required when budget_limit is supplied")
        budget_used = _finite_scalar(budget_used, "budget_used", non_negative=True)
        budget_limit = _finite_scalar(budget_limit, "budget_limit", non_negative=True)
        if budget_limit <= 0:
            raise ValueError("budget_limit must be positive")
        budget_exhausted = budget_used >= budget_limit
        checks.append(
            {
                "criterion": "compute_budget",
                "status": "STOP" if budget_exhausted else "CONTINUE",
                "used": float(budget_used),
                "limit": float(budget_limit),
                "fraction": float(budget_used) / float(budget_limit),
            }
        )

    uncertainty_sufficient = False
    if uncertainty_target is not None:
        if uncertainty is None:
            raise ValueError("uncertainty is required when uncertainty_target is supplied")
        uncertainty = _finite_scalar(uncertainty, "uncertainty", non_negative=True)
        uncertainty_target = _finite_scalar(uncertainty_target, "uncertainty_target", non_negative=True)
        uncertainty_sufficient = uncertainty <= uncertainty_target
        checks.append(
            {
                "criterion": "uncertainty_target",
                "status": "STOP" if uncertainty_sufficient else "CONTINUE",
                "uncertainty": float(uncertainty),
                "target": float(uncertainty_target),
            }
        )

    stop = converged or budget_exhausted or uncertainty_sufficient
    reasons = [c["criterion"] for c in checks if c["status"] == "STOP"]
    return {
        "decision": "STOP" if stop else "CONTINUE",
        "reasons": reasons,
        "checks": checks,
        "rule": "stop when any explicitly configured criterion is satisfied",
    }


def _sample_parameter(
    rng: np.random.Generator,
    spec: dict[str, Any],
    baseline: float,
    bounds: tuple[float | None, float | None] | None,
    samples: int,
) -> np.ndarray:
    kind = str(spec.get("distribution", spec.get("kind", "normal"))).lower()
    if kind == "normal":
        mean = _finite_scalar(spec.get("mean", baseline), "normal mean")
        if "std" not in spec:
            raise ValueError("normal parameter uncertainty requires std")
        std = _finite_scalar(spec["std"], "normal std", non_negative=True)
        values = rng.normal(mean, std, size=samples)
    elif kind == "uniform":
        low = spec.get("low")
        high = spec.get("high")
        if low is None or high is None:
            raise ValueError("uniform parameter uncertainty requires low and high")
        low_f = _finite_scalar(low, "uniform low")
        high_f = _finite_scalar(high, "uniform high")
        if high_f <= low_f:
            raise ValueError("uniform high must exceed low")
        values = rng.uniform(low_f, high_f, size=samples)
    elif kind == "fixed":
        values = np.full(samples, _finite_scalar(spec.get("value", baseline), "fixed value"))
    else:
        raise ValueError(f"unsupported uncertainty distribution: {kind}")

    if bounds is not None:
        low, high = bounds
        if low is not None:
            values = np.maximum(values, _finite_scalar(low, "parameter lower bound"))
        if high is not None:
            values = np.minimum(values, _finite_scalar(high, "parameter upper bound"))
    return np.asarray(values, dtype=float)


def propagate_parameter_uncertainty(
    model: ModelIR,
    *,
    t_span: tuple[float, float],
    parameter_uncertainty: dict[str, dict[str, Any]],
    points: int = 200,
    samples: int = 200,
    seed: int = 0,
    quantiles: tuple[float, ...] = (0.025, 0.5, 0.975),
    approve_heavy: bool = False,
) -> dict[str, Any]:
    """Monte-Carlo propagation of parameter uncertainty through Model IR.

    It is approval-gated because it multiplies model executions. Failed samples
    are counted and never silently discarded from the reported success rate.
    """
    if model.family not in {ModelFamily.ODE, ModelFamily.STOCHASTIC, ModelFamily.ALGEBRAIC}:
        return {
            "status": "TOOL_ROUTE_REQUIRED",
            "family": model.family.value,
            "detail": "generic uncertainty propagation requires a native executor for this family",
        }
    if samples < 2:
        raise ValueError("samples must be at least 2")
    if samples > 100_000:
        raise ValueError("samples exceeds hard safety limit of 100000")
    q = np.asarray(quantiles, dtype=float)
    if q.ndim != 1 or q.size == 0 or not np.all(np.isfinite(q)) or np.any((q < 0) | (q > 1)):
        raise ValueError("quantiles must be probabilities in [0, 1]")

    cost = estimate_compute(model, action="uncertainty", points=points, samples=samples)
    if not approve_heavy:
        return {
            "status": "APPROVAL_REQUIRED",
            "cost": cost,
            "detail": "Monte Carlo uncertainty propagation multiplies model executions; approve explicitly to run it",
        }

    baseline = _parameter_values(model)
    by_name = {p.name: p for p in model.parameters}
    unknown = sorted(set(parameter_uncertainty) - set(by_name))
    if unknown:
        raise ValueError(f"uncertainty supplied for unknown parameters: {unknown}")
    rng = np.random.default_rng(seed)
    draws: dict[str, np.ndarray] = {}
    for name, parameter in by_name.items():
        spec = parameter_uncertainty.get(name, {"distribution": "fixed", "value": baseline[name]})
        draws[name] = _sample_parameter(rng, spec, baseline[name], parameter.bounds, samples)

    successful: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for index in range(samples):
        overrides = {name: float(values[index]) for name, values in draws.items()}
        result = simulate_model(
            model,
            t_span=t_span,
            points=points,
            parameter_overrides=overrides,
            seed=int(seed + index),
            approve_heavy=True,
        )
        if result.get("status") == "PASS" and isinstance(result.get("states"), dict):
            successful.append(result)
        else:
            failures.append({"sample": index, "status": result.get("status"), "stage": result.get("stage")})

    if not successful:
        return {
            "status": "FAIL",
            "successful_samples": 0,
            "failed_samples": len(failures),
            "failures": failures[:50],
            "cost": cost,
        }

    state_names = sorted(successful[0]["states"])
    output: dict[str, Any] = {}
    for state in state_names:
        arrays = [np.asarray(result["states"][state], dtype=float) for result in successful]
        matrix = np.vstack(arrays)
        output[state] = {
            "mean": np.mean(matrix, axis=0).tolist(),
            "std": np.std(matrix, axis=0, ddof=1).tolist() if len(arrays) > 1 else np.zeros(matrix.shape[1]).tolist(),
            "quantiles": {f"q{prob:g}": np.quantile(matrix, prob, axis=0).tolist() for prob in q},
        }

    first_time = successful[0].get("time")
    return {
        "status": "PASS",
        "method": "monte_carlo_parameter_propagation",
        "seed": int(seed),
        "requested_samples": int(samples),
        "successful_samples": len(successful),
        "failed_samples": len(failures),
        "success_fraction": len(successful) / float(samples),
        "failures": failures[:50],
        "time": first_time,
        "states": output,
        "parameter_draw_summary": {
            name: {"mean": float(np.mean(values)), "std": float(np.std(values, ddof=1))}
            for name, values in draws.items()
        },
        "cost": cost,
    }


def _equilibrium_for_ode(
    model: ModelIR,
    *,
    parameter_values: dict[str, float],
    guess: dict[str, float] | None = None,
) -> dict[str, float]:
    import sympy as sp

    states = [v for v in model.variables if v.role == "state"]
    names = [v.name for v in states]
    pnames = [p.name for p in model.parameters]
    symbols = {name: sp.Symbol(name, real=True) for name in names + pnames + [model.independent_variable]}
    equations_by_target = {e.target: e for e in model.equations if e.kind == "derivative"}
    equations = [
        _sympy_expression(equations_by_target[name].expression, symbols).subs(
            {symbols[p]: float(parameter_values[p]) for p in pnames}
        )
        for name in names
    ]
    initial = []
    guess = dict(guess or {})
    for state in states:
        if state.name in guess:
            initial.append(float(guess[state.name]))
        elif state.initial is not None:
            initial.append(float(state.initial))
        else:
            initial.append(1.0)
    root = sp.nsolve(equations, [symbols[name] for name in names], initial)
    values = np.asarray(root, dtype=float).reshape(-1)
    return {name: float(values[i]) for i, name in enumerate(names)}


def bifurcation_scan(
    model: ModelIR,
    *,
    parameter: str,
    values: list[float],
    equilibrium_guess: dict[str, float] | None = None,
    approve_heavy: bool = False,
) -> dict[str, Any]:
    """Scan ODE equilibria and flag observed local-stability transitions."""
    if model.family != ModelFamily.ODE:
        return {
            "status": "TOOL_ROUTE_REQUIRED",
            "family": model.family.value,
            "detail": "native bifurcation scan currently requires an ODE Model IR",
        }
    if len(values) < 2:
        raise ValueError("bifurcation scan requires at least two parameter values")
    cost = estimate_compute(model, action="parameter_scan", points=1, samples=len(values))
    if not approve_heavy:
        return {
            "status": "APPROVAL_REQUIRED",
            "cost": cost,
            "detail": "equilibrium/stability parameter scanning requires explicit approval",
        }
    baseline = _parameter_values(model)
    if parameter not in baseline:
        raise ValueError(f"unknown parameter: {parameter}")

    rows: list[dict[str, Any]] = []
    previous_guess = dict(equilibrium_guess or {})
    for value in values:
        params = dict(baseline)
        params[parameter] = float(value)
        try:
            equilibrium = _equilibrium_for_ode(model, parameter_values=params, guess=previous_guess)
            stability = local_stability(model, state=equilibrium, parameter_overrides={parameter: float(value)})
            rows.append(
                {
                    "parameter_value": float(value),
                    "status": "PASS",
                    "equilibrium": equilibrium,
                    "stability": stability,
                }
            )
            previous_guess = equilibrium
        except Exception as exc:
            rows.append(
                {
                    "parameter_value": float(value),
                    "status": "FAIL",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    transitions: list[dict[str, Any]] = []
    successful = [row for row in rows if row["status"] == "PASS"]
    for left, right in zip(successful, successful[1:], strict=False):
        lvalue = float(left["stability"]["max_real_part"])
        rvalue = float(right["stability"]["max_real_part"])
        if lvalue == 0.0 or rvalue == 0.0 or (lvalue < 0 < rvalue) or (rvalue < 0 < lvalue):
            transitions.append(
                {
                    "between": [left["parameter_value"], right["parameter_value"]],
                    "max_real_part": [lvalue, rvalue],
                    "classification": "local_stability_transition_candidate",
                }
            )

    return {
        "status": "PASS" if successful else "FAIL",
        "parameter": parameter,
        "rows": rows,
        "transition_candidates": transitions,
        "interpretation": "sign changes in the dominant Jacobian eigenvalue flag local bifurcation candidates; they are not proof of a specific bifurcation type",
        "cost": cost,
    }
