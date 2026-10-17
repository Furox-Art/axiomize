"""Scientific holdout, input provenance, and explicit training-domain contracts."""

from __future__ import annotations

import copy

import numpy as np
import pytest

from axiomize.model_ir import ModelIR
from axiomize.surrogate import (
    _extract_output,
    _feature_powers,
    _latin_hypercube,
    _output_specs,
    _validate_parameter_ranges,
    evaluate_surrogate,
    fit_polynomial_surrogate,
)


@pytest.fixture
def model() -> ModelIR:
    return ModelIR.from_dict(
        {
            "schema_version": "1.0",
            "name": "decay",
            "domain": "physics",
            "family": "ode",
            "variables": [{"name": "x", "initial": 1.0}],
            "parameters": [{"name": "rate", "value": 0.5, "bounds": [0.1, 1.0]}],
            "equations": [{"target": "x", "kind": "derivative", "expression": "-rate*x"}],
        }
    )


@pytest.fixture
def data():
    x = np.linspace(-2.0, 2.0, 30)
    return {"x": x.tolist()}, {"y": (2.0 * x + 1.0).tolist()}


@pytest.fixture
def artifact(data):
    return fit_polynomial_surrogate(inputs=data[0], outputs=data[1], degree=1, seed=3)["surrogate"]


@pytest.mark.parametrize(
    ("inputs", "outputs", "message"),
    [
        ({}, {"y": list(range(10))}, "training inputs"),
        ({"x": list(range(10))}, {}, "training outputs"),
        ({"x": [1.0, 2.0]}, {"y": [1.0, 2.0]}, "at least 8"),
        ({"x": [float("nan")] * 10}, {"y": list(range(10))}, "finite 1D"),
        ({"x": list(range(10))}, {"y": list(range(9))}, "same length"),
        ({"x": [1] * 10}, {"y": list(range(10))}, "variation"),
    ],
)
def test_training_data_rejects_missing_or_uninformative_evidence(inputs, outputs, message):
    with pytest.raises(ValueError, match=message):
        fit_polynomial_surrogate(inputs=inputs, outputs=outputs, degree=1)


@pytest.mark.parametrize(
    ("keyword", "value", "message"),
    [
        ("degree", 0, "degree must be"),
        ("degree", 4, "degree must be"),
        ("ridge", -0.1, "ridge must be"),
        ("holdout_fraction", 0.09, "holdout_fraction"),
        ("holdout_fraction", 0.51, "holdout_fraction"),
        ("minimum_r2", 1.1, "minimum_r2"),
        ("maximum_nrmse", -0.01, "maximum_nrmse"),
    ],
)
def test_fit_never_relaxes_training_requirements_silently(data, keyword, value, message):
    kwargs = {"inputs": data[0], "outputs": data[1], "degree": 1}
    kwargs[keyword] = value
    with pytest.raises(ValueError, match=message):
        fit_polynomial_surrogate(**kwargs)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"schema_version": "999"}, "schema_version"),
        ({"kind": "interpolation_without_holdout"}, "surrogate kind"),
    ],
)
def test_evaluator_rejects_wrong_artifact_schema(artifact, overrides, message):
    broken = copy.deepcopy(artifact)
    broken.update(overrides)
    with pytest.raises(ValueError, match=message):
        evaluate_surrogate(broken, inputs={"x": 0.2})


@pytest.mark.parametrize("inputs", [{"y": 1.0}, {"x": 1.0, "other": 1.0}, {"x": float("inf")}])
def test_surrogate_requires_exact_finite_input_schema(artifact, inputs):
    with pytest.raises(ValueError):
        evaluate_surrogate(artifact, inputs=inputs)


def test_out_of_domain_is_blocked_and_explicit_extrapolation_is_unverified(artifact):
    blocked = evaluate_surrogate(artifact, inputs={"x": 10.0})
    assert blocked["status"] == "OUT_OF_DOMAIN"
    assert "predictions" not in blocked
    overridden = evaluate_surrogate(artifact, inputs={"x": 10.0}, allow_extrapolation=True)
    assert overridden["status"] == "UNVERIFIED_EXTRAPOLATION"
    assert overridden["in_training_domain"] is False


def test_unvalidated_surrogate_can_only_be_used_with_explicit_override(artifact):
    broken = copy.deepcopy(artifact)
    broken["validation"]["validated"] = False
    assert evaluate_surrogate(broken, inputs={"x": 0.0})["status"] == "SURROGATE_REJECTED"
    allowed = evaluate_surrogate(broken, inputs={"x": 0.0}, allow_unvalidated=True)
    assert allowed["status"] == "PASS"
    assert allowed["surrogate_validation"]["validated"] is False


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({}, "non-empty"),
        ({"unknown": [0.1, 0.2]}, "unknown parameters"),
        ({"rate": [0.0, 1.0]}, "below Model IR"),
        ({"rate": [0.2, 1.5]}, "exceeds Model IR"),
        ({"rate": [0.2]}, "must be"),
    ],
)
def test_generation_parameter_ranges_preserve_model_declared_bounds(model, raw, message):
    with pytest.raises(ValueError, match=message):
        _validate_parameter_ranges(model, raw)


@pytest.mark.parametrize(
    ("ranges", "message"),
    [
        ({"rate": (0.0, 0.0)}, "invalid finite"),
        ({"rate": (1.0, -1.0)}, "invalid finite"),
        ({"rate": (float("nan"), 1.0)}, "invalid finite"),
    ],
)
def test_latin_hypercube_requires_real_finite_increasing_range(ranges, message):
    with pytest.raises(ValueError, match=message):
        _latin_hypercube(ranges, samples=16, seed=7)


def test_latin_hypercube_reproducible_and_stratified():
    names, samples = _latin_hypercube({"rate": (0.1, 0.9)}, samples=16, seed=11)
    names2, samples2 = _latin_hypercube({"rate": (0.1, 0.9)}, samples=16, seed=11)
    assert names == names2 == ["rate"]
    np.testing.assert_array_equal(samples, samples2)
    assert 0.1 <= np.min(samples) <= np.max(samples) <= 0.9
    strata = np.floor((samples[:, 0] - 0.1) / 0.8 * 16).astype(int)
    assert sorted(strata.tolist()) == list(range(16))


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ([], "non-empty array"),
        ([1], "object"),
        ([{"state": "unknown"}], "unknown state"),
        ([{"state": "x", "metric": "median"}], "unsupported output metric"),
        ([{"state": "x", "name": "same"}, {"state": "x", "name": "same"}], "duplicate"),
    ],
)
def test_output_specification_rejects_unannounced_metrics(model, spec, message):
    with pytest.raises(ValueError, match=message):
        _output_specs(model, spec)


def test_default_output_spec_is_explicit_final_state(model):
    assert _output_specs(model, None) == [{"name": "x__final", "state": "x", "metric": "final"}]


@pytest.mark.parametrize(
    ("metric", "expected"),
    [
        ("final", 5.0),
        ("mean", 3.0),
        ("min", 1.0),
        ("max", 5.0),
        ("integral", 6.0),
    ],
)
def test_output_metrics_match_known_trajectory_integral(metric, expected):
    result = {"states": {"x": [1.0, 3.0, 5.0]}, "time": [0.0, 1.0, 2.0]}
    assert _extract_output(result, {"state": "x", "metric": metric}) == pytest.approx(expected)


def test_integral_never_invents_a_missing_time_axis():
    with pytest.raises(ValueError):
        _extract_output({"states": {"x": [1.0, 2.0]}}, {"state": "x", "metric": "integral"})


def test_feature_powers_are_bounded_not_implicitly_exponential():
    assert _feature_powers(2, 2) == [(0, 0), (1, 0), (0, 1), (2, 0), (1, 1), (0, 2)]
