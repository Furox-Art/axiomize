"""Family-complete numerical verification contracts.

Not every scientific family has a discretization error.  This extension keeps
that distinction explicit: ODE/DAE/PDE retain tolerance/mesh refinement, while
other families receive the numerically meaningful stability/convergence study
for their algorithm (sampling error, output-grid stability, multi-start
optimization, coupling convergence, estimator conditioning, or deterministic
repeatability). Repeated work remains approval-gated.
"""
from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np

from axiomize.model_ir import ModelFamily, ModelIR


def _approval(model: ModelIR, study: str, runs: int, points: int) -> dict[str, Any]:
    return {
        "status": "APPROVAL_REQUIRED", "study": study, "family": model.family.value,
        "cost": {"planned_refinement_runs": runs, "temporal_output_points": points,
                 "requires_user_approval": True, "reason": "verification repeats or extends numerical work"},
        "uncertainty_separation": {"numerical": "pending", "parameter": "separate", "data": "separate", "model_structural": "separate"},
    }


def _terminal_signature(result: dict[str, Any]) -> np.ndarray:
    states = result.get("states", {})
    values: list[float] = []
    if isinstance(states, dict):
        for name in sorted(states):
            arr = np.asarray(states[name], dtype=float)
            if arr.size:
                terminal = arr[-1] if arr.ndim else arr
                values.extend(np.asarray(terminal, dtype=float).reshape(-1).tolist())
    if not values and isinstance(result.get("objective"), dict) and result["objective"].get("value") is not None:
        values.append(float(result["objective"]["value"]))
    out = np.asarray(values, dtype=float)
    if out.size == 0 or not np.all(np.isfinite(out)):
        raise ValueError("verification requires finite numeric state/objective outputs")
    return out


def _relative(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape: raise ValueError(f"verification shape mismatch: {a.shape} != {b.shape}")
    return float(np.linalg.norm(a - b) / max(np.linalg.norm(b), np.finfo(float).eps))


def _grid_study(model: ModelIR, simulate_once: Callable[..., dict[str, Any]], *, t_span: tuple[float, float], points: int,
                parameter_overrides: dict[str, float] | None, seed: int, tolerance: float, approve_heavy: bool) -> dict[str, Any]:
    if not approve_heavy: return _approval(model, "output_grid_refinement", 2, points)
    coarse_points = max(4, points)
    fine_points = min(200_000, max(coarse_points + 1, 2 * coarse_points - 1))
    coarse = simulate_once(model, t_span=t_span, points=coarse_points, parameter_overrides=parameter_overrides, seed=seed, approve_heavy=True)
    fine = simulate_once(model, t_span=t_span, points=fine_points, parameter_overrides=parameter_overrides, seed=seed, approve_heavy=True)
    if coarse.get("status") != "PASS" or fine.get("status") != "PASS": return {"status": "FAIL", "study": "output_grid_refinement", "family": model.family.value, "runs": [coarse, fine]}
    cstates, fstates = coarse.get("states", {}), fine.get("states", {})
    if not isinstance(cstates, dict) or not isinstance(fstates, dict) or not cstates: raise ValueError("grid refinement requires state trajectories")
    ct, ft = np.asarray(coarse.get("time"), dtype=float), np.asarray(fine.get("time"), dtype=float)
    errors: dict[str, float] = {}; maximum = 0.0
    for name in sorted(cstates):
        c, f = np.asarray(cstates[name], dtype=float), np.asarray(fstates[name], dtype=float)
        if c.ndim == 1 and f.ndim == 1:
            interp = np.interp(ct, ft, f); err = _relative(c, interp)
        elif c.ndim == 2 and f.ndim == 2 and c.shape[1] == f.shape[1]:
            interp = np.vstack([np.interp(ct, ft, f[:, j]) for j in range(f.shape[1])]).T; err = _relative(c, interp)
        else:
            err = _relative(np.asarray(c[-1]).reshape(-1), np.asarray(f[-1]).reshape(-1))
        errors[name] = err; maximum = max(maximum, err)
    return {"status": "PASS" if maximum <= tolerance else "FAIL", "study": "output_grid_refinement", "family": model.family.value,
            "converged": maximum <= tolerance, "tolerance": tolerance, "coarse_points": coarse_points, "fine_points": fine_points,
            "state_relative_l2": errors, "estimated_numerical_error": maximum,
            "uncertainty_separation": {"numerical": maximum, "parameter": "separate", "data": "separate", "model_structural": "separate"}}


def _sampling_study(model: ModelIR, simulate_once: Callable[..., dict[str, Any]], *, t_span: tuple[float, float], points: int,
                    parameter_overrides: dict[str, float] | None, seed: int, tolerance: float, approve_heavy: bool) -> dict[str, Any]:
    runs = 8
    if not approve_heavy: return _approval(model, "sampling_convergence", runs, points)
    signatures: list[np.ndarray] = []
    for i in range(runs):
        result = simulate_once(model, t_span=t_span, points=points, parameter_overrides=parameter_overrides, seed=seed + i * 7919, approve_heavy=True)
        if result.get("status") not in {"PASS", "WARNING"}: return {"status": "FAIL", "study": "sampling_convergence", "family": model.family.value, "failed_run": i, "failed_result": result}
        signatures.append(_terminal_signature(result))
    matrix = np.vstack(signatures)
    mean = np.mean(matrix, axis=0); se = np.std(matrix, axis=0, ddof=1) / math.sqrt(runs)
    relative_se = float(np.max(np.abs(se) / np.maximum(np.abs(mean), 1e-12)))
    return {"status": "PASS" if relative_se <= tolerance else "FAIL", "study": "sampling_convergence", "family": model.family.value,
            "runs": runs, "converged": relative_se <= tolerance, "tolerance": tolerance, "max_relative_standard_error": relative_se,
            "estimated_numerical_error": relative_se,
            "uncertainty_separation": {"numerical_sampling": relative_se, "parameter": "separate", "data": "separate", "model_structural": "separate"}}


def _optimization_study(model: ModelIR, simulate_once: Callable[..., dict[str, Any]], *, t_span: tuple[float, float], points: int,
                        parameter_overrides: dict[str, float] | None, seed: int, tolerance: float, approve_heavy: bool) -> dict[str, Any]:
    decision = [v for v in model.variables if v.role == "decision"]
    if not approve_heavy: return _approval(model, "optimization_multistart", 3, points)
    signatures: list[np.ndarray] = []; objectives: list[float] = []
    for i, factor in enumerate((-0.5, 0.0, 0.5)):
        payload = model.to_dict()
        for variable in payload["variables"]:
            if variable.get("role") == "decision":
                base = float(variable.get("initial") or 0.0); bounds = variable.get("bounds")
                span = 2.0
                if isinstance(bounds, (list, tuple)) and len(bounds) == 2 and bounds[0] is not None and bounds[1] is not None: span = float(bounds[1]) - float(bounds[0])
                variable["initial"] = base + factor * 0.5 * span
                if isinstance(bounds, (list, tuple)) and len(bounds) == 2:
                    if bounds[0] is not None: variable["initial"] = max(variable["initial"], float(bounds[0]))
                    if bounds[1] is not None: variable["initial"] = min(variable["initial"], float(bounds[1]))
        candidate = ModelIR.from_dict(payload)
        result = simulate_once(candidate, t_span=t_span, points=points, parameter_overrides=parameter_overrides, seed=seed + i, approve_heavy=True)
        if result.get("status") != "PASS": return {"status": "FAIL", "study": "optimization_multistart", "family": model.family.value, "failed_result": result}
        signatures.append(_terminal_signature(result)); objectives.append(float(result.get("objective", {}).get("value", np.nan)))
    spread = max(_relative(s, signatures[0]) for s in signatures[1:]) if len(signatures) > 1 else 0.0
    obj = np.asarray(objectives, dtype=float); obj_scale = max(float(np.max(np.abs(obj))), 1.0)
    obj_spread = float((np.max(obj) - np.min(obj)) / obj_scale) if np.all(np.isfinite(obj)) else math.inf
    error = max(spread, obj_spread)
    return {"status": "PASS" if error <= tolerance else "FAIL", "study": "optimization_multistart", "family": model.family.value,
            "starts": len(signatures), "solution_relative_spread": spread, "objective_relative_spread": obj_spread,
            "estimated_numerical_error": error, "converged": error <= tolerance, "tolerance": tolerance}


def _bayesian_study(model: ModelIR, simulate_once: Callable[..., dict[str, Any]], *, t_span: tuple[float, float], points: int,
                    parameter_overrides: dict[str, float] | None, seed: int, tolerance: float, approve_heavy: bool) -> dict[str, Any]:
    if not approve_heavy: return _approval(model, "mcmc_convergence", 1, points)
    result = simulate_once(model, t_span=t_span, points=points, parameter_overrides=parameter_overrides, seed=seed, approve_heavy=True)
    if result.get("status") not in {"PASS", "WARNING"}: return {"status": "FAIL", "study": "mcmc_convergence", "family": model.family.value, "failed_result": result}
    params = result.get("diagnostics", {}).get("parameters", {})
    if not isinstance(params, dict) or not params: raise ValueError("Bayesian verification requires per-parameter Rhat/ESS diagnostics")
    max_rhat = max(float(v["r_hat"]) for v in params.values()); min_ess = min(float(v["ess_bulk"]) for v in params.values())
    draws_total = int(result.get("diagnostics", {}).get("chains", 1)) * int(result.get("diagnostics", {}).get("draws_per_chain", 0))
    passed = max_rhat <= 1.05 and min_ess >= max(100.0, 0.01 * draws_total)
    return {"status": "PASS" if passed else "FAIL", "study": "mcmc_convergence", "family": model.family.value,
            "converged": passed, "max_r_hat": max_rhat, "min_ess_bulk": min_ess,
            "posterior_predictive": result.get("posterior_predictive"),
            "estimated_numerical_error": max(0.0, max_rhat - 1.0), "error_metric": "MCMC convergence diagnostic, not discretization error"}


def _causal_study(model: ModelIR, simulate_once: Callable[..., dict[str, Any]], *, t_span: tuple[float, float], points: int,
                  parameter_overrides: dict[str, float] | None, seed: int, tolerance: float, approve_heavy: bool) -> dict[str, Any]:
    del tolerance
    if not approve_heavy: return _approval(model, "causal_estimator_numerical_stability", 1, points)
    result = simulate_once(model, t_span=t_span, points=points, parameter_overrides=parameter_overrides, seed=seed, approve_heavy=True)
    if result.get("status") != "PASS": return {"status": "FAIL", "study": "causal_estimator_numerical_stability", "family": model.family.value, "failed_result": result}
    diagnostics = result.get("diagnostics", {}); rank = int(diagnostics.get("design_rank", 0)); adjustment = diagnostics.get("adjustment_set", [])
    required_rank = 2 + len(adjustment) if isinstance(adjustment, list) else 2
    overlap = diagnostics.get("overlap", {}); bad_overlap = bool(isinstance(overlap, dict) and overlap.get("applicable") and float(overlap.get("fraction_outside_0.05_0.95", 0.0)) > 0.2)
    passed = rank >= required_rank and not bad_overlap
    return {"status": "PASS" if passed else "FAIL", "study": "causal_estimator_numerical_stability", "family": model.family.value,
            "converged": passed, "design_rank": rank, "required_rank": required_rank, "overlap": overlap,
            "estimated_numerical_error": None, "error_metric": "conditioning/overlap diagnostic; causal uncertainty is separate"}


def _repeatability(model: ModelIR, simulate_once: Callable[..., dict[str, Any]], *, t_span: tuple[float, float], points: int,
                   parameter_overrides: dict[str, float] | None, seed: int, tolerance: float, approve_heavy: bool) -> dict[str, Any]:
    if not approve_heavy: return _approval(model, "deterministic_repeatability", 2, points)
    first = simulate_once(model, t_span=t_span, points=points, parameter_overrides=parameter_overrides, seed=seed, approve_heavy=True)
    second = simulate_once(model, t_span=t_span, points=points, parameter_overrides=parameter_overrides, seed=seed, approve_heavy=True)
    if first.get("status") != "PASS" or second.get("status") != "PASS": return {"status": "FAIL", "study": "deterministic_repeatability", "family": model.family.value}
    error = _relative(_terminal_signature(first), _terminal_signature(second))
    return {"status": "PASS" if error <= tolerance else "FAIL", "study": "deterministic_repeatability", "family": model.family.value,
            "converged": error <= tolerance, "estimated_numerical_error": error, "tolerance": tolerance}


def install_family_complete_verification(module: Any) -> None:
    original = module.numerical_refinement_study
    if getattr(original, "__axiomize_family_complete__", False): return

    def family_complete(model: ModelIR, *, simulate_once: Callable[..., dict[str, Any]], t_span: tuple[float, float], points: int = 200,
                        parameter_overrides: dict[str, float] | None = None, seed: int = 0, tolerance: float = 1e-3,
                        approve_heavy: bool = False) -> dict[str, Any]:
        if model.family in {ModelFamily.ODE, ModelFamily.DAE, ModelFamily.PDE}:
            return original(model, simulate_once=simulate_once, t_span=t_span, points=points, parameter_overrides=parameter_overrides,
                            seed=seed, tolerance=tolerance, approve_heavy=approve_heavy)
        kwargs = dict(model=model, simulate_once=simulate_once, t_span=t_span, points=points, parameter_overrides=parameter_overrides,
                      seed=seed, tolerance=tolerance, approve_heavy=approve_heavy)
        if model.family in {ModelFamily.STOCHASTIC, ModelFamily.AGENT_BASED, ModelFamily.DISCRETE_EVENT}: return _sampling_study(**kwargs)
        if model.family == ModelFamily.BAYESIAN: return _bayesian_study(**kwargs)
        if model.family == ModelFamily.OPTIMIZATION: return _optimization_study(**kwargs)
        if model.family in {ModelFamily.CONTROL, ModelFamily.NETWORK, ModelFamily.HYBRID}: return _grid_study(**kwargs)
        if model.family == ModelFamily.CAUSAL: return _causal_study(**kwargs)
        # Algebraic and multiphysics receive deterministic repeatability here;
        # multiphysics already exposes its own coupling-convergence diagnostics.
        return _repeatability(**kwargs)

    family_complete.__axiomize_family_complete__ = True  # type: ignore[attr-defined]
    module.numerical_refinement_study = family_complete
