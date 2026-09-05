"""Numerical refinement studies for Model IR simulations.

This module keeps numerical/discretization error separate from model, parameter,
and data uncertainty. Refinement multiplies solver work, so it is always gated by
explicit approval. It consumes a single-run callback to avoid recursive
verification when it re-executes refined models.
"""

from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np

from axiomize.model_ir import ModelFamily, ModelIR

_SimulateOnce = Callable[..., dict[str, Any]]


def _relative_errors(reference: np.ndarray, candidate: np.ndarray) -> tuple[float, float, float]:
    reference = np.asarray(reference, dtype=float)
    candidate = np.asarray(candidate, dtype=float)
    if reference.shape != candidate.shape:
        raise ValueError(f"refinement comparison shape mismatch: {reference.shape} != {candidate.shape}")
    diff = candidate - reference
    abs_l2 = float(np.sqrt(np.mean(diff * diff)))
    scale = float(np.sqrt(np.mean(reference * reference)))
    rel_l2 = abs_l2 / max(scale, np.finfo(float).eps)
    rel_linf = float(np.max(np.abs(diff))) / max(float(np.max(np.abs(reference))), np.finfo(float).eps)
    return abs_l2, rel_l2, rel_linf


def _observed_order(errors: list[float], refinement_ratios: list[float]) -> float | None:
    if len(errors) < 2 or len(refinement_ratios) < 1:
        return None
    e_coarse, e_fine = float(errors[-2]), float(errors[-1])
    ratio = float(refinement_ratios[-1])
    if e_coarse <= 0.0 or e_fine <= 0.0 or ratio <= 1.0:
        return None
    order = math.log(e_coarse / e_fine) / math.log(ratio)
    return float(order) if math.isfinite(order) else None


def _richardson_error(last_difference: float, order: float | None, ratio: float) -> float | None:
    if order is None or order <= 0.0 or ratio <= 1.0:
        return None
    denominator = ratio ** order - 1.0
    if denominator <= 0.0 or not math.isfinite(denominator):
        return None
    estimate = float(last_difference) / denominator
    return estimate if math.isfinite(estimate) else None


def _approval_payload(model: ModelIR, *, study: str, runs: int, points: int, work_scale: int) -> dict[str, Any]:
    estimated_evaluations = int(max(1, runs) * max(2, points) * max(1, work_scale))
    level = "low" if estimated_evaluations < 50_000 else "medium" if estimated_evaluations < 2_000_000 else "high"
    return {
        "status": "APPROVAL_REQUIRED",
        "study": study,
        "family": model.family.value,
        "cost": {
            "level": level,
            "planned_refinement_runs": int(runs),
            "temporal_output_points": int(points),
            "estimated_work_units": estimated_evaluations,
            "requires_user_approval": True,
            "reason": "numerical refinement repeats the simulation at stricter discretization/tolerance settings",
        },
        "uncertainty_separation": {
            "numerical": "pending refinement study",
            "parameter": "not estimated by this study",
            "data": "not estimated by this study",
            "model_structural": "not estimated by this study",
        },
    }


def _pde_study(
    model: ModelIR,
    *,
    simulate_once: _SimulateOnce,
    t_span: tuple[float, float],
    points: int,
    parameter_overrides: dict[str, float] | None,
    seed: int,
    tolerance: float,
    approve_heavy: bool,
) -> dict[str, Any]:
    cfg = model.metadata.get("pde", {})
    if not isinstance(cfg, dict):
        raise ValueError("metadata.pde must be an object")
    base_grid = int(cfg.get("grid_points", 32))
    if base_grid < 5:
        raise ValueError("pde.grid_points must be at least 5 for refinement")
    levels: list[int] = []
    current = base_grid
    for _ in range(3):
        if current > 4096:
            break
        levels.append(current)
        next_grid = 2 * current - 1
        if next_grid > 4096:
            break
        current = next_grid
    levels = sorted(set(levels))
    if len(levels) < 2:
        raise ValueError("PDE grid is too large to construct at least two refinement levels")
    if not approve_heavy:
        return _approval_payload(model, study="mesh_refinement", runs=len(levels), points=points, work_scale=sum(levels))

    runs: list[dict[str, Any]] = []
    for index, grid_points in enumerate(levels):
        payload = model.to_dict()
        metadata = dict(payload.get("metadata", {}))
        pde = dict(metadata.get("pde", {}))
        pde["grid_points"] = int(grid_points)
        metadata["pde"] = pde
        payload["metadata"] = metadata
        refined = ModelIR.from_dict(payload)
        result = simulate_once(
            refined,
            t_span=t_span,
            points=points,
            parameter_overrides=parameter_overrides,
            seed=seed + index,
            approve_heavy=True,
        )
        if result.get("status") != "PASS":
            return {
                "status": "FAIL",
                "study": "mesh_refinement",
                "family": model.family.value,
                "failed_grid_points": grid_points,
                "failed_result": result,
            }
        coordinates = result.get("coordinates", {})
        if not isinstance(coordinates, dict) or not coordinates:
            raise ValueError("PDE refinement requires spatial coordinates in the simulation result")
        coordinate_name = next(iter(coordinates))
        x = np.asarray(coordinates[coordinate_name], dtype=float)
        states = result.get("states", {})
        if not isinstance(states, dict) or not states:
            raise ValueError("PDE refinement requires state arrays")
        runs.append({
            "grid_points": int(grid_points),
            "dx": float(result.get("diagnostics", {}).get("dx", np.nan)),
            "coordinate_name": coordinate_name,
            "x": x,
            "states": {name: np.asarray(values, dtype=float) for name, values in states.items()},
            "solver": result.get("solver"),
        })

    comparisons: list[dict[str, Any]] = []
    aggregate_errors: list[float] = []
    refinement_ratios: list[float] = []
    for coarse, fine in zip(runs, runs[1:]):
        state_errors: dict[str, Any] = {}
        max_rel_l2 = 0.0
        for name in sorted(coarse["states"]):
            if name not in fine["states"]:
                raise ValueError(f"state {name!r} missing from refined PDE result")
            coarse_values = coarse["states"][name]
            fine_values = fine["states"][name]
            if coarse_values.ndim != 2 or fine_values.ndim != 2:
                raise ValueError("PDE state arrays must be time-by-space matrices")
            coarse_final = coarse_values[-1]
            fine_final = fine_values[-1]
            fine_on_coarse = np.interp(coarse["x"], fine["x"], fine_final)
            abs_l2, rel_l2, rel_linf = _relative_errors(fine_on_coarse, coarse_final)
            state_errors[name] = {
                "absolute_l2": abs_l2,
                "relative_l2": rel_l2,
                "relative_linf": rel_linf,
            }
            max_rel_l2 = max(max_rel_l2, rel_l2)
        ratio = float(coarse["dx"] / fine["dx"]) if fine["dx"] > 0 else float(fine["grid_points"] - 1) / float(coarse["grid_points"] - 1)
        refinement_ratios.append(ratio)
        aggregate_errors.append(max_rel_l2)
        comparisons.append({
            "coarse_grid_points": coarse["grid_points"],
            "fine_grid_points": fine["grid_points"],
            "refinement_ratio": ratio,
            "max_relative_l2": max_rel_l2,
            "state_errors": state_errors,
        })

    order = _observed_order(aggregate_errors, refinement_ratios)
    final_difference = float(aggregate_errors[-1])
    ratio = float(refinement_ratios[-1])
    richardson = _richardson_error(final_difference, order, ratio)
    numerical_error = richardson if richardson is not None else final_difference
    converged = bool(final_difference <= tolerance)
    return {
        "status": "PASS" if converged else "FAIL",
        "study": "mesh_refinement",
        "family": model.family.value,
        "converged": converged,
        "tolerance": float(tolerance),
        "levels": [{"grid_points": row["grid_points"], "dx": row["dx"], "solver": row["solver"]} for row in runs],
        "comparisons": comparisons,
        "observed_order": order,
        "estimated_numerical_error": float(numerical_error),
        "error_metric": "maximum final-state relative L2 difference across states",
        "uncertainty_separation": {
            "numerical": float(numerical_error),
            "parameter": "separate; use uncertainty propagation",
            "data": "separate; use measurement/residual diagnostics",
            "model_structural": "separate; compare alternative model families",
        },
        "interpretation": "mesh refinement estimates discretization error only; it must not be conflated with parameter, measurement, or structural model uncertainty",
    }


def _tolerance_study(
    model: ModelIR,
    *,
    simulate_once: _SimulateOnce,
    t_span: tuple[float, float],
    points: int,
    parameter_overrides: dict[str, float] | None,
    seed: int,
    tolerance: float,
    approve_heavy: bool,
) -> dict[str, Any]:
    factors = (1.0, 0.1, 0.01)
    if not approve_heavy:
        return _approval_payload(model, study="solver_tolerance_refinement", runs=len(factors), points=points, work_scale=max(1, len(model.variables) * 20))
    runs: list[dict[str, Any]] = []
    for index, factor in enumerate(factors):
        payload = model.to_dict()
        solver = dict(payload.get("solver", {}))
        solver["rtol"] = max(float(model.solver.rtol) * factor, 1e-13)
        solver["atol"] = max(float(model.solver.atol) * factor, 1e-15)
        payload["solver"] = solver
        refined = ModelIR.from_dict(payload)
        result = simulate_once(
            refined,
            t_span=t_span,
            points=points,
            parameter_overrides=parameter_overrides,
            seed=seed + index,
            approve_heavy=True,
        )
        if result.get("status") != "PASS":
            return {
                "status": "FAIL",
                "study": "solver_tolerance_refinement",
                "family": model.family.value,
                "failed_factor": factor,
                "failed_result": result,
            }
        states = result.get("states")
        if not isinstance(states, dict) or not states:
            raise ValueError("tolerance refinement requires state trajectories")
        runs.append({
            "factor": factor,
            "rtol": solver["rtol"],
            "atol": solver["atol"],
            "states": {name: np.asarray(values, dtype=float) for name, values in states.items()},
            "solver": result.get("solver"),
        })

    comparisons: list[dict[str, Any]] = []
    aggregate_errors: list[float] = []
    refinement_ratios: list[float] = []
    for coarse, fine in zip(runs, runs[1:]):
        state_errors: dict[str, Any] = {}
        max_rel_l2 = 0.0
        for name in sorted(coarse["states"]):
            abs_l2, rel_l2, rel_linf = _relative_errors(fine["states"][name], coarse["states"][name])
            state_errors[name] = {"absolute_l2": abs_l2, "relative_l2": rel_l2, "relative_linf": rel_linf}
            max_rel_l2 = max(max_rel_l2, rel_l2)
        ratio = coarse["rtol"] / fine["rtol"]
        refinement_ratios.append(float(ratio))
        aggregate_errors.append(max_rel_l2)
        comparisons.append({
            "coarse_rtol": coarse["rtol"],
            "fine_rtol": fine["rtol"],
            "refinement_ratio": float(ratio),
            "max_relative_l2": max_rel_l2,
            "state_errors": state_errors,
        })
    order = _observed_order(aggregate_errors, refinement_ratios)
    final_difference = float(aggregate_errors[-1])
    richardson = _richardson_error(final_difference, order, float(refinement_ratios[-1]))
    numerical_error = richardson if richardson is not None else final_difference
    converged = bool(final_difference <= tolerance)
    return {
        "status": "PASS" if converged else "FAIL",
        "study": "solver_tolerance_refinement",
        "family": model.family.value,
        "converged": converged,
        "tolerance": float(tolerance),
        "levels": [{"rtol": row["rtol"], "atol": row["atol"], "solver": row["solver"]} for row in runs],
        "comparisons": comparisons,
        "observed_order": order,
        "estimated_numerical_error": float(numerical_error),
        "error_metric": "maximum trajectory relative L2 difference across states",
        "uncertainty_separation": {
            "numerical": float(numerical_error),
            "parameter": "separate; use uncertainty propagation",
            "data": "separate; use measurement/residual diagnostics",
            "model_structural": "separate; compare alternative model families",
        },
        "interpretation": "solver-tolerance refinement estimates numerical integration sensitivity only; it is distinct from scientific/model uncertainty",
    }


def numerical_refinement_study(
    model: ModelIR,
    *,
    simulate_once: _SimulateOnce,
    t_span: tuple[float, float],
    points: int = 200,
    parameter_overrides: dict[str, float] | None = None,
    seed: int = 0,
    tolerance: float = 1e-3,
    approve_heavy: bool = False,
) -> dict[str, Any]:
    """Run a mesh/tolerance refinement study for discretized numerical models."""
    if tolerance <= 0.0 or not math.isfinite(tolerance):
        raise ValueError("numerical refinement tolerance must be finite and positive")
    if points < 2:
        raise ValueError("points must be at least 2")
    if model.family == ModelFamily.PDE:
        return _pde_study(
            model,
            simulate_once=simulate_once,
            t_span=t_span,
            points=points,
            parameter_overrides=parameter_overrides,
            seed=seed,
            tolerance=tolerance,
            approve_heavy=approve_heavy,
        )
    if model.family in {ModelFamily.ODE, ModelFamily.DAE}:
        return _tolerance_study(
            model,
            simulate_once=simulate_once,
            t_span=t_span,
            points=points,
            parameter_overrides=parameter_overrides,
            seed=seed,
            tolerance=tolerance,
            approve_heavy=approve_heavy,
        )
    return {
        "status": "NOT_APPLICABLE",
        "family": model.family.value,
        "detail": "native refinement study currently applies to ODE, DAE, and PDE families",
        "uncertainty_separation": {
            "numerical": "not estimated for this family",
            "parameter": "separate",
            "data": "separate",
            "model_structural": "separate",
        },
    }
