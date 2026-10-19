"""Native polynomial-surrogate fidelity, provenance and refusal boundaries."""
from __future__ import annotations

import numpy as np
import pytest

from axiomize import surrogate as sur
from axiomize.model_ir import ModelIR


def model():
    return ModelIR.from_dict({
        "schema_version": "1.0", "domain": "physics", "name": "measured-decay", "family": "ode",
        "variables": [{"name": "x", "initial": 1.0}],
        "parameters": [{"name": "k", "value": 0.5, "bounds": [0.0, 1.0]}],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    })


def training():
    x = np.linspace(-1, 1, 36)
    return {"x": x.tolist()}, {"y": (2 + 1.5 * x + x * x).tolist()}


def fitted():
    x, y = training()
    return sur.fit_polynomial_surrogate(inputs=x, outputs=y, degree=2, seed=7)["surrogate"]


@pytest.mark.parametrize("inputs, outputs, fragment", [
    ({}, {"y": list(range(9))}, "non-empty object"),
    ({"x": list(range(9))}, {}, "non-empty object"),
    ({"x": [1.0, 2.0]}, {"y": [2.0, 3.0]}, "at least 8"),
    ({"x": [1] * 9}, {"y": [1] * 8}, "same length"),
    ({"x": [1] * 9}, {"y": [float("nan")] * 9}, "finite 1D"),
    ({"x": [[1]] * 9}, {"y": [1] * 9}, "finite 1D"),
])
def test_surrogate_training_rejects_unrepresentative_training_data(inputs, outputs, fragment):
    with pytest.raises(ValueError, match=fragment):
        sur._validate_training_data(inputs, outputs)


@pytest.mark.parametrize("arg, fragment", [
    ({"degree": 0}, "degree must"),
    ({"degree": 4}, "degree must"),
    ({"ridge": -0.1}, "ridge must"),
    ({"holdout_fraction": 0.05}, "holdout_fraction"),
    ({"holdout_fraction": 0.8}, "holdout_fraction"),
    ({"minimum_r2": -1.1}, "minimum_r2"),
    ({"minimum_r2": 1.1}, "minimum_r2"),
    ({"maximum_nrmse": -0.1}, "maximum_nrmse"),
])
def test_surrogate_hyperparameters_are_bounded_before_linear_algebra(arg, fragment):
    x, y = training()
    with pytest.raises(ValueError, match=fragment):
        sur.fit_polynomial_surrogate(inputs=x, outputs=y, **arg)


def test_polynomial_surrogate_evidence_is_reproducible_and_hashed():
    x, y = training()
    left = sur.fit_polynomial_surrogate(inputs=x, outputs=y, degree=2, seed=7)
    right = sur.fit_polynomial_surrogate(inputs=x, outputs=y, degree=2, seed=7)
    assert left == right
    assert left["validation_status"] == "PASS"
    artifact = left["surrogate"]
    assert len(artifact["dataset_sha256"]) == 64
    assert artifact["validation"]["method"] == "seeded_untouched_holdout"
    assert artifact["use_policy"]["may_replace_full_model"] is False
    assert artifact["training_rows"] + artifact["holdout_rows"] == 36


def test_fit_refuses_near_constant_parameter_even_with_infinite_precision():
    with pytest.raises(ValueError, match="near-constant"):
        sur.fit_polynomial_surrogate(
            inputs={"x": [1.0] * 36}, outputs={"y": list(range(36))}
        )


def test_fit_refuses_underdetermined_high_order_surrogate():
    x = np.linspace(-1, 1, 8)
    with pytest.raises(ValueError, match="underdetermined"):
        sur.fit_polynomial_surrogate(
            inputs={"x": x.tolist(), "z": (x*x).tolist()}, outputs={"y": x.tolist()}, degree=3
        )


def test_surrogate_direct_prediction_matches_known_polynomial_without_substitution():
    artifact = fitted()
    response = sur.evaluate_surrogate(artifact, inputs={"x": 0.3})
    assert response["status"] == "PASS"
    assert response["predictions"]["y"] == pytest.approx(2 + 1.5 * 0.3 + 0.3**2, abs=1e-6)


@pytest.mark.parametrize("override, fragment", [
    ({"schema_version": "0"}, "schema_version"),
    ({"kind": "neural-black-box"}, "unsupported surrogate kind"),
])
def test_surrogate_rejects_unknown_evaluation_schema(override, fragment):
    s = {**fitted(), **override}
    with pytest.raises(ValueError, match=fragment):
        sur.evaluate_surrogate(s, inputs={"x": 0.0})


@pytest.mark.parametrize("payload, fragment", [
    ({}, "missing"),
    ({"x": 0.0, "unregistered": 1.0}, "extra"),
    ({"x": float("nan")}, "must be finite"),
])
def test_surrogate_rejects_missing_extra_and_nonfinite_inputs(payload, fragment):
    with pytest.raises(ValueError, match=fragment):
        sur.evaluate_surrogate(fitted(), inputs=payload)


def test_extrapolation_requires_explicit_opt_in_and_remains_unverified():
    s = fitted()
    blocked = sur.evaluate_surrogate(s, inputs={"x": 2.0})
    assert blocked["status"] == "OUT_OF_DOMAIN"
    assert "predictions" not in blocked
    allowed = sur.evaluate_surrogate(s, inputs={"x": 2.0}, allow_extrapolation=True)
    assert allowed["status"] == "UNVERIFIED_EXTRAPOLATION"
    assert allowed["domain_violations"][0]["input"] == "x"
    assert allowed["in_training_domain"] is False


def test_unvalidated_surrogate_cannot_be_routed_without_explicit_permission():
    s = {**fitted(), "validation": {"validated": False}}
    denied = sur.evaluate_surrogate(s, inputs={"x": 0.0})
    assert denied["status"] == "SURROGATE_REJECTED"
    authorized = sur.evaluate_surrogate(s, inputs={"x": 0.0}, allow_unvalidated=True)
    assert authorized["status"] == "PASS"
    assert authorized["surrogate_validation"]["validated"] is False


@pytest.mark.parametrize("samples, fragment", [(7, "samples must"), (2001, "samples must")])
def test_latin_hypercube_has_hard_budget(samples, fragment):
    with pytest.raises(ValueError, match=fragment):
        sur._latin_hypercube({"x": (0, 1)}, samples=samples, seed=11)


@pytest.mark.parametrize("bounds, fragment", [
    ((1, 1), "invalid finite"),
    ((2, 1), "invalid finite"),
    ((0, float("inf")), "invalid finite"),
    ((float("nan"), 1), "invalid finite"),
])
def test_latin_hypercube_does_not_sample_unbounded_domain(bounds, fragment):
    with pytest.raises(ValueError, match=fragment):
        sur._latin_hypercube({"x": bounds}, samples=10, seed=3)


def test_latin_hypercube_is_reproducible_and_in_domain():
    names, samples = sur._latin_hypercube({"k": (0.1, 0.8)}, samples=16, seed=2)
    names2, samples2 = sur._latin_hypercube({"k": (0.1, 0.8)}, samples=16, seed=2)
    assert names == names2 == ["k"]
    np.testing.assert_array_equal(samples, samples2)
    assert samples.shape == (16, 1)
    assert np.all((samples >= 0.1) & (samples <= 0.8))


@pytest.mark.parametrize("bounds, fragment", [
    ({}, "non-empty object"),
    ({"missing": (0, 1)}, "unknown parameters"),
    ({"k": [0]}, "must be"),
    ({"k": [-0.1, 0.5]}, "below Model IR bound"),
    ({"k": [0.2, 1.2]}, "exceeds Model IR bound"),
])
def test_source_model_parameter_domain_is_authoritative(bounds, fragment):
    with pytest.raises(ValueError, match=fragment):
        sur._validate_parameter_ranges(model(), bounds)


def test_valid_parameter_domain_does_not_expand_source_bound():
    assert sur._validate_parameter_ranges(model(), {"k": (0.1, 0.5)}) == {"k": (0.1, 0.5)}


@pytest.mark.parametrize("bad, fragment", [
    ({}, "non-empty array"),
    ([1], "each output spec must be an object"),
    ([{"state": "missing"}], "unknown state"),
    ([{"state": "x", "metric": "sum"}], "unsupported output metric"),
    ([{"state": "x"}, {"state": "x"}], "duplicate surrogate output"),
])
def test_output_specification_requires_existing_source_state(bad, fragment):
    with pytest.raises(ValueError, match=fragment):
        sur._output_specs(model(), bad)


def test_surrogate_output_metric_is_computed_from_real_trajectory():
    result = {"time": [0, 1, 2], "states": {"x": [1.0, 2.0, 3.0]}}
    expected = {"final": 3.0, "mean": 2.0, "min": 1.0, "max": 3.0, "integral": 4.0}
    for name, value in expected.items():
        assert sur._extract_output(result, {"state": "x", "metric": name}) == pytest.approx(value)


def test_integral_missing_or_mismatched_measurements_cannot_be_fabricated():
    spec = {"state": "x", "metric": "integral"}
    with pytest.raises(ValueError, match="lacks state"):
        sur._extract_output({"states": {}}, spec)
    with pytest.raises(ValueError, match="equal length"):
        sur._extract_output({"time": [0], "states": {"x": [1.0, 2.0]}}, spec)


def test_approval_is_required_before_real_training_simulation():
    outcome = sur.generate_and_fit_surrogate(
        model(), parameter_ranges={"k": (0.1, 0.8)}, samples=12, points=12,
    )
    assert outcome["status"] == "APPROVAL_REQUIRED"
    assert outcome["cost"]["full_model_runs"] == 12
    assert "sampling" not in outcome
