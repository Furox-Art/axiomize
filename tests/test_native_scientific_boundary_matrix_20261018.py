"""Exact numerical/model-integrity boundary checks for native executors.

These are assertion-backed tests of real parameter, prior, validation, and
coupling behavior. They do not change threshold settings or exclude code.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize import advanced_family_engine as engine
from axiomize.model_ir import ModelIR


def model(*, with_value=True):
    parameter = {"name": "k", "bounds": [0.0, 1.0]}
    if with_value:
        parameter["value"] = 0.5
    return ModelIR.from_dict({
        "schema_version": "1.0", "domain": "physics",
        "name": "native-engine-test", "family": "ode",
        "variables": [{"name": "x", "initial": 1.0}],
        "parameters": [parameter],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    })


def test_parameters_are_recovered_from_actual_model():
    assert engine._parameter_values(model()) == {"k": 0.5}
    assert engine._parameter_values(model(), {"k": 0.8}) == {"k": 0.8}


@pytest.mark.parametrize("value, fragment", [
    ({"unknown": 0.2}, "unknown parameter"),
    ({"k": -0.1}, "below lower bound"),
    ({"k": 1.1}, "above upper bound"),
])
def test_parameter_override_must_be_named_and_in_bounds(value, fragment):
    with pytest.raises(ValueError, match=fragment):
        engine._parameter_values(model(), value)


def test_parameters_cannot_be_invented_if_not_declared():
    with pytest.raises(ValueError, match="has no value"):
        engine._parameter_values(model(with_value=False))


def test_scalar_expression_resolves_existing_parameter_only():
    assert engine._resolve_scalar("k", {"k": 0.5}, name="rate") == 0.5
    assert engine._resolve_scalar(1.25, {}, name="rate") == 1.25
    with pytest.raises(ValueError, match="references unknown parameter"):
        engine._resolve_scalar("absent", {"k": 0.5}, name="rate")


@pytest.mark.parametrize("bad", [
    {"states": [1], "time": [0.0]},
    {"states": {"x": [1]}, "time": "wrong"},
    {"states": {}, "time": [0.0]},
    {"states": {"x": [[[1]]]}, "time": [0.0]},
    {"states": {"x": [[1], [2]]}, "time": [0.0]},
    {"states": {"x": [[1, 2]], "y": [[1]]}, "time": [0.0]},
])
def test_unflattenable_data_does_not_fabricate_validation_provenance(bad):
    assert engine._flatten_validation_proxy(bad) is bad


def test_multientity_validation_flattens_axes_without_losing_order():
    sample = {
        "status": "PASS",
        "time": [0.0, 1.0],
        "states": {"x": [[1.0, 2.0], [3.0, 4.0]], "y": [[5.0, 6.0], [7.0, 8.0]]},
    }
    flattened = engine._flatten_validation_proxy(sample)
    assert flattened is not sample
    assert flattened["time"] == [0.0, 0.0, 1.0, 1.0]
    assert flattened["states"]["x"] == [1.0, 2.0, 3.0, 4.0]
    assert flattened["states"]["y"] == [5.0, 6.0, 7.0, 8.0]
    assert sample["states"]["x"] == [[1.0, 2.0], [3.0, 4.0]]


def test_single_entity_state_does_not_need_axis_proxy():
    raw = {"time": [0.0, 1.0], "states": {"x": [1.0, 0.5]}}
    assert engine._flatten_validation_proxy(raw) is raw


def test_finalizer_preserves_explicit_tool_route_without_validation():
    outcome = {"status": "TOOL_ROUTE_REQUIRED"}
    called = []
    def validator(*args, **kwargs):
        called.append(True)
    assert engine._finalize(model(), outcome, validator) is outcome
    assert not called


def test_finalizer_downgrades_failed_scientific_constraints():
    outcome = {"status": "PASS"}
    returned = engine._finalize(model(), outcome, lambda *args, **kwargs: {
        "status": "FAIL", "scientific_constraints": [{"status": "FAIL", "name": "positivity"}],
    })
    assert returned["status"] == "FAIL"
    assert returned["validation"]["scientific_constraints"][0]["name"] == "positivity"


def test_finalizer_does_not_discard_validator_exception():
    def bad_validator(*args, **kwargs):
        raise RuntimeError("invalid evidence stream")
    result = engine._finalize(model(), {"status": "PASS"}, bad_validator)
    assert result["status"] == "FAIL"
    assert result["validation"]["status"] == "FAIL"
    assert "RuntimeError: invalid evidence stream" in result["validation"]["checks"][0]["detail"]


def test_finalizer_keeps_pass_when_validated():
    result = engine._finalize(model(), {"status": "PASS"}, lambda *args, **kwargs: {"status": "PASS"})
    assert result["status"] == "PASS"
    assert result["validation"]["status"] == "PASS"


@pytest.mark.parametrize("configuration, expected", [
    ({"boundary_conditions": "unknown"}, {}),
    ({"boundary_conditions": {"x": {"left": {"type": "neumann"}}}}, {"left": {"type": "neumann"}}),
    ({"boundary_conditions": {"left": {"type": "dirichlet"}}}, {"left": {"type": "dirichlet"}}),
    ({"boundary_conditions": {"unknown": 1}}, {}),
])
def test_boundary_metadata_never_invents_missing_conditions(configuration, expected):
    assert engine._boundary_spec(model(), configuration, "x") == expected


@pytest.mark.parametrize("value, prior, bounds", [
    (-1.0, None, (0.0, None)),
    (2.0, None, (None, 1.0)),
    (-1.0, {"dist": "halfnormal", "sigma": 1.0}, None),
    (1.0, {"dist": "halfnormal", "sigma": -1.0}, None),
    (2.0, {"dist": "uniform", "low": 0.0, "high": 1.0}, None),
    (0.0, {"dist": "lognormal", "sigma": 1.0}, None),
])
def test_prior_rejects_out_of_support_values(value, prior, bounds):
    assert engine._log_prior(value, prior, bounds, 0.5) == -math.inf


@pytest.mark.parametrize("prior, fragment", [
    ({"dist": "normal", "sigma": 0.0}, "normal prior sigma"),
    ({"dist": "lognormal", "sigma": 0.0}, "lognormal prior sigma"),
    ({"dist": "not-a-distribution"}, "unsupported builtin prior"),
])
def test_invalid_prior_fails_loudly(prior, fragment):
    with pytest.raises(ValueError, match=fragment):
        engine._log_prior(0.5, prior, None, 0.5)


@pytest.mark.parametrize("prior", [
    None,
    {"dist": "normal", "mu": 0.5, "sigma": 1.0},
    {"dist": "halfnormal", "sigma": 1.0},
    {"dist": "uniform", "low": 0.0, "high": 1.0},
    {"dist": "lognormal", "mu": 0.0, "sigma": 1.0},
])
def test_supported_prior_distributions_have_finite_log_density(prior):
    assert math.isfinite(engine._log_prior(0.5, prior, (0.0, 1.0), 0.5))


@pytest.mark.parametrize("mode, expected", [
    ("mean", 2.5),
    ("min", 1.0),
    ("max", 4.0),
    ("final_mean", 3.5),
    ("final", 3.5),
])
def test_real_coupling_reductions_preserve_observed_measurements(mode, expected):
    assert engine._reduction(np.array([[1.0, 2.0], [3.0, 4.0]]), mode) == expected


def test_final_reduction_of_time_series_returns_last_sample():
    assert engine._reduction([1.0, 2.0, 3.0], "final") == 3.0
    assert engine._reduction([1.0, 2.0, 3.0], "final_mean") == 3.0


def test_empty_coupling_evidence_is_rejected():
    with pytest.raises(ValueError, match="empty coupled state"):
        engine._reduction([], "mean")


def test_compile_mathematical_expression_without_exec():
    numeric = engine._compile_expression("sin(x)+k", ["x", "k"])
    assert math.isclose(float(numeric(0.0, 0.25)), 0.25, abs_tol=1e-12)


@pytest.mark.parametrize("expression", [
    "__import__('os').system('true')",
    "untracked_symbol + x",
])
def test_expression_parser_refuses_unknown_code_and_symbols(expression):
    with pytest.raises((ValueError, SyntaxError, TypeError)):
        engine._compile_expression(expression, ["x"])
