"""Reproducible Markov chains, FTCS CFL stability and disaggregated uncertainty."""

from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pytest

from axiomize.bayesian.mh import (
    _finite_positive,
    metropolis_hastings,
    normal_mean_posterior,
)
from axiomize.pde.diffusion import _finite as finite_heat
from axiomize.pde.diffusion import heat_ftcs
from axiomize.uncertainty.quantify import (
    UncertaintyReport,
    confidence_intervals,
    propagate,
)


@pytest.mark.parametrize(
    ("value", "pattern"),
    [
        (None, "numeric"),
        ("bad", "numeric"),
        (float("nan"), "finite and positive"),
        (0.0, "finite and positive"),
        (-1.0, "finite and positive"),
    ],
)
def test_bayesian_proposal_scale_rejects_unmeasured_or_nonpositive_values(value, pattern):
    with pytest.raises(ValueError, match=pattern):
        _finite_positive(value, name="proposal_std")


@pytest.mark.parametrize(
    ("values", "pattern"),
    [
        ([], "non-empty 1D"),
        ([[1.0, 2.0]], "non-empty 1D"),
        ([float("nan")], "finite values"),
        ([float("inf")], "finite values"),
    ],
)
def test_mh_initial_parameter_vector_must_be_finite_and_one_dimensional(values, pattern):
    with pytest.raises(ValueError, match=pattern):
        metropolis_hastings(lambda x: -float(np.dot(x, x)), np.asarray(values), n_samples=10, burn=0)


def test_nonfinite_initial_log_density_is_not_a_valid_bayesian_posterior():
    with pytest.raises(ValueError, match="log_posterior\\(x0\\) must be finite"):
        metropolis_hastings(lambda x: float("nan"), np.array([0.0]), n_samples=10, burn=0)


def test_invalid_proposal_density_is_rejected_without_nan_contaminating_chain():
    def density(x):
        return 0.0 if x[0] == 0 else float("nan")

    out = metropolis_hastings(density, np.array([0.0]), n_samples=20, burn=2, seed=3)
    assert out["acceptance_rate"] == 0.0
    assert np.all(out["samples"] == 0.0)


def test_reproducible_gaussian_mh_is_seed_deterministic():
    def gaussian(x):
        return -0.5 * float(np.dot(x, x))

    kwargs = dict(log_posterior=gaussian, x0=np.array([0.0]), n_samples=200, burn=10, seed=12)
    left = metropolis_hastings(**kwargs)
    right = metropolis_hastings(**kwargs)
    np.testing.assert_array_equal(left["samples"], right["samples"])
    assert left["acceptance_rate"] == right["acceptance_rate"]
    assert 0.0 <= left["acceptance_rate"] <= 1.0


@pytest.mark.parametrize(
    ("observations", "pattern"),
    [
        ([], "non-empty 1D"),
        ([[1.0, 2.0]], "non-empty 1D"),
        ([float("nan")], "finite values"),
        ([float("inf")], "finite values"),
    ],
)
def test_gaussian_mean_posterior_rejects_invalid_observations(observations, pattern):
    with pytest.raises(ValueError, match=pattern):
        normal_mean_posterior(np.asarray(observations), sigma=1.0, n_samples=20, burn=5)


@pytest.mark.parametrize(
    ("prior_mean", "pattern"),
    [
        (None, "must be numeric"),
        ("bad", "must be numeric"),
        (float("inf"), "must be finite"),
    ],
)
def test_gaussian_prior_center_requires_explicit_finite_numeric_value(prior_mean, pattern):
    with pytest.raises(ValueError, match=pattern):
        normal_mean_posterior(np.array([1.0, 2.0]), sigma=1.0, prior_mean=prior_mean, n_samples=20, burn=5)


def test_seeded_normal_mean_posterior_agrees_with_gaussian_conjugate_order():
    data = np.array([1.8, 2.0, 2.2])
    result = normal_mean_posterior(data, sigma=0.5, prior_std=10.0, n_samples=750, burn=150, seed=1)
    assert result["mean"] == pytest.approx(2.0, abs=0.15)
    assert result["ci95"][0] < result["mean"] < result["ci95"][1]
    assert 0.0 <= result["acceptance_rate"] <= 1.0


@pytest.mark.parametrize(
    ("raw", "pattern"),
    [
        ("not numeric", "must be numeric"),
        (None, "must be numeric"),
        (float("inf"), "must be finite"),
    ],
)
def test_heat_solver_requires_finite_explicit_physical_rates(raw, pattern):
    with pytest.raises(ValueError, match=pattern):
        finite_heat(raw, name="alpha")


@pytest.mark.parametrize(
    ("altered", "pattern"),
    [
        ({"alpha": -1.0}, "non-negative"),
        ({"length": 0.0}, "positive"),
        ({"dt": 0.0}, "positive"),
        ({"t_end": -1.0}, "non-negative"),
        ({"nx": 1}, "nx"),
        ({"dt": 10.0}, "unstable"),
    ],
)
def test_heat_equation_refuses_nonphysical_parameters_or_violated_cfl(altered, pattern):
    params = dict(alpha=0.1, length=1.0, nx=11, dt=0.01, t_end=0.5)
    params.update(altered)
    with pytest.raises(ValueError, match=pattern):
        heat_ftcs(**params)


def test_exact_heat_solution_baseline_at_zero_time_has_zero_discretization_error():
    out = heat_ftcs(alpha=0.1, length=1.0, nx=40, dt=0.001, t_end=0.0)
    assert out["steps"] == 0
    assert out["l2_error"] == pytest.approx(0.0)


def test_positive_heat_diffusion_is_stable_under_true_cfl_and_tracks_exact_solution():
    out = heat_ftcs(alpha=0.1, length=1.0, nx=31, dt=0.002, t_end=0.2)
    assert out["steps"] == 100
    assert 0.0 <= out["cfl"] <= 0.5
    assert math.isfinite(out["l2_error"])
    assert out["l2_error"] < 0.005


def test_heat_grid_work_exceeds_safe_allocation_before_scientific_run():
    with pytest.raises(ValueError, match="grid-time work|step count"):
        heat_ftcs(alpha=0.0, length=1.0, nx=20000, dt=0.001, t_end=1000.0)


def test_heat_zero_diffusivity_preserves_sine_initial_profile():
    out = heat_ftcs(alpha=0.0, length=1.0, nx=12, dt=0.01, t_end=0.2)
    assert out["cfl"] == 0.0
    assert out["l2_error"] == pytest.approx(0.0, abs=1e-15)


@pytest.mark.parametrize(
    ("alpha", "pattern"),
    [
        (None, "numeric"),
        ("invalid", "numeric"),
        (0.0, "finite and in"),
        (1.0, "finite and in"),
        (float("nan"), "finite and in"),
    ],
)
def test_confidence_level_requires_actual_probability(alpha, pattern):
    with pytest.raises(ValueError, match=pattern):
        confidence_intervals(SimpleNamespace(params={"theta": (2.0, 0.1)}), alpha=alpha)


@pytest.mark.parametrize(
    ("value", "error"),
    [
        ((float("nan"), 1.0), "finite value"),
        ((1.0, float("nan")), "finite value"),
        ((1.0, -1.0), "finite value"),
    ],
)
def test_confidence_interval_refuses_nonfinite_or_negative_uncertainty(value, error):
    with pytest.raises(ValueError, match=error):
        confidence_intervals(SimpleNamespace(params={"theta": value}))


def test_confidence_intervals_match_standard_normal_quantile():
    intervals = confidence_intervals(SimpleNamespace(params={"theta": (2.0, 1.0)}), alpha=0.05)
    assert intervals["theta"][0] == pytest.approx(2 - 1.95996398454, rel=1e-6)
    assert intervals["theta"][1] == pytest.approx(2 + 1.95996398454, rel=1e-6)


@pytest.mark.parametrize(
    ("params", "pattern"),
    [
        ({}, "1.."),
        ({"x": [1.0]}, "[value, stderr]"),
        ({"x": [1.0, -1.0]}, "non-negative stderr"),
        ({"x": [1.0, float("nan")]}, "non-negative stderr"),
    ],
)
def test_mc_uncertainty_params_require_a_value_and_independent_error(params, pattern):
    with pytest.raises(ValueError, match=pattern):
        propagate(lambda p: p.get("x", 1.0), params, n=10, seed=0)


def test_mc_uncertainty_with_seed_is_reproducible_for_actual_observation_function():
    args = dict(func=lambda p: p["a"] * 2.0, params={"a": (3.0, 0.2)}, n=100, seed=123)
    left = propagate(**args)
    right = propagate(**args)
    assert left == right
    assert left["mean"] == pytest.approx(6.0, abs=0.2)
    assert left["std"] > 0.0


def test_mc_uncertainty_refuses_nonfinite_model_output():
    with pytest.raises(ValueError, match="non-finite"):
        propagate(lambda p: float("nan"), {"x": (1.0, 0.1)}, n=10, seed=0)


def test_uncertainty_categories_remain_separate_in_serialized_result():
    report = UncertaintyReport(
        parameter={"k": 0.1},
        measurement={"sensor": 0.2},
        numerical={"roundoff": 0.01},
        structural={"assumption": "untested"},
    )
    result = report.to_dict()
    assert result["parameter"] == {"k": 0.1}
    assert result["measurement"] == {"sensor": 0.2}
    assert result["numerical"] == {"roundoff": 0.01}
    assert result["structural"] == {"assumption": "untested"}
    assert result["model"] == {}
