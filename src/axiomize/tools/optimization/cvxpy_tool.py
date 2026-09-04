"""CVXPY convex-optimization adapter (PHASE 3/6)."""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from axiomize.tools.base import ScientificTool


class CvxpyTool(ScientificTool):
    name: ClassVar[str] = "cvxpy"
    capabilities: ClassVar[list[str]] = ["convex_qp", "convex_lp", "constrained_lsq"]

    @classmethod
    def _probe_version(cls) -> str:
        import cvxpy  # type: ignore[import-untyped]

        return str(cvxpy.__version__)

    def validate_input(self, payload: dict[str, Any]) -> None:
        if "P" not in payload or "q" not in payload:
            raise ValueError("cvxpy: payload needs 'P' and 'q' for a QP")

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_input(payload)
        return solve_qp(payload["P"], payload["q"],
                        payload.get("G"), payload.get("h"))


def solve_qp(P: list[list[float]], q: list[float],
             G: list[list[float]] | None = None,
             h: list[float] | None = None) -> dict[str, Any]:
    """Minimize (1/2)x'Px + q'x s.t. Gx <= h.

    CLARABEL is selected explicitly because it is a CVXPY dependency and keeps
    the adapter silent when ``verbose=False``. Some OSQP versions emit a
    polishing notice to stdout even in otherwise quiet solves, which corrupts
    machine-readable CLI/MCP output that wraps this adapter.
    """
    import cvxpy as cp  # type: ignore[import-untyped]

    n = len(q)
    x = cp.Variable(n)
    objective = cp.Minimize(0.5 * cp.quad_form(x, np.array(P)) + np.array(q) @ x)
    constraints = []
    if G is not None and h is not None:
        constraints.append(np.array(G) @ x <= np.array(h))
    problem = cp.Problem(objective, constraints)
    problem.solve(solver=cp.CLARABEL, verbose=False)
    if x.value is None or problem.value is None:
        raise RuntimeError(f"cvxpy solve produced no solution (status={problem.status})")
    return {"x": [float(v) for v in np.asarray(x.value).ravel()],
            "objective": float(problem.value),
            "status": str(problem.status).lower()}
