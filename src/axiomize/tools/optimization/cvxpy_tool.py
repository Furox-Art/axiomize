"""CVXPY convex-optimization adapter (PHASE 3/6)."""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from axiomize.limits import MAX_ARRAY_ITEMS, enforce_result_cells
from axiomize.tools.base import ScientificTool

MAX_QP_DIMENSION = 512
MAX_QP_CONSTRAINTS = 20_000
MAX_CLARABEL_ITERATIONS = 10_000


class CvxpyTool(ScientificTool):
    name: ClassVar[str] = "cvxpy"
    capabilities: ClassVar[list[str]] = ["convex_qp", "convex_lp", "constrained_lsq"]

    @classmethod
    def _probe_version(cls) -> str:
        import cvxpy  # type: ignore[import-untyped]
        return str(cvxpy.__version__)

    def validate_input(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict) or "P" not in payload or "q" not in payload:
            raise ValueError("cvxpy: payload needs 'P' and 'q' for a QP")
        _validated_qp(payload["P"], payload["q"], payload.get("G"), payload.get("h"))

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_input(payload)
        return solve_qp(payload["P"], payload["q"], payload.get("G"), payload.get("h"))


def _validated_qp(P: Any, q: Any, G: Any = None, h: Any = None):
    try:
        q_arr = np.asarray(q, dtype=float)
        P_arr = np.asarray(P, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("cvxpy: P and q must be numeric arrays") from exc
    if q_arr.ndim != 1 or q_arr.size == 0 or q_arr.size > MAX_QP_DIMENSION:
        raise ValueError(f"cvxpy: q must be a 1D array with 1..{MAX_QP_DIMENSION} entries")
    n = int(q_arr.size)
    if P_arr.shape != (n, n):
        raise ValueError(f"cvxpy: P must have shape ({n}, {n})")
    if not np.all(np.isfinite(P_arr)) or not np.all(np.isfinite(q_arr)):
        raise ValueError("cvxpy: P and q must contain only finite values")
    if not np.allclose(P_arr, P_arr.T, rtol=1e-10, atol=1e-12):
        raise ValueError("cvxpy: P must be symmetric")
    # Validate convexity before invoking CVXPY. The dimension is hard-capped so
    # this eigenvalue check cannot become an unbounded cubic-time operation.
    eigen_min = float(np.min(np.linalg.eigvalsh((P_arr + P_arr.T) / 2.0)))
    scale = max(1.0, float(np.linalg.norm(P_arr, ord=2)))
    if eigen_min < -1e-10 * scale:
        raise ValueError(f"cvxpy: P must be positive semidefinite; min eigenvalue={eigen_min:g}")

    if (G is None) != (h is None):
        raise ValueError("cvxpy: G and h must be supplied together")
    if G is None:
        return P_arr, q_arr, None, None
    try:
        G_arr = np.asarray(G, dtype=float)
        h_arr = np.asarray(h, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("cvxpy: G and h must be numeric arrays") from exc
    if G_arr.ndim != 2 or G_arr.shape[1] != n:
        raise ValueError(f"cvxpy: G must be a 2D matrix with {n} columns")
    rows = int(G_arr.shape[0])
    if rows < 1 or rows > MAX_QP_CONSTRAINTS or rows > MAX_ARRAY_ITEMS:
        raise ValueError(f"cvxpy: G row count must be in 1..{MAX_QP_CONSTRAINTS}")
    if h_arr.ndim != 1 or h_arr.size != rows:
        raise ValueError("cvxpy: h must be a 1D array with one value per row of G")
    enforce_result_cells(rows, n, name="QP constraint matrix")
    if not np.all(np.isfinite(G_arr)) or not np.all(np.isfinite(h_arr)):
        raise ValueError("cvxpy: G and h must contain only finite values")
    return P_arr, q_arr, G_arr, h_arr


def solve_qp(P: list[list[float]], q: list[float],
             G: list[list[float]] | None = None,
             h: list[float] | None = None) -> dict[str, Any]:
    """Minimize (1/2)x'Px + q'x s.t. Gx <= h."""
    import cvxpy as cp  # type: ignore[import-untyped]

    P_arr, q_arr, G_arr, h_arr = _validated_qp(P, q, G, h)
    n = int(q_arr.size)
    x = cp.Variable(n)
    objective = cp.Minimize(0.5 * cp.quad_form(x, P_arr) + q_arr @ x)
    constraints = []
    if G_arr is not None and h_arr is not None:
        constraints.append(G_arr @ x <= h_arr)
    problem = cp.Problem(objective, constraints)
    try:
        problem.solve(
            solver=cp.CLARABEL,
            verbose=False,
            max_iter=MAX_CLARABEL_ITERATIONS,
        )
    except cp.error.SolverError as exc:
        raise RuntimeError(f"cvxpy solver failed: {exc}") from exc
    status = str(problem.status).lower()
    accepted = {str(cp.OPTIMAL).lower(), str(cp.OPTIMAL_INACCURATE).lower()}
    if status not in accepted or x.value is None or problem.value is None:
        raise RuntimeError(f"cvxpy solve produced no accepted solution (status={problem.status})")
    values = np.asarray(x.value, dtype=float).ravel()
    objective_value = float(problem.value)
    if values.size != n or not np.all(np.isfinite(values)) or not np.isfinite(objective_value):
        raise RuntimeError("cvxpy returned non-finite or malformed solution values")
    return {
        "x": [float(v) for v in values],
        "objective": objective_value,
        "status": status,
        "solver": "CLARABEL",
        "max_iterations": MAX_CLARABEL_ITERATIONS,
    }
