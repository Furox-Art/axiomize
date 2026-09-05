"""Runtime capability discovery with truthful optional-backend probing."""
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
    from axiomize.tools.pde.fenics_tool import FEniCSAdapter

    scs = scs_probe(); families = [family.value for family in ModelFamily]
    fenics = FEniCSAdapter.availability()
    return {
        "axiomize_version": _version(),
        "adaptive_intake": _cap(True, levels=["weak", "medium", "strong"], question_modes=["one_by_one", "all_at_once", "adaptive"]),
        "consumption_guard": _cap(True, guarded_actions=["spawn_subtask", "repeat_alternative_method", "extra_paid_model_call", "heavy_compute", "constraint_rebuild", "model_discovery", "experiment_design", "ir_migration", "bayesian_sampling", "multiphysics_cosimulation", "surrogate_training_data_generation", "numerical_refinement"]),
        "model_ir": _cap(True, schema_version=CURRENT_SCHEMA_VERSION, versioned=True, migration_requires_approval=True, families=families),
        "general_modeling": _cap(True, candidate_family_ranking=True, solver_selection=True, visible_solver_fallbacks=True, scientific_constraints=True,
                                 constraint_repair_requires_approval=True, native_execution=families, pde_method_of_lines=True, dae_index1=True,
                                 nonlinear_optimization=True, state_space_control=True, graph_dynamics=True, agent_based=True, discrete_event=True,
                                 hybrid_event_ode=True, multiphysics_cosimulation=True),
        "causal_engine": _cap(True, version="2.0", no_causality_from_correlation=True, dag_cycle_validation=True, backdoor_adjustment=True,
                              binary_treatment_estimators=["AIPW", "IPW", "outcome_regression"], continuous_treatment="robust_linear_backdoor",
                              diagnostics=["positivity_overlap", "effective_sample_size", "standardized_mean_difference"], counterfactual_interventions=True),
        "bayesian_inference": _cap(True, native_backend="multi_chain_random_walk_metropolis", optional_pymc=_present("pymc"),
                                   diagnostics=["split_Rhat", "bulk_ESS", "MCSE", "HDI95"], posterior_predictive_checks=True,
                                   ppc=["predictive_RMSE", "coverage90", "coverage95", "Bayesian_p_values"]),
        "numerical_verification": _cap(True, families=families, approval_gated_repeated_runs=True,
                                       dedicated=["ODE_tolerance", "DAE_tolerance", "PDE_mesh"],
                                       generic=["same_seed_reproducibility", "output_resolution_refinement"],
                                       separates=["numerical", "aleatoric", "parameter", "data", "model_structural"]),
        "model_fitting": _cap(_present("scipy"), native_generic=["ode"], identifiability=True, residual_diagnostics=True, information_criteria=["AIC", "BIC"]),
        "model_discovery": _cap(True, native_methods=["sindy_style_sparse_dynamics"], requires_approval=True, discovered_models_start_unverified=True),
        "surrogate_modeling": _cap(True, native_methods=["polynomial_response_surface"], training_design=["supplied_data", "latin_hypercube_full_model_generation"],
                                  full_model_generation_requires_approval=True, untouched_holdout_validation=True, extrapolation_blocked_by_default=True,
                                  never_silently_replaces_full_model=True),
        "uncertainty_separation": _cap(True, components=["aleatoric", "epistemic", "numerical", "structural"]),
        "validity_and_stability": _cap(True, parameter_scan=True, ode_linear_stability=True, nondimensionalization_plan=True),
        "experiment_design": _cap(True, information_proxy="local Fisher-information proxy", requires_approval=True),
        "provenance": _cap(True, tool_versions=True, seed=True, data_hash=True, assumptions=True, solver=True),
        "model_export": _cap(True,
            native=["json", "python", "ipynb", "sbml-l3v2", "cellml-2.0", "modelica-3.6", "graphml", "causal-dot", "portable-bundle-v1"],
            optional=["yaml"], conservative_unversioned_aliases=["sbml", "cellml"], standard_validation_is_explicit=True),
        "scientific_stress_matrix": _cap(True, all_model_families=True, exact_wheel_release_gate=True, bounded_runtime=True),
        "symbolic_math": _cap(_present("sympy"), backend="sympy"),
        "numerical_computing": _cap(_present("scipy"), backend="scipy"),
        "statistics": _cap(_present("statsmodels"), backend="statsmodels"),
        "visualization": _cap(_present("matplotlib"), backend="matplotlib", supports_3d=True),
        "optimization_convex": _cap(_present("cvxpy"), backend="cvxpy"),
        "optimization_nonlinear": _cap(True, native_backend="scipy", optional_casadi=_present("casadi")),
        "automatic_differentiation": _cap(_present("jax"), backend="jax"),
        "z3_verification": _cap(_present("z3"), backend="z3"),
        "formal_verification": _cap(LeanAdapter.availability().available, backend="lean"),
        "network_models": _cap(True, native_backend="scipy", optional_networkx=_present("networkx")),
        "control_models": _cap(True, native_backend="scipy.signal", optional_control=_present("control")),
        "pde_models": _cap(True, native_backend="scipy_method_of_lines", optional_fenics=fenics.available,
                           fenics_version=fenics.version if fenics.available else None, fenics_reason=fenics.reason),
        "fenics": _cap(fenics.available, backend="dolfinx_or_fenics", version=fenics.version, reason=fenics.reason,
                       structured_executor="bounded Poisson P1 FEM on unit interval/square"),
        "dae_models": _cap(True, native_backend="scipy_index1", optional_casadi=_present("casadi")),
        "multiphysics": _cap(True, backend="axiomize_partitioned_cosimulation", requires_approval=True),
        "gpu": _cap(_present("torch") or _present("jax"), backends={"torch": _present("torch"), "jax": _present("jax")}),
        "scientific_computing_system": _cap(scs["cds"] or scs["cds2"], backends=scs),
        "interfaces": ["cli", "mcp", "rest"], "api_version": "v1",
    }


def _version() -> str:
    import axiomize
    return getattr(axiomize, "__version__", "unknown")
