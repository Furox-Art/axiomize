"""Exact DAG and estimand diagnostics on observed (not proxy) causal data."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.causal_engine import (
    _ancestors,
    _dag,
    _derive_adjustment,
    _descendants,
    _finite_vector,
    _ols,
    _parameter_values,
    _smd,
    estimate_causal_model,
)
from axiomize.model_ir import ModelFamily, ModelIR, ParameterSpec


def model(causal=None, parameters=None):
    t = np.asarray([0.0, 1.0] * 6)
    cov = np.arange(12, dtype=float) / 10.0
    y = 1.0 + 2.0 * t + 3.0 * cov
    cfg = (
        causal
        if causal is not None
        else {
            "identification": {"randomized": True},
            "treatment": "t",
            "outcome": "y",
            "data": {"t": t.tolist(), "y": y.tolist(), "z": cov.tolist()},
        }
    )
    return ModelIR(
        name="observed",
        domain="epidemiology",
        family=ModelFamily.CAUSAL,
        variables=[],
        parameters=parameters or [],
        equations=[],
        metadata={"causal": cfg},
    )


def execute(m, overrides=None):
    return estimate_causal_model(
        m,
        t_span=(0.0, 1.0),
        points=8,
        parameter_overrides=overrides,
        seed=7,
    )


@pytest.mark.parametrize(
    ("overrides", "params", "message"),
    [
        ({"unregistered": 1.0}, None, "unknown parameter overrides"),
        ({}, [ParameterSpec("k", None)], "has no value"),
        ({"k": float("nan")}, [ParameterSpec("k", 1.0)], "must be finite"),
        ({"k": float("inf")}, [ParameterSpec("k", 1.0)], "must be finite"),
    ],
)
def test_causal_parameter_values_never_guess_missing_estimates(overrides, params, message):
    with pytest.raises(ValueError, match=message):
        _parameter_values(model(parameters=params), overrides)


def test_causal_parameter_overrides_preserve_explicit_finite_value():
    result = _parameter_values(model(parameters=[ParameterSpec("k", 1.0)]), {"k": 2.0})
    assert result == {"k": 2.0}


@pytest.mark.parametrize(
    ("data", "name", "n", "message"),
    [
        ({}, "missing", None, "missing from data"),
        ({"y": [1.0, 2.0]}, "y", None, "at least 3"),
        ({"y": [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]}, "y", None, "1D array"),
        ({"y": [1.0, 2.0, 3.0]}, "y", 4, "length mismatch"),
        ({"y": [1.0, float("nan"), 3.0]}, "y", None, "must be finite"),
    ],
)
def test_causal_observations_must_be_finite_one_dimensional_and_direct(data, name, n, message):
    with pytest.raises(ValueError, match=message):
        _finite_vector(data, name, n=n)


@pytest.mark.parametrize(
    ("edges", "pattern"),
    [
        ("t->y", "edges must be an array"),
        ([["x"]], "must contain source"),
        ([["x", "x"]], "distinct non-empty"),
        ([["t", "y"], ["y", "t"]], "directed cycle"),
        ([{"source": "x", "target": "x"}], "distinct non-empty"),
    ],
)
def test_causal_dag_refuses_invalid_or_cyclic_declarations(edges, pattern):
    with pytest.raises(ValueError, match=pattern):
        _dag(edges)


def test_named_dag_edges_and_ancestor_descendant_sets_agree():
    parents, children = _dag(
        [
            {"source": "z", "target": "t"},
            {"source": "z", "target": "y"},
            {"source": "t", "target": "y"},
            {"source": "z", "target": "u"},
        ]
    )
    assert _ancestors("y", parents) == {"z", "t"}
    assert _descendants("z", children) == {"t", "y", "u"}
    assert _derive_adjustment("t", "y", parents, children, {"z", "t", "y"}) == ["z"]


def test_dag_adjustment_cannot_use_unmeasured_proxy_as_measured_covariate():
    parents, children = _dag([["unmeasured", "t"], ["unmeasured", "y"], ["t", "y"]])
    adjustment = _derive_adjustment("t", "y", parents, children, {"t", "y"})
    assert adjustment == []


def test_causal_weighted_ols_has_consistent_exact_linear_estimate():
    x = np.column_stack([np.ones(5), np.arange(5, dtype=float)])
    y = 1.0 + 2.0 * x[:, 1]
    coefficient, cov, residual = _ols(x, y, weights=np.asarray([1.0, 2.0, 3.0, 2.0, 1.0]))
    np.testing.assert_allclose(coefficient, [1.0, 2.0], atol=1e-12)
    np.testing.assert_allclose(residual, 0.0, atol=1e-12)
    assert cov.shape == (2, 2)


def test_smd_summaries_distinguish_absent_control_group():
    x = np.asarray([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    single_arm = np.ones(6)
    assert _smd(x, single_arm) == math.inf


def test_weighted_smd_is_finite_when_both_treatment_arms_exist():
    x = np.asarray([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    t = np.asarray([0.0, 1.0, 0.0, 1.0, 0.0, 1.0])
    assert math.isfinite(_smd(x, t))
    assert math.isfinite(_smd(x, t, np.asarray([1.0, 2.0, 1.0, 2.0, 1.0, 2.0])))


@pytest.mark.parametrize(
    ("cfg", "pattern"),
    [
        ({"data": []}, "causal.data"),
        ({"treatment": "", "outcome": "y", "data": {}}, "treatment and outcome"),
        (
            {
                "treatment": "t",
                "outcome": "y",
                "data": {"t": [0.0, 1.0, 0.0], "y": [1.0, 2.0, 3.0]},
                "identification": {"randomized": True, "adjustment_set": "invalid"},
            },
            "must be an array",
        ),
    ],
)
def test_causal_inference_rejects_malformed_study_config(cfg, pattern):
    with pytest.raises(ValueError, match=pattern):
        execute(model(cfg))


@pytest.mark.parametrize("raw", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_intervention_predictions_refused_before_publishing_claim(raw):
    m = model()
    m.metadata["causal"]["intervention_values"] = [0.0, raw]
    with pytest.raises(ValueError, match="intervention values must be finite"):
        execute(m)


def test_randomized_direct_binary_outcome_reports_observed_effect_with_interval():
    actual = execute(model())
    assert actual["status"] == "PASS"
    assert actual["diagnostics"]["binary_treatment"] is True
    assert actual["causal_effect"]["method"] == "aipw_unadjusted_randomized"
    assert math.isfinite(actual["causal_effect"]["std_error"])
    assert all(math.isfinite(v) for v in actual["causal_effect"]["ci95"])
    assert "positivity" in actual["causal_effect"]


def test_identification_scope_remains_explicit_not_a_unconditional_causal_proof():
    actual = execute(model())
    assert "conditional on" in actual["causal_scope"]
    assert actual["identification"]["randomized_or_interventional"] is True
