"""PHASES 2-6 engine tests: provenance, cross-val, candidates, fitting,
uncertainty, bayesian, logic, falsification, sensitivity, network,
control, pde, optimization, statistics."""

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from axiomize.bayesian.mh import normal_mean_posterior
from axiomize.falsification.engine import Falsifier
from axiomize.fitting.estimator import (
    compare_fits,
    fit_curve,
    fit_sir_curve,
)
from axiomize.models.candidates import CandidateModel
from axiomize.sensitivity.analysis import (
    local_sensitivity,
    mc_sensitivity,
)
from axiomize.uncertainty.quantify import (
    UncertaintyReport,
    confidence_intervals,
    propagate,
)
from axiomize.validation.cross import compare_values, unavailable
from axiomize.validation.provenance import Parameter, Provenance
from axiomize.validation.status import ValidationStatus


class TestProvenance:
    def test_default_is_unknown(self):
        assert Parameter("b", "beta", "1/day", 0.3).provenance == Provenance.UNKNOWN

    def test_demo_param_must_be_flagged(self):
        p = Parameter("b", "beta", "1/day", 0.3,
                      provenance=Provenance.ASSUMED_FOR_DEMONSTRATION)
        assert p.provenance == Provenance.ASSUMED_FOR_DEMONSTRATION

    def test_fitted_counts_as_evidence(self):
        from axiomize.validation.provenance import is_measured

        assert is_measured(Parameter("b", "beta", "1/day", 0.3,
                                     provenance=Provenance.DATA_FITTED)) is True
        assert is_measured(Parameter("b", "beta", "1/day", 0.3,
                                     provenance=Provenance.LLM_ASSUMED)) is False


class TestCrossValidation:
    def test_agreement_passes(self):
        r = compare_values(0.94048, 0.94048, tolerance=1e-4, name="final-size")
        assert r.status == ValidationStatus.PASS

    def test_disagreement_is_conflict_with_difference(self):
        r = compare_values(0.94, 0.50, tolerance=1e-4, name="final-size")
        assert r.status == ValidationStatus.CONFLICT
        assert abs(r.difference - 0.44) < 1e-9
        assert len(r.recommended_action) > 0

    def test_missing_tool_is_explicit(self):
        r = unavailable("fenics")
        assert r.status == ValidationStatus.TOOL_UNAVAILABLE


class TestCandidates:
    def test_full_candidate_validates(self):
        m = CandidateModel(
            family="deterministic ODE", structure="SIR compartmental",
            variables=["S", "I", "R"], parameters=["beta", "gamma"],
            initial_conditions={"I0": 10}, boundary_conditions={},
            assumptions=["homogeneous mixing"], constraints=["S+I+R=N"],
            dimensions={"S": "persons"}, units={"beta": "1/day"},
            expected_domain="R0>0", required_data="case counts",
            computational_complexity="O(steps)", identifiability="beta,gamma jointly",
            falsification_conditions=["final size exceeds theory"],
            expected_limitations=["no age structure"])
        assert m.validate() is True

    def test_missing_family_rejected(self):
        m = CandidateModel(family="", structure="x", variables=["S"],
                           parameters=["beta"], initial_conditions={},
                           boundary_conditions={}, assumptions=["a"],
                           constraints=[], dimensions={}, units={},
                           expected_domain="", required_data="",
                           computational_complexity="", identifiability="",
                           falsification_conditions=[], expected_limitations="")
        with pytest.raises(ValueError):
            m.validate()


class TestFitting:
    def test_exponential_fit_recovers_truth(self):
        rng = np.random.default_rng(3)
        t = np.linspace(0, 5, 30)
        clean = 10 * np.exp(0.7 * t)
        y = clean * (1 + rng.normal(0, 0.02, size=len(t)))
        res = fit_curve(lambda tt, a, r: a * np.exp(r * tt), t, y,
                        p0=[5.0, 0.5], param_names=["a", "r"])
        assert res.success is True
        assert abs(res.params["r"][0] - 0.7) / 0.7 < 0.10
        assert res.bic < res.aic or res.bic >= 0

    def test_compare_picks_sir_over_logistic_on_sir_data(self):
        from axiomize.tools.numerical.scipy_tool import solve_sir

        t = np.linspace(0, 60, 25)
        sol = solve_sir(0.35, 0.12, 20, 10000)
        y = np.interp(t, np.linspace(0, 60, 2000), sol.y[1])
        sir = fit_sir_curve(t, y, N=10000, I0=20.0)
        from axiomize.fitting.estimator import fit_logistic_curve

        logi = fit_logistic_curve(t, y)
        assert sir.success and logi.success
        ranking = compare_fits({"sir": sir, "logistic": logi})
        assert ranking["best"] == "sir"


class TestUncertainty:
    def test_confidence_interval_contains_estimate(self):
        from axiomize.fitting.estimator import FitResult

        fit = FitResult(params={"r": (0.7, 0.05)}, rmse=1.0, aic=10.0,
                        bic=12.0, resid_autocorr=0.1, success=True,
                        method="least_squares", n=30, k=1)
        ci = confidence_intervals(fit)
        lo, hi = ci["r"]
        assert lo < 0.7 < hi

    def test_mc_propagation_mean_and_std(self):
        out = propagate(lambda x: 2.0 * x["a"], {"a": (1.0, 0.1)},
                        n=5000, seed=0)
        assert abs(out["mean"] - 2.0) < 0.05
        assert abs(out["std"] - 0.2) < 0.03

    def test_report_has_six_classes(self):
        rep = UncertaintyReport()
        assert set(rep.to_dict()) == {"parameter", "measurement", "model",
                                      "numerical", "structural", "data"}


class TestBayesian:
    def test_mh_recovers_normal_mean(self):
        rng = np.random.default_rng(1)
        y = rng.normal(5.0, 1.0, size=50)
        post = normal_mean_posterior(y, sigma=1.0, n_samples=4000,
                                     burn=1000, seed=0)
        assert abs(post["mean"] - 5.0) < 0.25
        lo, hi = post["ci95"]
        assert lo < 5.0 < hi

    def test_pymc_unavailable_is_honest(self):
        from axiomize.bayesian.pymc_tool import PyMCTool

        meta = PyMCTool.availability()
        import importlib.util

        assert meta.available == (importlib.util.find_spec("pymc") is not None)


class TestLogic:
    def test_contradiction_is_unsat(self):
        from axiomize.tools.logic.z3_tool import check_constraints

        r = check_constraints(["x > 5", "x < 3"], {"x": (0, 10)})
        assert r["sat"] is False
        assert r["status"] == ValidationStatus.FAIL

    def test_consistent_constraints_give_model(self):
        from axiomize.tools.logic.z3_tool import check_constraints

        r = check_constraints(["x > 1", "x < 4"], {"x": (0, 10)})
        assert r["sat"] is True
        assert r["status"] == ValidationStatus.PASS
        assert 1 < r["model"]["x"] < 4


class TestFalsification:
    def test_violated_bound_fails(self):
        f = Falsifier(name="growth cap", observable="growth_rate",
                      threshold=1.0, direction="above")
        assert f.evaluate(1.5)["status"] == ValidationStatus.FAIL
        assert f.evaluate(0.5)["status"] == ValidationStatus.PASS


class TestSensitivity:
    def test_local_ranks_params(self):
        from axiomize.tools.numerical.scipy_tool import solve_sir

        def final(p):
            return solve_sir(p["beta"], p["gamma"], 10, 100000, days=120).final_size

        s = local_sensitivity(final, {"beta": 0.3, "gamma": 0.1})
        assert set(s) == {"beta", "gamma"}
        assert all(np.isfinite(v) for v in s.values())

    def test_mc_indices_normalized(self):
        s = mc_sensitivity(lambda p: p["a"] * 2 + p["b"] * 0.1,
                           {"a": (0, 1), "b": (0, 1)}, n=2000, seed=0)
        assert abs(sum(s.values()) - 1.0) < 1e-9
        assert s["a"] > s["b"]


class TestNetwork:
    def test_network_sir_attack_rate_bounded(self):
        from axiomize.network.epidemic import build_er_graph, sir_on_network

        g = build_er_graph(200, 0.03, seed=0)
        r = sir_on_network(g, beta=0.15, gamma=0.1, I0=3, seed=0)
        assert 0.0 <= r["attack_rate"] <= 1.0
        assert r["peak"] >= 3

    def test_heterogeneity_factor_positive(self):
        from axiomize.network.epidemic import build_er_graph, heterogeneity_factor

        g = build_er_graph(200, 0.03, seed=0)
        assert heterogeneity_factor(g) >= 1.0


class TestControl:
    def test_pid_loop_settles(self):
        from axiomize.control.pid import closed_loop_step

        r = closed_loop_step(kp=2.0, ki=1.0, kd=0.5,
                             plant_num=[1.0], plant_den=[1.0, 1.0, 0.0])
        assert r["settled"] is True
        assert abs(r["final"] - 1.0) < 0.02


class TestPDE:
    def test_ftcs_converges_to_analytic(self):
        from axiomize.pde.diffusion import heat_ftcs

        e_coarse = heat_ftcs(alpha=0.1, length=1.0, nx=25, dt=0.0008,
                             t_end=0.05)["l2_error"]
        e_fine = heat_ftcs(alpha=0.1, length=1.0, nx=50, dt=0.0002,
                           t_end=0.05)["l2_error"]
        assert e_fine < e_coarse

    def test_unstable_dt_rejected(self):
        from axiomize.pde.diffusion import heat_ftcs

        with pytest.raises(ValueError):
            heat_ftcs(alpha=0.1, length=1.0, nx=25, dt=0.05, t_end=0.05)

    def test_fenics_unavailable_is_explicit(self):
        from axiomize.tools.pde.fenics_tool import FEniCSAdapter

        assert FEniCSAdapter.availability().available is False


class TestOptimization:
    def test_cvxpy_qp_known_solution(self):
        from axiomize.tools.optimization.cvxpy_tool import solve_qp

        r = solve_qp([[2.0, 0.0], [0.0, 2.0]], [-2.0, -5.0])
        assert r["status"] == "optimal"
        assert abs(r["x"][0] - 1.0) < 1e-4
        assert abs(r["x"][1] - 2.5) < 1e-4

    def test_casadi_nlp_rosenbrock(self):
        from axiomize.tools.optimization.casadi_tool import solve_rosenbrock

        r = solve_rosenbrock()
        assert r["success"] is True
        assert abs(r["x"][0] - 1.0) < 1e-4
        assert abs(r["x"][1] - 1.0) < 1e-4


class TestStatistics:
    def test_ols_recovers_slope(self):
        from axiomize.tools.statistics.statsmodels_tool import ols_fit

        rng = np.random.default_rng(2)
        x = np.linspace(0, 10, 50)
        y = 3.0 * x + 2.0 + rng.normal(0, 0.5, size=50)
        r = ols_fit(x, y)
        assert abs(r["params"][1] - 3.0) < 0.15
        assert r["rsquared"] > 0.95
