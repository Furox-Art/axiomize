"""Second-pass regression tests for direct runtime/tool trust boundaries."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from axiomize.bayesian.mh import metropolis_hastings, normal_mean_posterior
from axiomize.limits import MAX_BAYES_DRAWS, bounded_int
from axiomize.pde.diffusion import MAX_FTCS_STEPS, heat_ftcs
from axiomize.safe_expression import auto_symbol_map, sympy_expression
from axiomize.tools.logic.z3_tool import check_constraints
from axiomize.tools.numerical.scipy_tool import final_size_numeric, solve_sir
from axiomize.tools.optimization.casadi_tool import CasadiTool
from axiomize.tools.optimization.cvxpy_tool import CvxpyTool
from axiomize.tools.pde.fenics_tool import FEniCSAdapter
from axiomize.tools.statistics.statsmodels_tool import StatsmodelsTool


ROOT = Path(__file__).resolve().parents[1]


def _load_benchmark_runner():
    path = ROOT / "skills" / "axiomize" / "tools" / "benchmark_runner.py"
    spec = importlib.util.spec_from_file_location("axiomize_test_benchmark_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("value", [1.5, "1.5", True, float("inf"), float("nan")])
def test_bounded_int_rejects_inexact_or_boolean_values(value) -> None:
    with pytest.raises(ValueError):
        bounded_int(value, name="count", minimum=0, maximum=10)


def test_bounded_int_accepts_exact_integer_representations() -> None:
    assert bounded_int(3, name="count", maximum=10) == 3
    assert bounded_int(3.0, name="count", maximum=10) == 3
    assert bounded_int("+3", name="count", maximum=10) == 3


def test_ast_to_sympy_preserves_piecewise_and_relations() -> None:
    import sympy as sp

    x = sp.Symbol("x", real=True)
    expr = sympy_expression("Piecewise((x**2, x >= 0), (-x, True))", {"x": x})
    assert float(expr.subs(x, 2)) == 4.0
    assert float(expr.subs(x, -2)) == 2.0


def test_auto_symbol_map_still_rejects_escape_syntax() -> None:
    with pytest.raises(ValueError):
        auto_symbol_map("__import__('os').system('echo nope')")


def test_metropolis_hastings_rejects_oversized_chain_before_allocation() -> None:
    with pytest.raises(ValueError):
        metropolis_hastings(lambda x: -float(np.sum(x * x)), np.array([0.0]), n_samples=MAX_BAYES_DRAWS + 1)


def test_metropolis_hastings_rejects_invalid_burn_and_nonfinite_initial_density() -> None:
    with pytest.raises(ValueError):
        metropolis_hastings(lambda x: -float(np.sum(x * x)), np.array([0.0]), n_samples=10, burn=10)
    with pytest.raises(ValueError):
        metropolis_hastings(lambda _x: float("nan"), np.array([0.0]), n_samples=10, burn=1)


def test_normal_mean_posterior_validates_scale() -> None:
    with pytest.raises(ValueError):
        normal_mean_posterior(np.array([1.0, 2.0]), sigma=0.0)
    with pytest.raises(ValueError):
        normal_mean_posterior(np.array([1.0, 2.0]), sigma=1.0, prior_std=-1.0)


def test_z3_direct_constraints_reject_pathological_power_and_bounds() -> None:
    with pytest.raises(ValueError):
        check_constraints(["x**33 >= 0"], {"x": (-1.0, 1.0)})
    with pytest.raises(ValueError):
        check_constraints(["x >= 0"], {"x": (1.0, -1.0)})


def test_cvxpy_validation_rejects_nonconvex_or_malformed_qp_without_solving() -> None:
    tool = CvxpyTool()
    with pytest.raises(ValueError, match="positive semidefinite"):
        tool.validate_input({"P": [[1.0, 0.0], [0.0, -1.0]], "q": [0.0, 0.0]})
    with pytest.raises(ValueError, match="shape"):
        tool.validate_input({"P": [[1.0]], "q": [0.0, 0.0]})
    with pytest.raises(ValueError):
        tool.validate_input({"P": [[1.0]], "q": [float("nan")]})


def test_casadi_validation_requires_supported_problem_and_honors_x0_shape() -> None:
    tool = CasadiTool()
    with pytest.raises(ValueError):
        tool.validate_input({"problem": "rosenbrock", "x0": [1.0]})
    with pytest.raises(ValueError):
        tool.validate_input({"problem": "other", "x0": [0.0, 0.0]})
    tool.validate_input({"problem": "rosenbrock", "x0": [-1.2, 1.0]})


def test_statsmodels_validation_rejects_mismatch_nonfinite_and_underdetermined() -> None:
    tool = StatsmodelsTool()
    with pytest.raises(ValueError):
        tool.validate_input({"x": [1.0, 2.0], "y": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError):
        tool.validate_input({"x": [1.0, float("nan")], "y": [1.0, 2.0]})
    with pytest.raises(ValueError):
        tool.validate_input({"x": [[1.0, 2.0], [2.0, 3.0]], "y": [1.0, 2.0]})


def test_fenics_adapter_never_advertises_unimplemented_executor() -> None:
    meta = FEniCSAdapter.availability()
    assert meta.available is False
    assert "not implemented" in meta.reason or "unavailable" in meta.reason


def test_scipy_direct_solver_rejects_invalid_physical_parameters() -> None:
    with pytest.raises(ValueError):
        solve_sir(-0.1, 0.1, 1.0, 100.0)
    with pytest.raises(ValueError):
        solve_sir(0.1, -0.1, 1.0, 100.0)
    with pytest.raises(ValueError):
        final_size_numeric(0.1, 0.0)


def test_ftcs_direct_solver_enforces_grid_step_and_cfl_bounds() -> None:
    with pytest.raises(ValueError):
        heat_ftcs(alpha=1.0, length=1.0, nx=2, dt=1e-4, t_end=1.0)
    with pytest.raises(ValueError, match="step count"):
        heat_ftcs(alpha=0.0, length=1.0, nx=10, dt=1e-9, t_end=(MAX_FTCS_STEPS + 1) * 1e-9)
    with pytest.raises(ValueError, match="unstable"):
        heat_ftcs(alpha=1.0, length=1.0, nx=10, dt=1.0, t_end=1.0)


def test_benchmark_custom_regex_text_is_literal_not_executed() -> None:
    runner = _load_benchmark_runner()
    case = {
        "must_contain": ["(a+)+$"],
        "expected_archetype": "",
        "min_lenses_built": 0,
        "must_reject_at_least_one": False,
    }
    checks, _ = runner.grade("a" * 10_000, case)
    first = next(iter(checks.values()))
    assert first is False
