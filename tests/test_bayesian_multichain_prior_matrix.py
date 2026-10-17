"""Multichain Bayesian priors, diagnostics, and explicit observation evidence."""

from __future__ import annotations

import math

import pytest

from axiomize.bayesian.engine_v2 import _log_prior, _parameters, infer_bayesian_model
from axiomize.model_ir import ModelFamily, ModelIR, ParameterSpec


def model(config=None, params=None):
    return ModelIR(
        name="bayes",
        domain="statistics",
        family=ModelFamily.BAYESIAN,
        variables=[],
        equations=[],
        parameters=params
        if params is not None
        else [
            ParameterSpec("mu", 1.0, prior={"dist": "normal", "mu": 0.0, "sigma": 5.0}, fit=True),
        ],
        metadata={
            "bayesian": config
            if config is not None
            else {
                "observations": [1.0, 2.0, 3.0, 2.0],
                "mean_expression": "mu",
                "sigma": 0.5,
                "draws": 60,
                "burn": 20,
                "chains": 2,
            }
        },
    )


def run(mod, seed=7, overrides=None):
    return infer_bayesian_model(
        mod,
        t_span=(0.0, 1.0),
        points=5,
        parameter_overrides=overrides,
        seed=seed,
    )


@pytest.mark.parametrize(
    ("overrides", "params", "pattern"),
    [
        ({"absent": 1.0}, None, "unknown parameter overrides"),
        ({}, [ParameterSpec("mu", None)], "has no value"),
        ({"mu": float("nan")}, None, "must be finite"),
        ({"mu": float("inf")}, None, "must be finite"),
    ],
)
def test_bayesian_parameter_source_never_fabricates_missing_numeric_values(overrides, params, pattern):
    with pytest.raises(ValueError, match=pattern):
        _parameters(model(params=params), overrides)


@pytest.mark.parametrize(
    ("value", "prior", "expected"),
    [
        (0.0, {"dist": "normal", "mu": 0.0, "sigma": 1.0}, 0.0),
        (1.0, {"dist": "uniform", "low": 0.0, "high": 2.0}, 0.0),
        (-1.0, {"dist": "halfnormal", "sigma": 1.0}, -math.inf),
        (-1.0, {"dist": "lognormal", "sigma": 1.0}, -math.inf),
        (3.0, {"dist": "uniform", "low": 0.0, "high": 2.0}, -math.inf),
        (1.0, {"dist": "halfnormal", "sigma": 1.0}, -0.5),
    ],
)
def test_native_prior_support_and_density_are_explicit(value, prior, expected):
    score = _log_prior(value, prior, None, center=1.0)
    assert score == pytest.approx(expected) if math.isfinite(expected) else score == -math.inf


@pytest.mark.parametrize(
    ("prior", "pattern"),
    [
        ({"dist": "normal", "sigma": 0}, "normal prior sigma"),
        ({"dist": "normal", "sigma": float("nan")}, "normal prior sigma"),
        ({"dist": "halfnormal", "sigma": 0}, "halfnormal prior sigma"),
        ({"dist": "halfnormal", "sigma": float("inf")}, "halfnormal prior sigma"),
        ({"dist": "lognormal", "sigma": 0}, "lognormal prior sigma"),
        ({"dist": "uniform", "low": 3.0, "high": 2.0}, "lower must be"),
        ({"dist": "unknown"}, "unsupported builtin prior"),
    ],
)
def test_invalid_prior_does_not_turn_into_finite_scientific_evidence(prior, pattern):
    with pytest.raises(ValueError, match=pattern):
        _log_prior(1.0, prior, None, center=1.0)


def test_prior_bounds_exclude_values_outside_physical_domain():
    assert _log_prior(-1.0, None, (0.0, 2.0), center=1.0) == -math.inf
    assert _log_prior(3.0, None, (0.0, 2.0), center=1.0) == -math.inf
    assert math.isfinite(_log_prior(1.0, None, (0.0, 2.0), center=1.0))


@pytest.mark.parametrize(
    ("cfg", "pattern"),
    [
        ([], "metadata.bayesian"),
        ({"data": []}, "bayesian.data"),
        ({}, "observations must be finite"),
        ({"observations": [1.0]}, "observations must be finite"),
        ({"observations": [1.0, float("nan")]}, "observations must be finite"),
        ({"observations": [1.0, 2.0]}, "requires mean_expression"),
        ({"observations": [1.0, 2.0], "mean_expression": "mu", "draws": 49}, "bayesian.draws"),
        ({"observations": [1.0, 2.0], "mean_expression": "mu", "chains": 1}, "bayesian.chains"),
        ({"observations": [1.0, 2.0], "mean_expression": "mu", "chains": 9}, "bayesian.chains"),
        ({"observations": [1.0, 2.0], "mean_expression": "mu", "sigma": "missing"}, "sigma parameter name"),
        ({"observations": [1.0, 2.0], "mean_expression": "mu", "proposal_scale": 0}, "proposal scale"),
        ({"observations": [1.0, 2.0], "mean_expression": "mu", "proposal_scale": float("nan")}, "proposal scale"),
        ({"observations": [1.0, 2.0], "mean_expression": "mu", "data": {"x": [1.0]}}, "match observations"),
        (
            {"observations": [1.0, 2.0], "mean_expression": "mu", "data": {"x": [float("nan"), 1.0]}},
            "match observations",
        ),
    ],
)
def test_bayesian_inference_enforces_observation_and_chain_contracts(cfg, pattern):
    with pytest.raises(ValueError, match=pattern):
        run(model(cfg))


def test_finite_posterior_keeps_raw_and_summary_evidence_separate():
    settings = {
        "observations": [1.0, 1.5, 2.0],
        "mean_expression": "mu",
        "sigma": 0.25,
        "chains": 2,
        "draws": 75,
        "burn": 30,
        "return_samples": True,
        "proposal_scale": 0.12,
    }
    one = run(model(settings), seed=11)
    two = run(model(settings), seed=11)
    assert one["status"] == "PASS"
    assert one == two
    assert one["solver"]["method"] == "multi_chain_random_walk_metropolis"
    assert one["diagnostics"]["chains"] == 2
    assert len(one["samples"]["mu"]) == 150
    assert one["diagnostics"]["posterior"]["parameters"]["mu"]["ess_bulk"] > 0
    assert one["posterior_predictive"]
    assert one["parameters"]["mu"] == one["posterior"]["mu"]["mean"]


def test_bayesian_sigma_as_fitted_parameter_is_reported_in_posterior():
    settings = {
        "observations": [1.0, 2.0, 1.5, 2.5],
        "mean_expression": "mu",
        "sigma": "sigma",
        "chains": 2,
        "draws": 60,
        "burn": 20,
    }
    params = [
        ParameterSpec("mu", 1.7, prior={"dist": "normal", "mu": 2.0, "sigma": 3.0}, fit=True),
        ParameterSpec("sigma", 0.5, prior={"dist": "halfnormal", "sigma": 1.0}, fit=True),
    ]
    out = run(model(settings, params=params))
    assert out["status"] == "PASS"
    assert set(out["posterior"]) == {"mu", "sigma"}
    assert out["posterior_predictive"]


def test_bayesian_named_outcome_can_come_from_declared_data():
    settings = {
        "outcome": "observed_y",
        "data": {"observed_y": [1.0, 1.5, 2.0], "x": 1.0},
        "mean_expression": "mu",
        "chains": 2,
        "draws": 50,
        "burn": 10,
    }
    out = run(model(settings))
    assert out["status"] == "PASS"


def test_empty_bayesian_parameter_list_is_never_auto_padded():
    with pytest.raises(ValueError, match="at least one parameter"):
        run(model(params=[]))
