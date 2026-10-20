"""Round-2 coverage hardening: numerical/symbolic tool adapters and small engines."""

from __future__ import annotations

import importlib
import math
import sys
from types import SimpleNamespace

import control
import numpy as np
import pytest
import sympy

from axiomize.control import pid as pid_engine
from axiomize.pde import diffusion
from axiomize.tools.base import ScientificTool
from axiomize.tools.numerical import scipy_tool
from axiomize.tools.optimization import casadi_tool, cvxpy_tool
from axiomize.tools.symbolic import sympy_tool

# ---------------------------------------------------------------------------
# CasADi adapter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("payload", [None, [], {}, {"problem": "rosenbrock"}])
def test_casadi_validate_input_requires_x0(payload) -> None:
    with pytest.raises(ValueError, match="needs 'x0'"):
        casadi_tool.CasadiTool().validate_input(payload)


def test_casadi_execute_runs_the_real_rosenbrock_problem() -> None:
    result = casadi_tool.CasadiTool().execute(
        {"problem": "rosenbrock", "x0": [-1.2, 1.0]}
    )
    assert result["success"] is True
    assert result["x"] == pytest.approx([1.0, 1.0], abs=1e-4)
    assert result["objective"] == pytest.approx(0.0, abs=1e-8)
    assert result["initial_x"] == [-1.2, 1.0]


def test_casadi_x0_conversion_failure_is_a_value_error() -> None:
    with pytest.raises(ValueError, match="numeric length-2 array"):
        casadi_tool._validate_rosenbrock_x0(["not", "numeric"])


@pytest.mark.parametrize("x0", [[1e13, 0.0], [float("inf"), 0.0], [0.0, float("nan")]])
def test_casadi_x0_rejects_non_finite_or_extreme_values(x0) -> None:
    with pytest.raises(ValueError, match="finite with"):
        casadi_tool._validate_rosenbrock_x0(x0)


def test_casadi_rejects_non_finite_solver_output(monkeypatch) -> None:
    real_casadi = importlib.import_module("casadi")

    class _Solver:
        def __call__(self, **kwargs):
            return {"x": real_casadi.DM([1.0, 1.0]), "f": float("nan")}

        def stats(self):
            return {"success": True, "return_status": "fake"}

    wrapper = SimpleNamespace(SX=real_casadi.SX, DM=real_casadi.DM, nlpsol=lambda *a, **k: _Solver())
    real_import_module = importlib.import_module
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: wrapper if name == "casadi" else real_import_module(name),
    )
    with pytest.raises(RuntimeError, match="non-finite or malformed result"):
        casadi_tool.solve_rosenbrock([-1.2, 1.0])


# ---------------------------------------------------------------------------
# CVXPY adapter
# ---------------------------------------------------------------------------


def test_cvxpy_rejects_zero_row_constraint_matrix() -> None:
    with pytest.raises(ValueError, match="G row count must be in 1"):
        cvxpy_tool._validated_qp(
            [[1.0]], [1.0], np.empty((0, 1)), np.empty((0,))
        )


def test_cvxpy_rejects_non_finite_solution_values(monkeypatch) -> None:
    class _Variable:
        __array_priority__ = 1000

        def __init__(self, n):
            self.value = np.full(n, np.nan)

        def __rmatmul__(self, other):
            return 0.0

        def __array_ufunc__(self, *args, **kwargs):
            return 0.0

    class _Problem:
        def __init__(self, objective, constraints):
            self.value = 1.0
            self.status = "optimal"

        def solve(self, **kwargs):
            return None

    fake = SimpleNamespace(
        Variable=_Variable,
        Minimize=lambda expression: expression,
        quad_form=lambda variable, matrix: 0.0,
        Problem=_Problem,
        CLARABEL="CLARABEL",
        OPTIMAL="optimal",
        OPTIMAL_INACCURATE="optimal_inaccurate",
        error=SimpleNamespace(SolverError=RuntimeError),
    )
    monkeypatch.setitem(sys.modules, "cvxpy", fake)
    with pytest.raises(RuntimeError, match="non-finite or malformed solution"):
        cvxpy_tool.solve_qp([[1.0]], [1.0])


# ---------------------------------------------------------------------------
# SciPy adapter
# ---------------------------------------------------------------------------


def test_scipy_solver_rejects_malformed_ivp_output(monkeypatch) -> None:
    def _fake_solve_ivp(*args, **kwargs):
        return SimpleNamespace(y=np.zeros((2, 3)), t=np.zeros(3), success=False)

    monkeypatch.setattr("scipy.integrate.solve_ivp", _fake_solve_ivp)
    result = scipy_tool.solve_sir(0.3, 0.1, 10.0, 1000.0)
    assert result.success is False
    assert math.isnan(result.final_size)
    assert result.max_residual == math.inf


def test_scipy_solver_marks_single_point_output_with_infinite_residual(monkeypatch) -> None:
    def _fake_solve_ivp(*args, **kwargs):
        return SimpleNamespace(
            y=np.array([[900.0], [100.0], [0.0]]), t=np.array([0.0]), success=True
        )

    monkeypatch.setattr("scipy.integrate.solve_ivp", _fake_solve_ivp)
    result = scipy_tool.solve_sir(0.3, 0.1, 10.0, 1000.0)
    assert result.max_residual == math.inf
    assert result.success is False
    assert result.final_size == pytest.approx(0.0)


def test_scipy_tool_metadata_reports_the_real_backend() -> None:
    meta = scipy_tool.SciPyTool().metadata()
    assert meta.available is True
    assert meta.name == "scipy"
    assert meta.version
    assert "ode_solve" in meta.capabilities


# ---------------------------------------------------------------------------
# SymPy adapter
# ---------------------------------------------------------------------------


def test_sympy_symbol_namespace_is_hard_limited(monkeypatch) -> None:
    monkeypatch.setattr(sympy_tool, "MAX_MODEL_VARIABLES", 1)
    monkeypatch.setattr(sympy_tool, "MAX_MODEL_PARAMETERS", 1)
    with pytest.raises(ValueError, match="namespace exceeds hard symbol limit"):
        sympy_tool._symbols_for("x + y + z")


def test_sympy_tool_metadata_reports_the_real_backend() -> None:
    meta = sympy_tool.SymPyTool().metadata()
    assert meta.available is True
    assert meta.name == "sympy"
    assert meta.version
    assert "simplify" in meta.capabilities


def test_sympy_final_size_rejects_out_of_range_root(monkeypatch) -> None:
    monkeypatch.setattr(sympy, "nsolve", lambda *args, **kwargs: 1.5)
    with pytest.raises(RuntimeError, match="outside \\[0, 1\\]"):
        sympy_tool.final_size_symbolic(2.0)


def test_sympy_singularity_count_is_hard_limited(monkeypatch) -> None:
    monkeypatch.setattr(sympy_tool, "MAX_MODEL_EQUATIONS", 1)
    monkeypatch.setattr(sympy, "solve", lambda *args, **kwargs: [1, 2])
    with pytest.raises(ValueError, match="result exceeds hard result count"):
        sympy_tool.find_singularities("1/((x - 1)*(x - 2))", "x")


# ---------------------------------------------------------------------------
# FTCS diffusion reference solver
# ---------------------------------------------------------------------------


def test_diffusion_finite_rejects_non_numeric_values() -> None:
    with pytest.raises(ValueError, match="alpha must be numeric"):
        diffusion._finite("not-a-number", name="alpha")


def test_diffusion_rejects_negative_step_count_from_rounding(monkeypatch) -> None:
    monkeypatch.setattr(diffusion, "round", lambda value: -1.0, raising=False)
    with pytest.raises(ValueError, match="step count must be in 0"):
        diffusion.heat_ftcs(0.0, 1.0, 3, 0.1, 0.2)


def test_diffusion_rejects_non_finite_error_metric(monkeypatch) -> None:
    monkeypatch.setattr(diffusion.np, "mean", lambda *args, **kwargs: math.inf)
    with pytest.raises(RuntimeError, match="non-finite error metric"):
        diffusion.heat_ftcs(0.0, 1.0, 5, 0.01, 0.1)


# ---------------------------------------------------------------------------
# PID control engine
# ---------------------------------------------------------------------------


def test_pid_rejects_malformed_step_response(monkeypatch) -> None:
    monkeypatch.setattr(control, "step_response", lambda loop, t: SimpleNamespace(y=np.array([1.0])))
    with pytest.raises(RuntimeError, match="malformed or non-finite"):
        pid_engine.closed_loop_step(1.0, 0.0, 0.0, [1.0], [1.0, 1.0], t_end=1.0, n=5)


# ---------------------------------------------------------------------------
# Scientific tool base contract
# ---------------------------------------------------------------------------


def test_base_probe_version_is_a_not_implemented_contract() -> None:
    class _BareTool(ScientificTool):
        name = "bare"

        def validate_input(self, payload):
            return None

        def execute(self, payload):
            return {}

    meta = _BareTool.availability()
    assert meta.available is False
    assert meta.name == "bare"
    assert meta.reason == ""
