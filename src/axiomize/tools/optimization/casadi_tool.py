"""CasADi nonlinear-optimization adapter (PHASE 3/6)."""

from __future__ import annotations

from typing import Any, ClassVar

from axiomize.tools.base import ScientificTool


class CasadiTool(ScientificTool):
    name: ClassVar[str] = "casadi"
    capabilities: ClassVar[list[str]] = ["nonlinear_programming", "optimal_control"]

    @classmethod
    def _probe_version(cls) -> str:
        import importlib

        # importlib (not a static import): casadi ships a .pyi with a
        # duplicate-parameter syntax error that breaks stub parsing.
        casadi = importlib.import_module("casadi")

        return str(casadi.__version__)

    def validate_input(self, payload: dict[str, Any]) -> None:
        if "x0" not in payload:
            raise ValueError("casadi: payload needs 'x0'")

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_input(payload)
        if payload.get("problem") == "rosenbrock":
            return solve_rosenbrock()
        raise ValueError("casadi: unknown problem; use solve_rosenbrock or the SX API")


def solve_rosenbrock() -> dict[str, Any]:
    """Minimize the Rosenbrock function from (-1.2, 1); optimum is (1, 1)."""
    import importlib

    ca = importlib.import_module("casadi")

    x = ca.SX.sym("x", 2)
    f = (1 - x[0]) ** 2 + 100 * (x[1] - x[0] ** 2) ** 2
    # `ipopt.print_level=0` suppresses iteration output; `ipopt.sb=yes`
    # additionally suppresses the IPOPT startup banner. Keeping numerical
    # backends silent is part of the CLI contract because commands such as
    # `axiomize benchmark` emit machine-readable JSON on stdout.
    solver = ca.nlpsol(
        "solver",
        "ipopt",
        {"x": x, "f": f},
        {"ipopt.print_level": 0, "ipopt.sb": "yes", "print_time": 0},
    )
    result = solver(x0=[-1.2, 1.0], lbx=[-10, -10], ubx=[10, 10])
    stats = solver.stats()
    return {"x": [float(v) for v in result["x"].full().ravel()],
            "objective": float(result["f"]),
            "success": bool(stats.get("success", False))}
