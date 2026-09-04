"""Machine-readable CLI output must not be polluted by scientific backends."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))


def test_optimization_backends_are_silent_on_stdout(capfd) -> None:
    from axiomize.tools.optimization.casadi_tool import solve_rosenbrock
    from axiomize.tools.optimization.cvxpy_tool import solve_qp

    qp = solve_qp([[2.0, 0.0], [0.0, 2.0]], [-2.0, -5.0])
    nlp = solve_rosenbrock()

    captured = capfd.readouterr()
    assert captured.out == ""
    assert qp["status"] == "optimal"
    assert nlp["success"] is True
