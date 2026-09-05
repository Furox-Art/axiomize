"""Runtime capability discovery."""
from __future__ import annotations

import importlib.util
from typing import Any


class Capability(dict[str, Any]):
    def __bool__(self) -> bool: return bool(self.get("available", False))


def _present(module: str) -> bool: return importlib.util.find_spec(module) is not None

def _cap(available: bool, **metadata: Any) -> Capability: return Capability(available=bool(available), **metadata)


def get_capabilities() -> dict[str, Any]:
    from axiomize.formal.lean_adapter import LeanAdapter
    from axiomize.integrations.scs_adapter import scs_probe
    from axiomize.model_ir import CURRENT_SCHEMA_VERSION, ModelFamily
    from axiomize.tools.pde.fenics_tool import FEniCSAdapter

    scs = scs_probe(); all_families = [family.value for family in ModelFamily]
    fenics = FEniCSAdapter.availability()
    return {
        "axiomize_version": _version(),
        "adaptive_intake": _cap(True, levels=["weak", "medium", "strong"], question_modes=["one_by_one", "all_at_once", "adaptive"]),
        "consumption_guard": _cap(True, guarded_actions=[
            "spawn_subtask", "repeat_alternative_method", "extra_paid_model_call", "heavy_compute",
            "constraint_rebuild", "model_discovery", "experiment_design", "ir_migration",
            "bayesian_sampling", "multiphysics_cosimulation", "surrogate_training_data_generation", "numerical_refinement",
        ]),
        "model_ir": _cap(True, schema_version=CURRENT_SCHEMA_VERSION, versioned=True, migration_requires_approval=True, families=all_families),
        "general_modeling": _cap(
            True, candidate_family_ranking=True, solver_selection=True, visible_solver_fallbacks=True,
            scientific_constraints=True, constraint_repair_requires_approval=True, native_execution=all_families,
            routed_specialized_execution=[], pde_method_of_lines=True, dae_index1=True, nonlinear_optimization=True,
            state_space_control=True, graph_dynamics=True, builtin_bayesian_mh=True, agent_based=True,
            discrete_event=True, hybrid_event_ode=True, causal_identification_guard=True,
            causal_engine="2.0", multiphysics_cosimulation=True,
            note="all Model IR families have explicit native execution contracts; no family is silently replaced by a reference model",
        ),
        "model_fitting": _cap(_present("scipy"), native_generic=["ode"], identifiability=True,
                              residual_diagnostics=True, information_criteria=["AIC", "BIC"]),
        "model_discovery": _cap(True, native_methods=["sindy_style_sparse_dynamics"], requires_approval=True, discovered_models_start_unverified=True),
        "surrogate_modeling": _cap(True, native_methods=["polynomial_response_surface"],
                                   training_design=["supplied_data", "latin_hypercube_full_model_generation"],
                                   full_model_generation_requires_approval=True, untouched_holdout_validation=True,
                                   extrapolation_blocked_by_default=True, never_silently_replaces_full_model=True),
        "causal_guard": _cap(True, fit_or_correlation_alone_is_not_causal=True),
        "causal_inference": _cap(True, engine="2.0", dag_cycle_validation=True, backdoor_d_separation=True,
                                 bounded_auto_adjustment=True, estimators=["difference_in_means", "robust_ols", "ipw", "aipw"],
                                 overlap_diagnostics=True, counterfactual_means=True),
        "uncertainty_separation": _cap(True, components=["aleatoric", "epistemic", "numerical", "structural"]),
        "numerical_verification": _cap(True, families=all_families,
                                       contracts={"ode_dae": "solver_tolerance", "pde": "mesh_refinement",
                                                  "stochastic_abm_des": "sampling_convergence", "bayesian": "mcmc_convergence",
                                                  "optimization": "multistart", "control_network_hybrid": "output_grid_refinement",
                                                  "causal": "conditioning_overlap", "algebraic_multiphysics": "repeatability/coupling"},
                                       repeated_work_requires_approval=True),
        "validity_and_stability": _cap(True, parameter_scan=True, ode_linear_stability=True, nondimensionalization_plan=True),
        "experiment_design": _cap(True, information_proxy="local Fisher-information proxy", requires_approval=True),
        "provenance": _cap(True, tool_versions=True, seed=True, data_hash=True, assumptions=True, solver=True),
        "model_export": _cap(True,
            native=["json", "python", "ipynb", "sbml-l3v2", "cellml-2.0", "latex", "mathml", "dot", "markdown"],
            family_scoped=["julia-ode"], optional=["yaml"], conservative_unversioned_aliases=["sbml", "cellml"],
            standard_validation_is_explicit=True),
        "symbolic_math": _cap(_present("sympy"), backend="sympy"),
        "numerical_computing": _cap(_present("scipy"), backend="scipy"),
        "statistics": _cap(_present("statsmodels"), backend="statsmodels"),
        "visualization": _cap(_present("matplotlib"), backend="matplotlib", supports_3d=True),
        "optimization_convex": _cap(_present("cvxpy"), backend="cvxpy"),
        "optimization_nonlinear": _cap(True, native_backend="scipy", optional_casadi=_present("casadi")),
        "bayesian_inference": _cap(True, native_backend="multi_chain_builtin_mh", optional_pymc=_present("pymc"),
                                   diagnostics=["split_rhat", "ess_bulk", "mcse_mean"], posterior_predictive_checks=True),
        "bayesian_builtin_mh": _cap(True, backend="builtin", chains=True),
        "automatic_differentiation": _cap(_present("jax"), backend="jax"),
        "z3_verification": _cap(_present("z3"), backend="z3"),
        "formal_verification": _cap(LeanAdapter.availability().available, backend="lean"),
        "network_models": _cap(True, native_backend="scipy", optional_networkx=_present("networkx")),
        "control_models": _cap(True, native_backend="scipy.signal", optional_control=_present("control")),
        "pde_models": _cap(True, native_backend="scipy_method_of_lines", optional_fenics=fenics.available,
                           fenics_reason=fenics.reason, fem_safe_subset=["poisson_1d"] if fenics.available else []),
        "dae_models": _cap(True, native_backend="scipy_index1", optional_casadi=_present("casadi")),
        "multiphysics": _cap(True, backend="axiomize_partitioned_cosimulation", requires_approval=True),
        "fenics": _cap(fenics.available, backend="fenicsx_or_legacy", version=fenics.version, reason=fenics.reason,
                       safe_declarative_problems=["poisson_1d"]),
        "gpu": _cap(_present("torch") or _present("jax"), backends={"torch": _present("torch"), "jax": _present("jax")}),
        "scientific_computing_system": _cap(scs["cds"] or scs["cds2"], backends=scs),
        "interfaces": ["cli", "mcp", "rest"], "api_version": "v1",
    }


def _version() -> str:
    import axiomize
    return getattr(axiomize, "__version__", "unknown")
