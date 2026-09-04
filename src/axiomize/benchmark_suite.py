"""Package-native scientific benchmark suite used by ``axiomize benchmark``.

Unlike the repository test file, this module is shipped in wheels and does not
require pytest or a source checkout. Each case exercises real public services or
numerical implementations and returns an explicit PASS/FAIL record.
"""
from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

import numpy as np


def _case_01() -> None:
    from axiomize.tools.numerical.scipy_tool import final_size_numeric, solve_sir
    result = solve_sir(0.3, 0.1, 10, 1_000_000, days=180)
    assert result.success and result.max_conservation_error < 1e-3
    assert abs(result.final_size - final_size_numeric(0.3, 0.1)) < 5e-4


def _case_02() -> None:
    from axiomize.tools.numerical.scipy_tool import solve_sir
    result = solve_sir(0.35, 0.12, 20, 10_000, days=120)
    assert result.final_size > 0.5
    assert float(np.max(result.y[1])) > 20


def _case_03() -> None:
    from axiomize.tools.optimization.casadi_tool import solve_rosenbrock
    from axiomize.tools.optimization.cvxpy_tool import solve_qp
    qp = solve_qp([[2.0, 0.0], [0.0, 2.0]], [-2.0, -5.0])
    assert qp["status"] == "optimal"
    assert solve_rosenbrock()["success"] is True


def _case_04() -> None:
    from axiomize.tools.statistics.statsmodels_tool import ols_fit
    rng = np.random.default_rng(5)
    x = np.linspace(0, 10, 50)
    y = 3.0 * x + 2.0 + rng.normal(0, 0.5, size=50)
    result = ols_fit(x, y)
    assert abs(result["params"][1] - 3.0) < 0.15


def _case_05() -> None:
    from axiomize.bayesian.mh import normal_mean_posterior
    rng = np.random.default_rng(6)
    y = rng.normal(5.0, 1.0, size=50)
    result = normal_mean_posterior(y, sigma=1.0, n_samples=4000, burn=1000, seed=0)
    lo, hi = result["ci95"]
    assert lo < 5.0 < hi


def _case_06() -> None:
    from axiomize.network.epidemic import build_er_graph, heterogeneity_factor, sir_on_network
    graph = build_er_graph(200, 0.03, seed=0)
    assert heterogeneity_factor(graph) >= 1.0
    result = sir_on_network(graph, beta=0.15, gamma=0.1, I0=3, seed=0)
    assert 0.0 <= result["attack_rate"] <= 1.0


def _case_07() -> None:
    from axiomize.control.pid import closed_loop_step
    result = closed_loop_step(kp=2.0, ki=1.0, kd=0.5, plant_num=[1.0], plant_den=[1.0, 1.0, 0.0])
    assert result["settled"] is True


def _case_08() -> None:
    from axiomize.tools.validate import gillespie_sir_once
    rng = np.random.default_rng(9)
    runs = [gillespie_sir_once(0.3, 0.1, 1, 5000, rng=rng) for _ in range(400)]
    observed = sum(item["extinct_early"] for item in runs) / len(runs)
    expected = 1 / (1 + 3.0)
    assert abs(observed - expected) < 0.08


def _case_09() -> None:
    from axiomize.pde.diffusion import heat_ftcs
    coarse = heat_ftcs(alpha=0.1, length=1.0, nx=25, dt=0.0008, t_end=0.05)
    fine = heat_ftcs(alpha=0.1, length=1.0, nx=50, dt=0.0002, t_end=0.05)
    assert fine["l2_error"] < coarse["l2_error"]


def _case_10() -> None:
    from axiomize.fitting.estimator import compare_fits, fit_logistic_curve, fit_sir_curve
    from axiomize.tools.numerical.scipy_tool import solve_sir
    t = np.linspace(0, 60, 25)
    sol = solve_sir(0.35, 0.12, 20, 10_000)
    y = np.interp(t, np.linspace(0, 60, 2000), sol.y[1])
    sir = fit_sir_curve(t, y, N=10_000, I0=20.0)
    logistic = fit_logistic_curve(t, y)
    ranking = compare_fits({"sir": sir, "logistic": logistic})
    assert ranking["best"] == "sir" and logistic.bic > sir.bic


def _case_11() -> None:
    from axiomize.routing.router import classify
    from axiomize.validation.status import ValidationStatus
    result = classify({"signals": []})
    assert result.problem_type == "unknown"
    assert result.status == ValidationStatus.INCONCLUSIVE


def _case_12() -> None:
    from axiomize.application.services import compare_service
    from axiomize.tools.numerical.scipy_tool import solve_sir
    t = np.linspace(0, 60, 25)
    sol = solve_sir(0.35, 0.12, 20, 10_000)
    y = np.interp(t, np.linspace(0, 60, 2000), sol.y[1])
    result = compare_service({"t": t.tolist(), "y": y.tolist(), "N": 10_000, "I0": 20.0})
    assert len(result["ranking"]) >= 2
    assert result["best"] in result["ranking"] and "BIC" in result["reason"]


_CASES: list[tuple[str, Callable[[], None]]] = [
    ("deterministic_model", _case_01),
    ("nonlinear_ode_outbreak", _case_02),
    ("optimization", _case_03),
    ("regression", _case_04),
    ("bayesian_fitting", _case_05),
    ("network_model", _case_06),
    ("control_problem", _case_07),
    ("stochastic_model", _case_08),
    ("pde_convergence", _case_09),
    ("wrong_model_rejected", _case_10),
    ("missing_information_explicit", _case_11),
    ("multiple_models_compared", _case_12),
]


def run_suite() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for name, case in _CASES:
        try:
            case()
        except Exception as exc:  # benchmark boundary: report, do not hide
            results.append({
                "name": name,
                "status": "FAIL",
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": "".join(traceback.format_exception_only(type(exc), exc)).strip(),
            })
        else:
            results.append({"name": name, "status": "PASS"})
    passed = sum(item["status"] == "PASS" for item in results)
    return {
        "status": "PASS" if passed == len(results) else "FAIL",
        "passed": passed,
        "total": len(results),
        "results": results,
    }
