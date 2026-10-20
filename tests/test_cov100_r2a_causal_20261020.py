"""Round-2 coverage hardening for ``axiomize.causal_engine``.

Every test drives the real estimator/helpers and asserts observable scientific
behaviour (estimates, adjustment sets, typed refusals). Optional DAG and
identification branches are exercised through public estimation entry points;
only genuinely internal numeric helpers are called directly.
"""
from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from axiomize.causal_engine import _ols, _smd, estimate_causal_model
from axiomize.model_ir import ModelIR


def _model(
    *,
    causal: dict | None = None,
    parameters: list[dict] | None = None,
    identification: object | None = None,
) -> ModelIR:
    cfg: dict = {
        "treatment": "t",
        "outcome": "y",
        "data": {
            "t": [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0],
            "y": [1.0, 3.0, 1.0, 3.0, 1.0, 3.0, 1.0, 3.0],
        },
        "identification": {"randomized": True},
    }
    if causal:
        cfg.update(causal)
    if identification is not None:
        cfg["identification"] = identification
    payload = {
        "schema_version": "1.0",
        "domain": "general",
        "name": "cov100-causal",
        "family": "causal",
        "variables": [{"name": "out", "role": "output", "initial": 0.0}],
        "parameters": parameters or [{"name": "gain", "value": 1.0}],
        "equations": [{"target": "out", "kind": "causal", "expression": "0"}],
        "metadata": {"causal": cfg},
    }
    return ModelIR.from_dict(payload)


def _estimate(model: ModelIR, overrides: dict[str, float] | None = None) -> dict:
    return estimate_causal_model(
        model, t_span=(0.0, 1.0), points=20, parameter_overrides=overrides, seed=11
    )


def test_parameter_overrides_are_applied_to_the_reported_parameter_block():
    result = _estimate(_model(), {"gain": 2.5})
    assert result["status"] == "PASS"
    assert result["parameters"] == {"gain": 2.5}
    assert result["causal_effect"]["estimate"] == pytest.approx(2.0, abs=1e-12)


def test_unknown_parameter_override_is_refused_by_name():
    with pytest.raises(ValueError, match="unknown parameter overrides"):
        _estimate(_model(), {"nope": 1.0})


def test_parameter_without_value_is_refused():
    model = _model(parameters=[{"name": "gain"}])
    with pytest.raises(ValueError, match="has no value"):
        _estimate(model)


@pytest.mark.parametrize("override", [math.inf, -math.inf, math.nan])
def test_non_finite_parameter_override_is_refused(override: float):
    with pytest.raises(ValueError, match="must be finite"):
        _estimate(_model(), {"gain": override})


@pytest.mark.parametrize(
    ("data", "match"),
    [
        ({"t": [0.0, 1.0, 0.0]}, "missing from data"),
        ({"t": [0.0, 1.0, 0.0], "y": [1.0, 2.0]}, "must be a 1D array"),
        ({"t": [0.0, 1.0, 0.0, 1.0], "y": [1.0, 2.0, 3.0, 4.0, 5.0]}, "length mismatch"),
        ({"t": [0.0, 1.0, 0.0], "y": [1.0, math.nan, 3.0]}, "must be finite"),
        (["not", "an", "object"], "causal.data must be an object"),
    ],
)
def test_causal_vectors_require_matching_finite_rows(data: object, match: str):
    with pytest.raises(ValueError, match=match):
        _estimate(_model(causal={"data": data}))


def test_dag_adjustment_is_derived_from_parents_and_blocks_descendants():
    # The diamond rooted at the treatment forces the descendant walk to revisit
    # ``d``; a->t, a->y makes the backdoor parent the only valid observed
    # adjustment variable.
    edges = [
        ["t", "b"],
        ["t", "c"],
        ["b", "d"],
        ["c", "d"],
        {"source": "a", "target": "t"},
        {"source": "a", "target": "y"},
        {"source": "t", "target": "y"},
        {"source": "d", "target": "y"},
    ]
    data = {
        "a": [1.0, 0.0, 2.0, 0.0, 3.0, 1.0, 2.0, 0.0],
        "t": [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0],
        "y": [1.0, 3.0, 1.0, 3.0, 1.0, 3.0, 1.0, 3.0],
        "d": [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0],
    }
    model = _model(causal={"data": data, "identification": {"dag_edges": edges}})
    result = _estimate(model)
    assert result["status"] == "PASS"
    assert result["identification"]["dag_validated_acyclic"] is True
    assert result["identification"]["adjustment_set_used"] == ["a"]
    assert result["identification"]["randomized_or_interventional"] is False
    assert result["causal_effect"]["estimate"] == pytest.approx(2.0, abs=1e-9)


@pytest.mark.parametrize(
    ("edges", "match"),
    [
        ("t->y", "must be an array"),
        ([7], "must contain source and target"),
        (["t", "y"], "must contain source and target"),
        ([["t", ""]], "distinct non-empty"),
        ([["t", "t"]], "distinct non-empty"),
        ([["t", "y"], ["y", "t"]], "directed cycle"),
    ],
)
def test_malformed_dag_edges_are_refused(edges: object, match: str):
    model = _model(
        causal={"identification": {"identified_dag": True, "dag_edges": edges}},
        identification={"identified_dag": True, "dag_edges": edges},
    )
    with pytest.raises(ValueError, match=match):
        _estimate(model)


def test_continuous_treatment_uses_robust_linear_backdoor_adjustment():
    t = [-2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    y = [1.0 + 3.0 * value for value in t]
    model = _model(causal={"data": {"t": t, "y": y}})
    result = _estimate(model)
    assert result["status"] == "PASS"
    assert result["diagnostics"]["binary_treatment"] is False
    assert result["causal_effect"]["method"] == "robust_linear_backdoor_adjustment"
    assert result["causal_effect"]["estimate"] == pytest.approx(3.0, abs=1e-9)
    # A perfect linear relationship leaves zero residual variance, so the HC1
    # standard error and therefore the CI collapse onto the point estimate.
    assert result["causal_effect"]["ci95"] == pytest.approx([3.0, 3.0], abs=1e-9)
    assert result["causal_effect"]["residual_rmse"] == pytest.approx(0.0, abs=1e-9)
    assert result["solver"] == {"backend": "numpy", "method": "robust_linear_backdoor_adjustment"}
    assert result["diagnostics"]["warnings"] == []


def test_continuous_treatment_with_explicit_adjustment_still_estimates_effect():
    t = [-2.0, -1.0, 0.0, 1.0, 2.0, 3.0]
    a = [1.0, 0.0, 1.0, 0.0, 1.0, 0.0]
    y = [1.0 + 3.0 * tv + 10.0 * av for tv, av in zip(t, a, strict=True)]
    model = _model(
        causal={
            "data": {"t": t, "y": y, "a": a},
            "identification": {"adjustment_set": ["a"], "assumptions": ["exchangeability"]},
        }
    )
    result = _estimate(model)
    assert result["status"] == "PASS"
    assert result["identification"]["adjustment_set_used"] == ["a"]
    assert result["causal_effect"]["estimate"] == pytest.approx(3.0, abs=1e-9)


def test_non_object_identification_metadata_degrades_to_empty_mapping():
    model = _model(identification="not-an-object")
    result = _estimate(model)
    assert result["status"] == "INSUFFICIENT_CAUSAL_EVIDENCE"
    assert result["required_next_evidence"]


def test_non_object_causal_metadata_is_refused():
    model = _model()
    broken = dataclasses.replace(model, metadata={"causal": ["not", "an", "object"]})
    with pytest.raises(ValueError, match="metadata.causal must be an object"):
        _estimate(broken)


@pytest.mark.parametrize("cfg", [{"treatment": ""}, {"outcome": ""}])
def test_treatment_and_outcome_names_are_required(cfg: dict):
    with pytest.raises(ValueError, match="requires treatment and outcome"):
        _estimate(_model(causal=cfg))


@pytest.mark.parametrize("adjustment", [["t"], ["y"], ["t", "y"]])
def test_adjustment_set_cannot_contain_treatment_or_outcome(adjustment: list[str]):
    model = _model(
        identification={"adjustment_set": adjustment, "assumptions": ["exchangeability"]}
    )
    with pytest.raises(ValueError, match="cannot include treatment or outcome"):
        _estimate(model)


def test_adjustment_set_must_be_an_array_when_declared():
    model = _model(
        identification={"adjustment_set": "a", "assumptions": ["exchangeability"]}
    )
    with pytest.raises(ValueError, match="adjustment_set must be an array"):
        _estimate(model)


def test_adjustment_set_cannot_contain_post_treatment_descendants():
    data = {
        "t": [0.0, 1.0, 0.0, 1.0],
        "y": [1.0, 3.0, 1.0, 3.0],
        "m": [0.5, 0.5, 0.5, 0.5],
    }
    model = _model(
        causal={
            "data": data,
            "identification": {
                "adjustment_set": ["m"],
                "assumptions": ["exchangeability"],
                "dag_edges": [["t", "m"]],
            },
        }
    )
    with pytest.raises(ValueError, match="descendants of treatment"):
        _estimate(model)


def test_non_finite_intervention_value_is_refused():
    model = _model(causal={"intervention_values": [0.0, math.inf]})
    with pytest.raises(ValueError, match="intervention values must be finite"):
        _estimate(model)


def test_weighted_ols_matches_ols_on_duplicated_observations():
    X = np.array([[1.0, 1.0], [1.0, 2.0], [1.0, 3.0], [1.0, 4.0]])
    y = np.array([2.0, 4.1, 5.9, 8.2])
    weights = np.array([2.0, 1.0, 1.0, 1.0])
    beta, cov, residual = _ols(X, y, weights=weights)
    duplicated = np.vstack([X[0], X[0], X[1], X[2], X[3]])
    duplicated_y = np.concatenate([[y[0], y[0]], y[1:]])
    reference, *_ = np.linalg.lstsq(duplicated, duplicated_y, rcond=None)
    assert beta == pytest.approx(reference, abs=1e-10)
    assert cov.shape == (2, 2)
    assert np.all(np.isfinite(cov))
    assert residual == pytest.approx(y - X @ beta, abs=1e-12)
    assert float(residual @ residual) == pytest.approx(
        float(np.sum((y - X @ beta) ** 2)), abs=1e-9
    )


def test_standardized_mean_difference_is_infinite_without_both_groups():
    value = _smd(np.array([1.0, 2.0, 3.0]), np.array([1.0, 1.0, 1.0]))
    assert value == math.inf
