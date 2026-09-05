"""CasADi nonlinear-optimization adapter (PHASE 3/6)."""

from __future__ import annotations

import math
from typing import Any, ClassVar

import numpy as np

from axiomize.tools.base import ScientificTool

_MAX_ABS_INITIAL = 1e12


class CasadiTool(ScientificTool):
    name: ClassVar[str] = "casadi"
    capabilities: ClassVar[list[str]] = ["nonlinear_programming", "optimal_control"]

    @classmethod
    def _probe_version(cls) -> str:
        import importlib
        casadi = importlib.import_module("casadi")
        return str(casadi.__version__)

    def validate_input(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict) or "x0" not in payload:
            raise ValueError("casadi: payload needs 'x0'")
        if payload.get("problem") != "rosenbrock":
            raise ValueError("casadi: supported problem is 'rosenbrock'")
        _validate_rosenbrock_x0(payload["x0"])

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_input(payload)
        return solve_rosenbrock(payload["x0"])


def _validate_rosenbrock_x0(x0: Any) -> list[float]:
    try:
        values = np.asarray(x0, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("casadi: x0 must be a numeric length-2 array") from exc
    if values.ndim != 1 or values.size != 2:
        raise ValueError("casadi: Rosenbrock x0 must contain exactly two values")
    if not np.all(np.isfinite(values)) or np.any(np.abs(values) > _MAX_ABS_INITIAL):
        raise ValueError(f"casadi: x0 must be finite with |value| <= {_MAX_ABS_INITIAL:g}")
    return [float(values[0]), float(values[1])]


def solve_rosenbrock(x0: Any = (-1.2, 1.0)) -> dict[str, Any]:
    """Minimize the Rosenbrock function; optimum is (1, 1)."""
    import importlib
    start = _validate_rosenbrock_x0(x0)
    ca = importlib.import_module("casadi")

    x = ca.SX.sym("x", 2)
    f = (1 - x[0]) ** 2 + 100 * (x[1] - x[0] ** 2) ** 2
    solver = ca.nlpsol(
        "solver",
        "ipopt",
        {"x": x, "f": f},
        {
            "ipopt.print_level": 0,
            "ipopt.sb": "yes",
            "ipopt.max_iter": 10_000,
            "print_time": 0,
        },
    )
    result = solver(x0=start, lbx=[-1e12, -1e12], ubx=[1e12, 1e12])
    stats = solver.stats()
    values = [float(v) for v in result["x"].full().ravel()]
    objective = float(result["f"])
    if len(values) != 2 or not all(math.isfinite(v) for v in values) or not math.isfinite(objective):
        raise RuntimeError("casadi returned a non-finite or malformed result")
    return {
        "x": values,
        "objective": objective,
        "success": bool(stats.get("success", False)),
        "initial_x": start,
        "return_status": str(stats.get("return_status", "unknown")),
    }
