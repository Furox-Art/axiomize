"""Runtime integration hooks for Axiomize 1.12 scientific upgrades."""
from __future__ import annotations

from typing import Any

from axiomize.model_ir import ModelFamily, ModelIR


def install(engine: Any, advanced: Any) -> None:
    if getattr(engine, "_AXIOMIZE_112_INSTALLED", False):
        return
    from axiomize.bayesian.engine_v2 import infer_bayesian_model
    from axiomize.causal_engine import estimate_causal_model
    from axiomize.extended_export import export_extended
    from axiomize.numerical_verification_v2 import numerical_refinement_study_v2

    advanced._estimate_causal = estimate_causal_model

    def infer_bayesian_compat(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = infer_bayesian_model(*args, **kwargs)
        diagnostics = result.get("diagnostics")
        if isinstance(diagnostics, dict):
            rates = diagnostics.get("acceptance_rate_by_chain")
            if isinstance(rates, list) and rates:
                diagnostics["acceptance_rate"] = float(sum(float(v) for v in rates) / len(rates))
        return result
    advanced._infer_bayesian = infer_bayesian_compat

    # Every executable family gets an explicit numerical-verification contract.
    engine._NUMERICALLY_REFINED = set(ModelFamily)

    def numerical_refinement_v2(
        model: ModelIR,
        *,
        t_span: tuple[float, float] = (0.0, 1.0),
        points: int = 200,
        parameter_overrides: dict[str, float] | None = None,
        seed: int = 0,
        tolerance: float = 1e-3,
        approve_heavy: bool = False,
    ) -> dict[str, Any]:
        return numerical_refinement_study_v2(
            model,
            simulate_once=engine._simulate_once,
            t_span=engine._validated_span(t_span),
            points=engine._validated_points(points, model),
            parameter_overrides=parameter_overrides,
            seed=seed,
            tolerance=float(tolerance),
            approve_heavy=approve_heavy,
        )
    engine.numerical_refinement = numerical_refinement_v2

    original_export = engine.export_model
    def export_model_v2(model: ModelIR, *, format: str = "json") -> dict[str, Any]:
        extended = export_extended(model, format=format)
        return extended if extended is not None else original_export(model, format=format)
    engine.export_model = export_model_v2
    engine._core.export_model = export_model_v2
    engine._AXIOMIZE_112_INSTALLED = True
