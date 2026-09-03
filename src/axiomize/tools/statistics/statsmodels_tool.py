"""statsmodels statistics adapter (PHASE 3)."""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from axiomize.tools.base import ScientificTool


class StatsmodelsTool(ScientificTool):
    name: ClassVar[str] = "statsmodels"
    capabilities: ClassVar[list[str]] = ["ols", "regression_diagnostics"]

    @classmethod
    def _probe_version(cls) -> str:
        import statsmodels  # type: ignore[import-untyped]

        return str(statsmodels.__version__)

    def validate_input(self, payload: dict[str, Any]) -> None:
        if "x" not in payload or "y" not in payload:
            raise ValueError("statsmodels: payload needs 'x' and 'y'")

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_input(payload)
        return ols_fit(payload["x"], payload["y"])


def ols_fit(x: Any, y: Any) -> dict[str, Any]:
    """Ordinary least squares with intercept: y = b0 + b1*x."""
    import statsmodels.api as sm  # type: ignore[import-untyped]

    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    design = sm.add_constant(x_arr)
    result = sm.OLS(y_arr, design).fit()
    return {"params": [float(v) for v in result.params],
            "stderr": [float(v) for v in result.bse],
            "rsquared": float(result.rsquared),
            "pvalues": [float(v) for v in result.pvalues]}
