"""Non-bypassable runtime guards and scientific-maturity extensions.

Installed at package import so CLI, REST, MCP and direct Python calls share the
same resource ceilings and the same causal/Bayesian/verification/export engines.
"""
from __future__ import annotations

from typing import Any, Callable

from axiomize.limits import MAX_ARRAY_ITEMS, MAX_BAYES_DRAWS, bounded_int, enforce_result_cells
from axiomize.model_ir import ModelFamily, ModelIR

_MAX_PDE_GRID_POINTS = 4096
_MAX_CAUSAL_COVARIATES = 2048
_MAX_CAUSAL_DESIGN_CELLS = 20_000_000
_MAX_BAYES_CHAINS = 8
_MAX_BAYES_LIKELIHOOD_WORK = 50_000_000


def _extra_preflight(model: ModelIR, *, points: int) -> None:
    metadata = model.metadata if isinstance(model.metadata, dict) else {}
    state_count = max(1, sum(v.role == "state" for v in model.variables))

    if model.family == ModelFamily.PDE:
        cfg = metadata.get("pde", {})
        if not isinstance(cfg, dict): raise ValueError("metadata.pde must be an object")
        grid_points = bounded_int(cfg.get("grid_points", 32), name="pde.grid_points", minimum=5, maximum=_MAX_PDE_GRID_POINTS)
        enforce_result_cells(state_count, points, grid_points, name="PDE trajectory")
        profiles = cfg.get("initial_profiles", {})
        if profiles is not None and not isinstance(profiles, dict): raise ValueError("pde.initial_profiles must be an object")
        if isinstance(profiles, dict):
            for name, values in profiles.items():
                if isinstance(values, list) and len(values) > _MAX_PDE_GRID_POINTS: raise ValueError(f"pde.initial_profiles.{name} exceeds grid hard limit")

    elif model.family == ModelFamily.BAYESIAN:
        cfg = metadata.get("bayesian", {})
        if not isinstance(cfg, dict): raise ValueError("metadata.bayesian must be an object")
        draws = bounded_int(cfg.get("draws", max(200, points)), name="bayesian.draws", minimum=50, maximum=MAX_BAYES_DRAWS)
        burn = bounded_int(cfg.get("burn", max(50, draws // 4)), name="bayesian.burn", minimum=0, maximum=MAX_BAYES_DRAWS)
        chains = bounded_int(cfg.get("chains", 4), name="bayesian.chains", minimum=2, maximum=_MAX_BAYES_CHAINS)
        observed = cfg.get("observations", cfg.get("observed"))
        if observed is None and isinstance(cfg.get("outcome"), str):
            data = cfg.get("data", {})
            if isinstance(data, dict): observed = data.get(str(cfg["outcome"]))
        if isinstance(observed, list):
            if len(observed) > MAX_ARRAY_ITEMS: raise ValueError(f"bayesian observations exceed hard limit {MAX_ARRAY_ITEMS}")
            if chains * (draws + burn) * max(1, len(observed)) > _MAX_BAYES_LIKELIHOOD_WORK:
                raise ValueError(f"Bayesian request exceeds hard {_MAX_BAYES_LIKELIHOOD_WORK:,} likelihood-work-unit limit")
        if bool(cfg.get("return_samples", False)):
            enforce_result_cells(chains, draws, max(1, len(model.parameters)), name="Bayesian returned samples")

    elif model.family == ModelFamily.CAUSAL:
        cfg = metadata.get("causal", {})
        if not isinstance(cfg, dict): raise ValueError("metadata.causal must be an object")
        data = cfg.get("data", {})
        if not isinstance(data, dict): raise ValueError("causal.data must be an object")
        n_rows: int | None = None
        for name, values in data.items():
            if not isinstance(values, list): raise ValueError(f"causal.data.{name} must be an array")
            if len(values) > MAX_ARRAY_ITEMS: raise ValueError(f"causal.data.{name} exceeds hard limit {MAX_ARRAY_ITEMS}")
            if n_rows is None: n_rows = len(values)
            elif len(values) != n_rows: raise ValueError("all causal.data arrays must have the same length")
        identification = cfg.get("identification", metadata.get("causal_identification", {}))
        adjustment = []
        if isinstance(identification, dict): adjustment = identification.get("adjustment_set", [])
        if not adjustment: adjustment = cfg.get("adjustment_set", cfg.get("covariates", []))
        if not isinstance(adjustment, list): raise ValueError("causal adjustment_set/covariates must be an array")
        if len(adjustment) > _MAX_CAUSAL_COVARIATES: raise ValueError(f"causal covariates exceed hard limit {_MAX_CAUSAL_COVARIATES}")
        columns = 2 + len(adjustment)
        if (n_rows or 0) * columns > _MAX_CAUSAL_DESIGN_CELLS: raise ValueError(f"causal design matrix exceeds hard limit {_MAX_CAUSAL_DESIGN_CELLS} cells")


def install_general_engine_guards(engine_module: Any) -> None:
    """Install all non-bypassable runtime/scientific extensions exactly once."""
    current = getattr(engine_module, "_advanced_preflight", None)
    if not callable(current): raise RuntimeError("general engine does not expose the expected advanced preflight hook")
    if not getattr(current, "__axiomize_runtime_guard__", False):
        original: Callable[..., None] = current
        def guarded(model: ModelIR, *, points: int) -> None:
            original(model, points=points); _extra_preflight(model, points=points)
        guarded.__axiomize_runtime_guard__ = True  # type: ignore[attr-defined]
        engine_module._advanced_preflight = guarded

    # Replace legacy advanced-family causal/Bayesian implementations with the
    # versioned engines. advanced_family_engine is already imported by package
    # initialization, so direct callers cannot bypass these replacements.
    from axiomize import advanced_family_engine as advanced
    from axiomize.bayesian_engine import infer_bayesian
    from axiomize.causal_engine import estimate_causal
    advanced._estimate_causal = lambda model, *, t_span, points, parameter_overrides, seed: estimate_causal(
        model, t_span=t_span, points=points, parameter_overrides=parameter_overrides, seed=seed
    )
    advanced._infer_bayesian = lambda model, *, t_span, points, parameter_overrides, seed: infer_bayesian(
        model, t_span=t_span, points=points, parameter_overrides=parameter_overrides, seed=seed
    )

    # Every family now exposes an explicit numerical-verification contract. The
    # contract remains family-specific and never labels sampling/conditioning
    # diagnostics as discretization error.
    from axiomize import numerical_verification as verification_module
    from axiomize.numerical_verification_ext import install_family_complete_verification
    install_family_complete_verification(verification_module)
    engine_module._NUMERICALLY_REFINED = set(ModelFamily)

    # Extend portable/document exports while preserving existing JSON/Python/
    # YAML/SBML/CellML/notebook behavior.
    if not getattr(engine_module.export_model, "__axiomize_extended_export__", False):
        from axiomize.export_extensions import export_extended
        original_export = engine_module.export_model
        def extended_export(model: ModelIR, *, format: str = "json") -> dict[str, Any]:
            extra = export_extended(model, format=format)
            return extra if extra is not None else original_export(model, format=format)
        extended_export.__axiomize_extended_export__ = True  # type: ignore[attr-defined]
        engine_module.export_model = extended_export
        engine_module._core.export_model = extended_export
