"""Scientific benchmark suite (PHASE 10).

Twelve end-to-end cases exercising the engine the way the mandate
requires. Nothing here is mocked: every case runs real solvers and
asserts verifiable properties. Failing cases fail loudly.
"""

import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "skills" / "axiomize" / "tools"))

from axiomize.application.services import compare_service
from axiomize.bayesian.mh import normal_mean_posterior
from axiomize.control.pid import closed_loop_step
from axiomize.fitting.estimator import (
    compare_fits,
    fit_logistic_curve,
    fit_sir_curve,
)
from axiomize.network.epidemic import (
    build_er_graph,
    heterogeneity_factor,
    sir_on_network,
)
from axiomize.pde.diffusion import heat_ftcs
from axiomize.routing.router import classify
from axiomize.tools.numerical.scipy_tool import (
    final_size_numeric,
    solve_sir,
)
from axiomize.tools.optimization.casadi_tool import solve_rosenbrock
from axiomize.tools.optimization.cvxpy_tool import solve_qp
from axiomize.tools.statistics.statsmodels_tool import ols_fit
from axiomize.validation.status import ValidationStatus


def test_01_deterministic_model():
    res = solve_sir(0.3, 0.1, 10, 1_000_000, days=180)
    assert res.success and res.max_conservation_error < 1e-3
    # finite-horizon simulation vs t->infinity theory: close, not identical
    assert abs(res.final_size - final_size_numeric(0.3, 0.1)) < 5e-4


def test_02_nonlinear_ode_outbreak():
    res = solve_sir(0.35, 0.12, 20, 10000, days=120)
    assert res.final_size > 0.5
    assert float(np.max(res.y[1])) > 20


def test_03_optimization():
    qp = solve_qp([[2.0, 0.0], [0.0, 2.0]], [-2.0, -5.0])
    assert qp["status"] == "optimal"
    nlp = solve_rosenbrock()
    assert nlp["success"] is True


def test_04_regression():
    rng = np.random.default_rng(5)
    x = np.linspace(0, 10, 50)
    y = 3.0 * x + 2.0 + rng.normal(0, 0.5, size=50)
    r = ols_fit(x, y)
    assert abs(r["params"][1] - 3.0) < 0.15


def test_05_bayesian_fitting():
    rng = np.random.default_rng(6)
    y = rng.normal(5.0, 1.0, size=50)
    post = normal_mean_posterior(y, sigma=1.0, n_samples=4000,
                                 burn=1000, seed=0)
    lo, hi = post["ci95"]
    assert lo < 5.0 < hi


def test_06_network_model():
    g = build_er_graph(200, 0.03, seed=0)
    assert heterogeneity_factor(g) >= 1.0
    r = sir_on_network(g, beta=0.15, gamma=0.1, I0=3, seed=0)
    assert 0.0 <= r["attack_rate"] <= 1.0


def test_07_control_problem():
    r = closed_loop_step(kp=2.0, ki=1.0, kd=0.5,
                         plant_num=[1.0], plant_den=[1.0, 1.0, 0.0])
    assert r["settled"] is True


def test_08_stochastic_model():
    from validate import gillespie_sir_once

    rng = np.random.default_rng(9)
    runs = [gillespie_sir_once(0.3, 0.1, 1, 5000, rng=rng) for _ in range(400)]
    p_obs = sum(r["extinct_early"] for r in runs) / len(runs)
    p_theory = (1 / (1 + 3.0)) ** 1
    assert abs(p_obs - p_theory) < 0.08


def test_09_pde_convergence():
    coarse = heat_ftcs(alpha=0.1, length=1.0, nx=25, dt=0.0008, t_end=0.05)
    fine = heat_ftcs(alpha=0.1, length=1.0, nx=50, dt=0.0002, t_end=0.05)
    assert fine["l2_error"] < coarse["l2_error"]


def test_10_wrong_model_rejected():
    t = np.linspace(0, 60, 25)
    sol = solve_sir(0.35, 0.12, 20, 10000)
    y = np.interp(t, np.linspace(0, 60, 2000), sol.y[1])
    sir = fit_sir_curve(t, y, N=10000, I0=20.0)
    logi = fit_logistic_curve(t, y)
    ranking = compare_fits({"sir": sir, "logistic": logi})
    assert ranking["best"] == "sir"
    assert logi.bic > sir.bic


def test_11_missing_information_explicit():
    d = classify({"signals": []})
    assert d.problem_type == "unknown"
    assert d.status == ValidationStatus.INCONCLUSIVE


def test_12_multiple_valid_models_compared():
    t = np.linspace(0, 60, 25)
    sol = solve_sir(0.35, 0.12, 20, 10000)
    y = np.interp(t, np.linspace(0, 60, 2000), sol.y[1])
    out = compare_service({"t": t.tolist(), "y": y.tolist(), "N": 10000,
                           "I0": 20.0})
    assert len(out["ranking"]) >= 2
    assert out["best"] in out["ranking"]
    assert "BIC" in out["reason"]
