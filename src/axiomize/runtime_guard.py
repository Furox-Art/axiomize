"""Non-bypassable runtime guards for high-dimensional native executors.

This module extends the general-engine preflight without duplicating solver
implementation. It is installed at package import so direct facade calls and
CLI/REST/MCP service calls share the same memory/work ceilings.
"""

from __future__ import annotations

from typing import Any, Callable

from axiomize.limits import MAX_ARRAY_ITEMS, bounded_int, enforce_result_cells
from axiomize.model_ir import ModelFamily, ModelIR

_MAX_PDE_GRID_POINTS = 4096
_MAX_CAUSAL_COVARIATES = 2048
_MAX_CAUSAL_DESIGN_CELLS = 20_000_000


def _extra_preflight(model: ModelIR, *, points: int) -> None:
    metadata = model.metadata if isinstance(model.metadata, dict) else {}
    state_count = max(1, sum(v.role == "state" for v in model.variables))

    if model.family == ModelFamily.PDE:
        cfg = metadata.get("pde", {})
        if not isinstance(cfg, dict):
            raise ValueError("metadata.pde must be an object")
        grid_points = bounded_int(
            cfg.get("grid_points", 32),
            name="pde.grid_points",
            minimum=5,
            maximum=_MAX_PDE_GRID_POINTS,
        )
        # Native PDE results are time x space for every state. The executor's
        # own grid bound alone is insufficient because a large time grid can
        # still allocate an excessive output tensor.
        enforce_result_cells(state_count, points, grid_points, name="PDE trajectory")
        profiles = cfg.get("initial_profiles", {})
        if profiles is not None and not isinstance(profiles, dict):
            raise ValueError("pde.initial_profiles must be an object")
        if isinstance(profiles, dict):
            for name, values in profiles.items():
                if isinstance(values, list) and len(values) > _MAX_PDE_GRID_POINTS:
                    raise ValueError(f"pde.initial_profiles.{name} exceeds grid hard limit")

    elif model.family == ModelFamily.CAUSAL:
        cfg = metadata.get("causal", {})
        if not isinstance(cfg, dict):
            raise ValueError("metadata.causal must be an object")
        data = cfg.get("data", {})
        if not isinstance(data, dict):
            raise ValueError("causal.data must be an object")
        n_rows: int | None = None
        for name, values in data.items():
            if not isinstance(values, list):
                raise ValueError(f"causal.data.{name} must be an array")
            if len(values) > MAX_ARRAY_ITEMS:
                raise ValueError(f"causal.data.{name} exceeds hard limit {MAX_ARRAY_ITEMS}")
            if n_rows is None:
                n_rows = len(values)
            elif len(values) != n_rows:
                raise ValueError("all causal.data arrays must have the same length")
        adjustment = cfg.get("adjustment_set", cfg.get("covariates", []))
        if not isinstance(adjustment, list):
            raise ValueError("causal adjustment_set/covariates must be an array")
        if len(adjustment) > _MAX_CAUSAL_COVARIATES:
            raise ValueError(f"causal covariates exceed hard limit {_MAX_CAUSAL_COVARIATES}")
        columns = 2 + len(adjustment)  # intercept + treatment + adjustment
        if (n_rows or 0) * columns > _MAX_CAUSAL_DESIGN_CELLS:
            raise ValueError(
                f"causal design matrix exceeds hard limit {_MAX_CAUSAL_DESIGN_CELLS} cells"
            )


def install_general_engine_guards(engine_module: Any) -> None:
    """Chain the extra guard into the already-hardened public engine once."""
    current = getattr(engine_module, "_advanced_preflight", None)
    if not callable(current):
        raise RuntimeError("general engine does not expose the expected advanced preflight hook")
    if getattr(current, "__axiomize_runtime_guard__", False):
        return

    original: Callable[..., None] = current

    def guarded(model: ModelIR, *, points: int) -> None:
        original(model, points=points)
        _extra_preflight(model, points=points)

    guarded.__axiomize_runtime_guard__ = True  # type: ignore[attr-defined]
    engine_module._advanced_preflight = guarded
