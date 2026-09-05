"""statsmodels statistics adapter (PHASE 3)."""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from axiomize.limits import MAX_ARRAY_ITEMS, enforce_result_cells
from axiomize.tools.base import ScientificTool

_MAX_PREDICTORS = 512


class StatsmodelsTool(ScientificTool):
    name: ClassVar[str] = "statsmodels"
    capabilities: ClassVar[list[str]] = ["ols", "regression_diagnostics"]

    @classmethod
    def _probe_version(cls) -> str:
        import statsmodels  # type: ignore[import-untyped]
        return str(statsmodels.__version__)

    def validate_input(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict) or "x" not in payload or "y" not in payload:
            raise ValueError("statsmodels: payload needs 'x' and 'y'")
        _validated_xy(payload["x"], payload["y"])

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_input(payload)
        return ols_fit(payload["x"], payload["y"])


def _validated_xy(x: Any, y: Any) -> tuple[np.ndarray, np.ndarray]:
    try:
        x_arr = np.asarray(x, dtype=float)
        y_arr = np.asarray(y, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("statsmodels: x and y must be numeric arrays") from exc
    if y_arr.ndim != 1 or y_arr.size < 2 or y_arr.size > MAX_ARRAY_ITEMS:
        raise ValueError(f"statsmodels: y must be 1D with 2..{MAX_ARRAY_ITEMS} observations")
    if x_arr.ndim == 1:
        if x_arr.size != y_arr.size:
            raise ValueError("statsmodels: x and y must have the same observation count")
        x_arr = x_arr.reshape(-1, 1)
    elif x_arr.ndim == 2:
        if x_arr.shape[0] != y_arr.size:
            raise ValueError("statsmodels: x rows must match y length")
    else:
        raise ValueError("statsmodels: x must be a 1D predictor or 2D design matrix")
    if x_arr.shape[1] < 1 or x_arr.shape[1] > _MAX_PREDICTORS:
        raise ValueError(f"statsmodels: predictor count must be in 1..{_MAX_PREDICTORS}")
    enforce_result_cells(int(x_arr.shape[0]), int(x_arr.shape[1] + 1), name="OLS design matrix")
    if not np.all(np.isfinite(x_arr)) or not np.all(np.isfinite(y_arr)):
        raise ValueError("statsmodels: x and y must contain only finite values")
    if y_arr.size <= x_arr.shape[1]:
        raise ValueError("statsmodels: observations must exceed predictor count")
    return x_arr, y_arr


def ols_fit(x: Any, y: Any) -> dict[str, Any]:
    """Ordinary least squares with an intercept for one or more predictors."""
    import statsmodels.api as sm  # type: ignore[import-untyped]

    x_arr, y_arr = _validated_xy(x, y)
    design = sm.add_constant(x_arr, has_constant="add")
    result = sm.OLS(y_arr, design, missing="raise").fit()
    params = np.asarray(result.params, dtype=float)
    stderr = np.asarray(result.bse, dtype=float)
    pvalues = np.asarray(result.pvalues, dtype=float)
    rsquared = float(result.rsquared)
    # Some statistically degenerate cases legitimately produce non-finite
    # standard errors/p-values. Preserve them as explicit strings instead of
    # emitting invalid JSON floats.
    def safe(value: float):
        return float(value) if np.isfinite(value) else "UNDEFINED"
    return {
        "params": [safe(v) for v in params],
        "stderr": [safe(v) for v in stderr],
        "rsquared": safe(rsquared),
        "pvalues": [safe(v) for v in pvalues],
        "n_obs": int(y_arr.size),
        "n_predictors": int(x_arr.shape[1]),
    }
