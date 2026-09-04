"""Runtime capability discovery.

Capabilities are explicit about what the generic engine executes natively and
what is only routed to a specialized scientific backend.
"""

from __future__ import annotations

import importlib.util
from typing import Any


class Capability(dict[str, Any]):
    def __bool__(self) -> bool:
        return bool(self.get("available", False))


def _present(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _cap(available: bool, **metadata: Any) -> Capability:
    return Capability(available=bool(available), **metadata)


def get_capabilities() -> dict[str, Any]:
    from axiomize.formal.lean_adapter import LeanAdapter
    from axiomize.integrations.scs_adapter import scs_probe
    from axiomize.model_ir import CURRENT_SCHEMA_VERSION, ModelFamily

    scs = scs_probe()
    all_families = [family.value for family in ModelFamily]
    return {
        "axiomize_version": _version(),
        "adaptive_intake": _cap(True, levels=["weak", "medium", "strong"],
                                question_modes=["one_by_one", "all_at_once", "adaptive"]),
        "consumption_guard": _cap(True, guarded_actions=[
            "spawn_subtask", "repeat_alternative_method", "extra_paid_model_call",
            "heavy_compute", "constraint_rebuild", "model_discovery",
            "experiment_design", "ir_migration",
        ]),
        "model_ir": _cap(
            True, schema_version=CURRENT_SCHEMA_VERSION, versioned=True,
            migration_requires_approval=True, families=all_families,
        ),
        "general_modeling": _cap(
            True,
            candidate_family_ranking=True,
            solver_selection=True,
            visible_solver_fallbacks=True,
            scientific_constraints=True,
            constraint_repair_requires_approval=True,
            native_execution=["ode", "stochastic", "algebraic"],
            routed_specialized_execution=[
                "pde", "dae", "optimization", "control", "network", "bayesian",
                "agent_based", "discrete_event", "hybrid", "causal",
            ],
            note="routed families are not silently replaced by a generic/reference model",
        ),
        "model_fitting": _cap(
            _present("scipy"), native_generic=["ode"],
            identifiability=True, residual_diagnostics=True,
            information_criteria=["AIC", "BIC"],
        ),
        "model_discovery": _cap(True, native_methods=["sindy_style_sparse_dynamics"],
                                requires_approval=True, discovered_models_start_unverified=True),
        "causal_guard": _cap(True, fit_or_correlation_alone_is_not_causal=True),
        "uncertainty_separation": _cap(True, components=["aleatoric", "epistemic"]),
        "validity_and_stability": _cap(True, parameter_scan=True, ode_linear_stability=True,
                                       nondimensionalization_plan=True),
        "experiment_design": _cap(True, information_proxy="local Fisher-information proxy",
                                  requires_approval=True),
        "provenance": _cap(True, tool_versions=True, seed=True, data_hash=True,
                           assumptions=True, solver=True),
        "model_export": _cap(True, native=["json", "python"], optional=["yaml"],
                             adapters_required=["sbml", "cellml"]),
        "symbolic_math": _cap(_present("sympy"), backend="sympy"),
        "numerical_computing": _cap(_present("scipy"), backend="scipy"),
        "statistics": _cap(_present("statsmodels"), backend="statsmodels"),
        "visualization": _cap(_present("matplotlib"), backend="matplotlib", supports_3d=True),
        "optimization_convex": _cap(_present("cvxpy"), backend="cvxpy"),
        "optimization_nonlinear": _cap(_present("casadi"), backend="casadi"),
        "bayesian_inference": _cap(_present("pymc"), backend="pymc"),
        "bayesian_builtin_mh": _cap(True, backend="builtin"),
        "automatic_differentiation": _cap(_present("jax"), backend="jax"),
        "z3_verification": _cap(_present("z3"), backend="z3"),
        "formal_verification": _cap(LeanAdapter.availability().available, backend="lean"),
        "network_models": _cap(_present("networkx"), backend="networkx"),
        "control_models": _cap(_present("control"), backend="control"),
        "fenics": _cap(_present("fenics"), backend="fenics"),
        "gpu": _cap(_present("torch") or _present("jax"), backends={
            "torch": _present("torch"), "jax": _present("jax"),
        }),
        "scientific_computing_system": _cap(scs["cds"] or scs["cds2"], backends=scs),
        "interfaces": ["cli", "mcp", "rest"],
        "api_version": "v1",
    }


def _version() -> str:
    import axiomize
    return getattr(axiomize, "__version__", "unknown")
