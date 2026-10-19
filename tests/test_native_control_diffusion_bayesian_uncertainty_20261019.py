"""Executable bounded control, heat diffusion, posterior diagnostics and uncertainty."""
from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.bayesian.diagnostics import (
    _autocorrelation,
    effective_sample_size,
    normal_posterior_predictive,
    posterior_diagnostics,
    split_rhat,
)
from axiomize.control.pid import closed_loop_step
from axiomize.fitting.estimator import FitResult
from axiomize.pde.diffusion import heat_ftcs
from axiomize.uncertainty.quantify import (
    UncertaintyReport,
    confidence_intervals,
    propagate,
)


def test_pid_actual_stable_control_reaches_unit_setpoint():
    actual = closed_loop_step(
        kp=2.0, ki=1.0, kd=0.0,
        plant_num=[1.0], plant_den=[1.0, 1.0], t_end=15.0, n=300,
    )
    assert actual["points"] == 300
    assert math.isfinite(actual["final"])
    assert actual["settled"] is True
    assert actual["final"] == pytest.approx(1.0, abs=0.03)
    assert actual["overshoot"] >= 0.0


def test_zero_plant_has_no_false_settling_time():
    out = closed_loop_step(1, 0, 0, [0], [1, 1], n=40, t_end=1)
    assert out["final"] == pytest.approx(0)
    assert out["settled"] is False
    assert out["settling_time"] is None


@pytest.mark.parametrize("arg, kwargs, pattern", [
    ("kp", {"kp": "no"}, "kp must be numeric"),
    ("ki", {"ki": float("inf")}, "ki must be finite"),
    ("plant_num", {"plant_num": "x"}, "numeric 1D"),
    ("plant_den", {"plant_den": [0, 0]}, "zero polynomial"),
    ("plant_den", {"plant_den": []}, "coefficients"),
    ("plant_num", {"plant_num": [1, float("nan")]}, "must be finite"),
    ("t_end", {"t_end": 0}, "t_end must be"),
    ("t_end", {"t_end": 1e10}, "t_end must be"),
    ("n", {"n": 1}, "control output points"),
])
def test_pid_fails_closed_on_invalid_or_unbounded_model(arg, kwargs, pattern):
    base = dict(kp=1.0, ki=0.5, kd=0.0, plant_num=[1.0],
                plant_den=[1.0, 1.0], t_end=1.0, n=40)
    base.update(kwargs)
    with pytest.raises(ValueError, match=pattern):
        closed_loop_step(**base)


def test_heat_solver_matches_analytic_sine_decay_under_cfl_bound():
    result = heat_ftcs(alpha=0.01, length=1.0, nx=15, dt=0.05, t_end=1.0)
    assert 0 <= result["cfl"] <= 0.5
    assert result["steps"] == 20
    assert result["work_units"] == 15 * 20
    assert result["l2_error"] < 0.01


def test_zero_diffusion_exactly_conserves_the_initial_sine():
    out = heat_ftcs(alpha=0.0, length=1.0, nx=5, dt=0.1, t_end=0.5)
    assert out["l2_error"] == pytest.approx(0.0, abs=1e-15)
    assert out["cfl"] == 0


@pytest.mark.parametrize("kw,pattern", [
    ({"alpha": -1.0}, "alpha must be non-negative"),
    ({"length": 0}, "length must be positive"),
    ({"dt": 0}, "dt must be positive"),
    ({"t_end": -1}, "t_end must be non-negative"),
    ({"alpha": float("nan")}, "finite"),
    ({"nx": 2}, "nx"),
    ({"dt": 1, "alpha": 1.0}, "unstable"),
    ({"dt": 1e-7, "t_end": 1.0}, "FTCS step count exceeds"),
])
def test_heat_solver_refuses_unphysical_or_unbounded_simulation(kw,pattern):
    inputs = dict(alpha=0.01, length=1.0, nx=10, dt=0.01, t_end=1)
    inputs.update(kw)
    with pytest.raises(ValueError, match=pattern):
        heat_ftcs(**inputs)


def test_rhat_distinguishes_stationary_and_disjoint_chains():
    rng = np.random.default_rng(9)
    coherent = rng.normal(size=(4, 90))
    disjoint = np.vstack((rng.normal(-5, 0.1, 90), rng.normal(5, 0.1, 90)))
    assert split_rhat(coherent) < 1.2
    assert split_rhat(disjoint) > 1.05
    assert math.isnan(split_rhat(np.zeros((1, 3))))
    assert split_rhat(np.zeros((2, 8))) == 1.0
    assert math.isinf(split_rhat(np.array([[0]*8, [1]*8])))


def test_effective_sample_size_bounded_and_degenerate():
    rng = np.random.default_rng(7)
    chains = rng.normal(size=(3, 100))
    ess = effective_sample_size(chains)
    assert 1 <= ess <= chains.size
    assert math.isnan(effective_sample_size(np.asarray([1, 2, 3])))
    assert np.all(_autocorrelation(np.ones(8), 4) == 0.0)


def test_real_posterior_diagnostics_are_explicit_for_nonidentical_chains():
    rng = np.random.default_rng(5)
    values = rng.normal(size=(4, 80, 2))
    report = posterior_diagnostics(values, ["slope", "intercept"])
    assert report["status"] in {"PASS", "WARNING"}
    assert set(report["parameters"]) == {"slope", "intercept"}
    assert report["parameters"]["slope"]["ess_bulk"] > 0
    with pytest.raises(ValueError, match="shape"):
        posterior_diagnostics(values, ["missing"])


def test_bayesian_ppc_real_draws_report_coverage_without_inventing_agreement():
    observed = np.zeros(12)
    means = np.zeros((50, 12))
    sigmas = np.ones(50)
    output = normal_posterior_predictive(
        observed=observed, means=means, sigmas=sigmas,
        seed=7, max_replications=20,
    )
    assert output["replications"] == 20
    assert output["seed"] == 7
    assert 0 <= output["coverage90"] <= 1
    assert 0 <= output["coverage95"] <= 1
    assert output["predictive_rmse"] >= 0
    assert output == normal_posterior_predictive(
        observed=observed, means=means, sigmas=sigmas, seed=7,
        max_replications=20,
    )


@pytest.mark.parametrize("means, sigmas, fragment", [
    (np.zeros((10, 2)), np.ones(10), "means must have shape"),
    (np.zeros((12, 3)), np.ones(9), "sigma vector"),
    (np.zeros((9, 3)), np.ones(9), "at least 10"),
])
def test_ppc_does_not_silently_accept_mismatched_posterior(means,sigmas,fragment):
    with pytest.raises(ValueError, match=fragment):
        normal_posterior_predictive(
            observed=np.zeros(3), means=means, sigmas=sigmas,
            seed=1, max_replications=100,
        )


def fit(params):
    return FitResult(
        params=params, rmse=0, aic=0, bic=0, resid_autocorr=0,
        success=True, method="synthetic-check", n=10, k=len(params),
    )


def test_normal_confidence_intervals_match_declared_error_scale():
    ci = confidence_intervals(fit({"k": (2.0, 0.5)}))
    assert ci["k"][0] < 2.0 < ci["k"][1]
    assert ci["k"][1] - 2.0 == pytest.approx(0.98, abs=0.01)


@pytest.mark.parametrize("params,alpha,fragment", [
    ({"x": (1, 1)}, 0.0, "alpha must"),
    ({"x": (1, 1)}, 1.0, "alpha must"),
    ({"x": (1, 1)}, "bad", "alpha must be numeric"),
    ({"x": (1, -1)}, 0.05, "non-negative"),
    ({"x": (float("nan"), 1)}, 0.05, "finite"),
])
def test_confidence_intervals_reject_unjustified_sigma_and_alpha(params,alpha,fragment):
    with pytest.raises(ValueError, match=fragment):
        confidence_intervals(fit(params), alpha)


def test_direct_uncertainty_propagation_keeps_parameter_and_signal_separate():
    result = propagate(lambda p: 2*p["x"], {"x": (1.0, 0.1)}, n=500, seed=17)
    assert result["mean"] == pytest.approx(2.0, abs=0.05)
    assert 0.12 <= result["std"] <= 0.27
    assert result["p5"] < result["mean"] < result["p95"]


@pytest.mark.parametrize("params,pattern", [
    ({}, "params must contain"),
    ({"x": (1,)}, "must be"),
    ({"x": (1, -1)}, "non-negative"),
    ({"x": (float("inf"), 1)}, "finite"),
])
def test_uncertainty_sampling_refuses_untrusted_parameters(params,pattern):
    with pytest.raises(ValueError, match=pattern):
        propagate(lambda p: 1, params, n=10)


def test_nonfinite_parameter_response_is_never_silent_posterior_evidence():
    with pytest.raises(ValueError, match="non-finite"):
        propagate(lambda p: float("nan"), {"x": (1, 0.1)}, n=10)


def test_uncertainty_report_separates_six_sources():
    result = UncertaintyReport(parameter={"k": {"stderr": 0.1}})
    wire = result.to_dict()
    assert set(wire) == {"parameter", "measurement", "model", "numerical", "structural", "data"}
    assert wire["parameter"]["k"]["stderr"] == 0.1
    assert all(wire[k] == {} for k in ("measurement", "model", "numerical", "structural", "data"))
