"""Backward-compatible public facade for the scientific Model IR engine.

The stable 1.8 engine implementation lives in :mod:`general_engine_core`.  This
facade preserves that public API while extending execution to advanced model
families through deterministic native adapters.  It deliberately keeps the
same Model IR contract and never substitutes a hidden reference model.
"""

from __future__ import annotations

from typing import Any

from axiomize import general_engine_core as _core
from axiomize.general_engine_core import *  # noqa: F401,F403
from axiomize.model_ir import ModelFamily, ModelIR

# A small number of internal helpers are intentionally imported by the existing
# advanced diagnostics module.  Star imports omit underscore names, so preserve
# those compatibility symbols explicitly while the core is split behind this
# facade.
_parameter_values = _core._parameter_values
_sympy_expression = _core._sympy_expression

_base_select_solver = _core.select_solver
_base_estimate_compute = _core.estimate_compute
_base_recommend_model_families = _core.recommend_model_families
_base_simulate_model = _core.simulate_model

_CORE_NATIVE = {ModelFamily.ODE, ModelFamily.STOCHASTIC, ModelFamily.ALGEBRAIC}
_ADVANCED_NATIVE = {
    ModelFamily.PDE,
    ModelFamily.DAE,
    ModelFamily.OPTIMIZATION,
    ModelFamily.CONTROL,
    ModelFamily.NETWORK,
    ModelFamily.BAYESIAN,
    ModelFamily.AGENT_BASED,
    ModelFamily.DISCRETE_EVENT,
    ModelFamily.HYBRID,
    ModelFamily.MULTIPHYSICS,
    ModelFamily.CAUSAL,
}


def select_solver(model: ModelIR) -> dict[str, Any]:
    """Select the native backend, including coupled multi-physics execution."""
    if model.family == ModelFamily.MULTIPHYSICS:
        if model.solver.backend != "auto" or model.solver.method != "auto":
            return {
                "backend": model.solver.backend,
                "method": model.solver.method,
                "fallbacks": list(model.solver.fallbacks),
                "reason": "explicit solver configuration",
            }
        return {
            "backend": "axiomize",
            "method": "partitioned_fixed_point_cosimulation",
            "fallbacks": [],
            "reason": "coupled component Model IR co-simulation with explicit convergence diagnostics",
        }
    return _base_select_solver(model)


def estimate_compute(
    model: ModelIR,
    *,
    action: str = "simulate",
    points: int = 1000,
    samples: int = 1,
) -> dict[str, Any]:
    """Estimate compute and preserve consent gates for multiplicative families."""
    if model.family != ModelFamily.MULTIPHYSICS:
        out = dict(_base_estimate_compute(model, action=action, points=points, samples=samples))
    else:
        action_factor = {
            "solve": 1,
            "simulate": 1,
            "validate": 2,
            "fit": 12,
            "uncertainty": 20,
            "parameter_scan": 25,
            "discovery": 30,
            "experiment_design": 15,
        }.get(action, 5)
        evals = max(1, int(points)) * max(1, int(samples)) * 40 * action_factor
        level = "low" if evals < 50_000 else "medium" if evals < 2_000_000 else "high"
        estimated_memory_mb = max(
            1.0,
            len(model.variables) * max(1, int(points)) * 8 / 1_000_000 * max(2, int(samples)),
        )
        out = {
            "action": action,
            "level": level,
            "estimated_model_evaluations": int(evals),
            "estimated_memory_mb": round(float(estimated_memory_mb), 2),
            "requires_user_approval": True,
            "reason": "multi-physics co-simulation can multiply component solves; explicit approval required",
        }

    guarded_family = model.family in {ModelFamily.BAYESIAN, ModelFamily.MULTIPHYSICS}
    if action in {"simulate", "solve", "fit"} and guarded_family:
        out["requires_user_approval"] = True
        if model.family == ModelFamily.BAYESIAN:
            out["reason"] = "Bayesian posterior sampling can be compute-intensive; explicit approval required"
        else:
            out["reason"] = "multi-physics co-simulation can multiply component solves; explicit approval required"
    return out


def recommend_model_families(
    *,
    domain: str = "general",
    signals: list[str] | None = None,
    idea: str = "",
) -> list[dict[str, Any]]:
    """Rank candidates and recognize explicit coupled/multi-physics problems."""
    base = list(_base_recommend_model_families(domain=domain, signals=signals, idea=idea))
    signal_set = {str(value).strip().lower().replace("-", "_") for value in (signals or [])}
    text = str(idea).lower()
    wants_multiphysics = bool(
        {"multiphysics", "multi_physics", "coupled_physics", "multi_scale", "multiscale"} & signal_set
        or "multiphysics" in text
        or "multi-physics" in text
        or "coupled physics" in text
        or "multiscale" in text
        or "multi-scale" in text
    )
    if not wants_multiphysics:
        return base
    combined = [
        {
            "rank": 1,
            "family": ModelFamily.MULTIPHYSICS.value,
            "reason": "explicit coupled multi-physics/multi-scale signal",
            "score": 100,
        },
        *[row for row in base if row.get("family") != ModelFamily.MULTIPHYSICS.value],
    ][:3]
    for index, row in enumerate(combined, start=1):
        row["rank"] = index
    return combined


def simulate_model(
    model: ModelIR,
    *,
    t_span: tuple[float, float] = (0.0, 1.0),
    points: int = 200,
    parameter_overrides: dict[str, float] | None = None,
    seed: int = 0,
    approve_heavy: bool = False,
) -> dict[str, Any]:
    """Execute every supported Model IR family without silent fallback."""
    structure = model.validate_structure()
    if any(check["status"] == "FAIL" for check in structure):
        return {"status": "FAIL", "stage": "structure", "checks": structure}

    cost = estimate_compute(model, action="simulate", points=points)
    if cost["requires_user_approval"] and not approve_heavy:
        return {
            "status": "APPROVAL_REQUIRED",
            "cost": cost,
            "plan": build_execution_plan(model, action="simulate", points=points),
        }

    if model.family in _CORE_NATIVE:
        return _base_simulate_model(
            model,
            t_span=t_span,
            points=points,
            parameter_overrides=parameter_overrides,
            seed=seed,
            approve_heavy=True,
        )

    if model.family in _ADVANCED_NATIVE:
        from axiomize.advanced_family_engine import simulate_advanced_family

        return simulate_advanced_family(
            model,
            t_span=t_span,
            points=points,
            parameter_overrides=parameter_overrides,
            seed=seed,
            validate_fn=_core.validate_model,
            simulate_fn=simulate_model,
        )

    return {
        "status": "TOOL_ROUTE_REQUIRED",
        "family": model.family.value,
        "solver": select_solver(model),
        "detail": "no native executor registered for this Model IR family",
    }


# The preserved core functions (validity scans, experiment design, provenance,
# execution planning, generated Python export, etc.) resolve these names through
# their original module globals. Patch those globals once so every public path
# uses the same extended runtime rather than a divergent implementation.
_core.select_solver = select_solver
_core.estimate_compute = estimate_compute
_core.recommend_model_families = recommend_model_families
_core.simulate_model = simulate_model
