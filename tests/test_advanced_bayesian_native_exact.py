"""Native Bayesian inference: analytic Gaussian posterior and hard input guards."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.advanced_family_engine import _infer_bayesian
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, ParameterSpec

OBSERVATIONS = [2.0, 2.5, 3.0, 2.5]


def _model(config, *, params=None, equations=()):
    return ModelIR(
        name="normal-location",
        domain="statistics",
        family=ModelFamily.BAYESIAN,
        variables=[],
        parameters=list(
            params
            if params is not None
            else [ParameterSpec("mu", 1.0, prior={"dist": "normal", "mu": 0.0, "sigma": 5.0}, fit=True)]
        ),
        equations=list(equations),
        metadata={"bayesian": config},
    )


def _run(model, *, seed=17):
    return _infer_bayesian(
        model,
        t_span=(0.0, 1.0),
        points=5,
        parameter_overrides=None,
        seed=seed,
    )


def test_normal_mean_posterior_matches_closed_form_with_mcmc_error():
    prior_sigma = 5.0
    likelihood_sigma = 0.5
    n = len(OBSERVATIONS)
    expected_variance = 1.0 / (1.0 / prior_sigma**2 + n / likelihood_sigma**2)
    expected_mean = expected_variance * sum(OBSERVATIONS) / likelihood_sigma**2
    model = _model(
        {
            "observations": OBSERVATIONS,
            "mean_expression": "mu",
            "sigma": likelihood_sigma,
            "draws": 1600,
            "burn": 400,
            "proposal_scale": 0.15,
            "return_samples": True,
        }
    )
    out = _run(model, seed=11)
    assert out["status"] == "PASS"
    assert out["solver"]["method"] == "multi_chain_random_walk_metropolis"
    assert out["diagnostics"]["draws"] == 1600
    assert out["diagnostics"]["finite"] is True
    samples = np.asarray(out["samples"]["mu"])
    chains = out["diagnostics"]["chains"]
    assert chains >= 2
    assert samples.shape == (1600 * chains,)
    diag = out["diagnostics"]["posterior"]["parameters"]["mu"]
    assert diag["r_hat"] < 1.05
    assert diag["ess_bulk"] > 50
    assert math.isfinite(out["posterior"]["mu"]["mean"])
    assert out["posterior"]["mu"]["mean"] == pytest.approx(expected_mean, abs=0.18)
    assert out["posterior"]["mu"]["sd"] == pytest.approx(math.sqrt(expected_variance), abs=0.12)
    assert 0 < out["diagnostics"]["acceptance_rate"] < 1
    assert out["parameters"]["mu"] == out["posterior"]["mu"]["mean"]


def test_identical_seed_reproduces_full_posterior_summary():
    model = _model(
        {
            "observations": OBSERVATIONS,
            "mean_expression": "mu",
            "draws": 60,
            "burn": 20,
            "return_samples": True,
        }
    )
    assert _run(model, seed=7) == _run(model, seed=7)
    assert _run(model, seed=7)["samples"] != _run(model, seed=8)["samples"]


def test_mean_expression_can_be_from_declared_equation():
    model = _model(
        {
            "observations": OBSERVATIONS,
            "draws": 60,
            "burn": 20,
        },
        equations=[EquationSpec("observed", "mu", kind="likelihood")],
    )
    out = _run(model)
    assert out["status"] == "PASS"
    assert out["diagnostics"]["draws"] == 60


def test_observed_outcome_must_be_supplied_without_silent_imputation():
    model = _model(
        {
            "outcome": "y",
            "data": {"y": OBSERVATIONS},
            "mean_expression": "mu",
            "draws": 60,
            "burn": 20,
        }
    )
    assert _run(model)["status"] == "PASS"


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ("invalid", "metadata.bayesian must be an object"),
        ({"observations": OBSERVATIONS, "data": [], "mean_expression": "mu"}, "bayesian.data must be an object"),
        ({}, "observations must be finite"),
        ({"observations": [1.0], "mean_expression": "mu"}, "finite 1D with 2"),
        ({"observations": [[1.0, 2.0]], "mean_expression": "mu"}, "finite 1D with 2"),
        ({"observations": OBSERVATIONS}, "requires mean_expression"),
        ({"observations": OBSERVATIONS, "mean_expression": "mu", "draws": 49}, "draws must be"),
        ({"observations": OBSERVATIONS, "mean_expression": "mu", "draws": 200001}, "draws must be"),
        ({"observations": OBSERVATIONS, "mean_expression": "mu", "draws": 60, "burn": -1}, "bayesian.burn must be"),
        (
            {"observations": OBSERVATIONS, "mean_expression": "mu", "sigma": "missing", "draws": 60},
            "sigma parameter name is unknown",
        ),
        (
            {"observations": OBSERVATIONS, "mean_expression": "mu", "sigma": 0, "draws": 60, "burn": 10},
            "zero/invalid posterior",
        ),
        (
            {"observations": OBSERVATIONS, "mean_expression": "mu", "sigma": float("nan"), "draws": 60, "burn": 10},
            "zero/invalid posterior",
        ),
        (
            {"observations": OBSERVATIONS, "mean_expression": "mu", "data": {"x": [1.0]}, "draws": 60, "burn": 10},
            "must be finite scalar or match observations",
        ),
        (
            {"observations": OBSERVATIONS, "mean_expression": "mu + x", "data": {"x": [1.0]}, "draws": 60, "burn": 10},
            "must be finite scalar or match observations",
        ),
    ],
)
def test_native_bayes_rejects_missing_malformed_or_nonphysical_evidence(config, expected):
    with pytest.raises(ValueError, match=expected):
        _run(_model(config))


def test_bayes_rejects_absent_parameters_even_with_defined_mean():
    model = _model({"observations": OBSERVATIONS, "mean_expression": "1", "draws": 60}, params=[])
    with pytest.raises(ValueError, match="at least one parameter"):
        _run(model)


def test_bayes_rejects_initial_value_outside_its_prior_bounds():
    model = _model(
        {
            "observations": OBSERVATIONS,
            "mean_expression": "mu",
            "draws": 60,
        },
        params=[ParameterSpec("mu", 2.0, bounds=(0.0, 1.0))],
    )
    with pytest.raises(ValueError, match="zero/invalid posterior density"):
        _run(model)
