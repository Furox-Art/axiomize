"""Direct causal DAG and doubly robust AIPW estimator tests."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.causal_engine import estimate_causal_model
from axiomize.model_ir import ModelFamily, ModelIR


def _data() -> dict[str, list[float]]:
    treatment = np.asarray([i % 2 for i in range(24)], dtype=float)
    covariate = np.asarray([(i * 7) % 11 for i in range(24)], dtype=float) / 10.0
    outcome = 1.0 + 2.0 * treatment + 3.0 * covariate
    return {"t": treatment.tolist(), "y": outcome.tolist(), "z": covariate.tolist()}


def _run(identification, data=None):
    model = ModelIR(
        name="binary",
        domain="epidemiology",
        family=ModelFamily.CAUSAL,
        variables=[],
        parameters=[],
        equations=[],
        metadata={
            "causal": {"treatment": "t", "outcome": "y", "data": data or _data(), "identification": identification}
        },
    )
    return estimate_causal_model(model, t_span=(0.0, 1.0), points=5, parameter_overrides=None, seed=17)


def test_binary_randomized_outcome_uses_real_aipw_not_ols_proxy():
    data = _data()
    # Under the explicit randomized/no-confounding scenario, potential outcome
    # is independent of z. The observational z-effect is tested separately.
    t = np.asarray(data["t"])
    data["y"] = (1.0 + 2.0 * t).tolist()
    result = _run({"randomized": True}, data=data)
    assert result["status"] == "PASS", result
    effect = result["causal_effect"]
    assert effect["method"] == "aipw_unadjusted_randomized"
    assert effect["estimate"] == pytest.approx(2.0, abs=1e-10)
    assert effect["estimators"]["outcome_regression"]["estimate"] == pytest.approx(2.0, abs=1e-10)
    assert effect["effective_sample_size_ipw"] == pytest.approx(24.0)
    assert result["diagnostics"]["binary_treatment"] is True


def test_binary_backdoor_dag_derives_adjustment_and_estimates_known_effect():
    result = _run({"dag_edges": [["z", "t"], ["z", "y"], ["t", "y"]], "assumptions": ["exchangeability"]})
    assert result["status"] == "PASS", result
    assert result["identification"]["dag_validated_acyclic"] is True
    assert result["identification"]["adjustment_set_used"] == ["z"]
    assert result["causal_effect"]["method"] == "aipw_doubly_robust"
    assert result["causal_effect"]["estimate"] == pytest.approx(2.0, abs=1e-8)
    assert "z" in result["causal_effect"]["balance"]["after_ipw"]
    assert result["causal_effect"]["effective_sample_size_ipw"] > 0
    assert all(math.isfinite(x) for x in result["causal_effect"]["ci95"])


@pytest.mark.parametrize(
    ("identification", "pattern"),
    [
        ({"dag_edges": [["t", "y"], ["y", "t"]]}, "directed cycle"),
        ({"dag_edges": [["t", "t"]]}, "distinct non-empty"),
        ({"dag_edges": "invalid"}, "DAG edges must be an array"),
        ({"dag_edges": [["t"]]}, "edge must contain"),
        ({"dag_edges": [["t", "z"], ["z", "y"]], "adjustment_set": ["z"]}, "descendants of treatment"),
        ({"randomized": True, "adjustment_set": ["t"]}, "cannot include treatment"),
        ({"randomized": True, "adjustment_set": ["y"]}, "cannot include treatment"),
        ({"randomized": True, "adjustment_set": ["unknown"]}, "missing from data"),
        ({"randomized": True, "adjustment_set": "z"}, "must be an array"),
    ],
)
def test_invalid_dag_or_post_treatment_adjustment_does_not_generate_effect(identification, pattern):
    with pytest.raises(ValueError, match=pattern):
        _run(identification)


def test_unidentified_data_do_not_become_claimed_causal_effect():
    result = _run({})
    assert result["status"] == "INSUFFICIENT_CAUSAL_EVIDENCE"
    assert "causal_effect" not in result
    assert result["required_next_evidence"]


@pytest.mark.parametrize(
    ("replacement", "pattern"),
    [
        ({"y": [1.0, 2.0, 3.0]}, "length mismatch"),
        ({"y": [float("nan")] * 24}, "must be finite"),
        ({"t": [0.0, 1.0, 0.0]}, "length mismatch"),
    ],
)
def test_invalid_clinical_inputs_are_not_silently_imputed(replacement, pattern):
    dataset = _data()
    dataset.update(replacement)
    with pytest.raises(ValueError, match=pattern):
        _run({"randomized": True}, data=dataset)
