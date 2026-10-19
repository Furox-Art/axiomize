"""Real convex QP solutions plus mandatory pre-solver physical guards."""
from __future__ import annotations

import math

import pytest

from axiomize.tools.optimization import cvxpy_tool as qp


@pytest.mark.parametrize("p,q,fragment", [
    ([[1]], [1, 2], "P must have shape"),
    ([[1, 2], [2, 1]], [0, 0], "positive semidefinite"),
    ([[1, 2], [0, 1]], [0, 0], "symmetric"),
    ([[float("nan")]], [1], "finite"),
    ([[1]], [float("inf")], "finite"),
    ([["not numeric"]], [1], "numeric arrays"),
    ([], [], "q must be"),
    ([[1]], [[0]], "q must be"),
    ([[1]], [1] * 513, "q must be"),
])
def test_qp_refuses_malformed_nonconvex_or_unbounded_objective(p, q, fragment):
    with pytest.raises(ValueError, match=fragment):
        qp._validated_qp(p, q)


@pytest.mark.parametrize("g,h,fragment", [
    ([[1]], None, "together"),
    (None, [1], "together"),
    ([[1, 2]], [1], "2D matrix"),
    ([1], [1], "2D matrix"),
    ([], [], "2D matrix"),
    ([[1]], [[1]], "1D array"),
    ([[1]], [float("nan")], "finite"),
    ([["invalid"]], [1], "numeric arrays"),
])
def test_qp_constraints_must_be_coupled_finite_and_shape_safe(g, h, fragment):
    with pytest.raises(ValueError, match=fragment):
        qp._validated_qp([[2]], [-4], g, h)


def test_native_unconstrained_qp_recovers_known_global_minimum():
    result = qp.solve_qp([[2]], [-4])
    assert result["status"] in {"optimal", "optimal_inaccurate"}
    assert result["x"][0] == pytest.approx(2.0, abs=1e-5)
    assert result["objective"] == pytest.approx(-4.0, abs=1e-5)
    assert result["solver"] == "CLARABEL"
    assert result["max_iterations"] <= 10000


def test_real_constraint_changes_optimum_in_correct_direction():
    result = qp.solve_qp([[2]], [-4], [[1]], [1])
    assert result["x"][0] == pytest.approx(1.0, abs=1e-5)
    assert result["objective"] == pytest.approx(-3.0, abs=1e-5)


def test_native_infeasible_qp_is_not_reported_as_optimal():
    with pytest.raises(RuntimeError, match="no accepted solution"):
        qp.solve_qp([[2]], [-4], [[1], [-1]], [0, -1])


def test_adapter_executes_same_real_native_solver_and_checks_bounds():
    tool = qp.CvxpyTool()
    tool.validate_input({"P": [[2]], "q": [-4], "G": [[1]], "h": [1]})
    actual = tool.execute({"P": [[2]], "q": [-4], "G": [[1]], "h": [1]})
    assert math.isfinite(actual["objective"])
    assert actual["x"][0] == pytest.approx(1.0, abs=1e-5)
    assert tool._probe_version()


@pytest.mark.parametrize("payload", [None, {}, {"P": [[1]]}, {"q": [1]}, []])
def test_adapter_refuses_missing_qp_input(payload):
    with pytest.raises(ValueError, match="payload needs"):
        qp.CvxpyTool().validate_input(payload)


def test_solver_error_is_propagated_as_typed_runtime_failure(monkeypatch):
    import cvxpy as cp

    def raise_solver_error(*args, **kwargs):
        raise cp.error.SolverError("solver interface refused input")

    monkeypatch.setattr(cp.Problem, "solve", raise_solver_error)
    with pytest.raises(RuntimeError, match="cvxpy solver failed"):
        qp.solve_qp([[2]], [-4])


def test_unreported_solver_status_cannot_claim_a_solution(monkeypatch):
    import cvxpy as cp

    monkeypatch.setattr(cp.Problem, "solve", lambda *args, **kwargs: None)
    with pytest.raises(RuntimeError, match="no accepted solution"):
        qp.solve_qp([[2]], [-4])
