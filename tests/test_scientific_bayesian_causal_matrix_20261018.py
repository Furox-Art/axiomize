"""Direct native likelihood sampling and identified causal effect contracts.

Deterministic controlled test models are not represented as external evidence.
Identification assumptions must be supplied, never inferred by the adapter.
"""

from __future__ import annotations

import numpy as np
import pytest

from axiomize import advanced_family_engine as engine
from axiomize.model_ir import ModelIR


def bayesian(*, cfg=None, equation=None, parameters=None):
    metadata = {
        "data": {"x": [0.0, 1.0, 2.0, 3.0]},
        "observations": [0.0, 2.0, 4.0, 6.0],
        "mean_expression": "a*x", "sigma": 0.25,
        "draws": 80, "burn": 20, "proposal_scale": {"a": 0.15},
    }
    if cfg:
        metadata.update(cfg)
    return ModelIR.from_dict({
        "schema_version": "1.0", "domain": "general", "name": "direct-bayesian-model",
        "family": "bayesian", "variables": [{"name": "y", "role": "output", "initial": 0.0}],
        "parameters": parameters if parameters is not None else [{
            "name": "a", "value": 0.6, "fit": True,
            "prior": {"dist": "normal", "mu": 1.0, "sigma": 2.0},
        }],
        "equations": [equation if equation is not None else {
            "target": "y", "expression": "a*x", "kind": "observation",
        }],
        "metadata": {"bayesian": metadata},
    })


def infer(model, *, seed=23):
    return engine._infer_bayesian(model, t_span=(0.0, 1.0), points=40, parameter_overrides=None, seed=seed)


def test_direct_bayesian_likelihood_recovers_controlled_parameter_with_seed():
    first = infer(bayesian())
    second = infer(bayesian())
    assert first == second
    assert first["status"] == "PASS"
    assert first["solver"]["method"] == "multi_chain_random_walk_metropolis"
    assert first["posterior"]["a"]["mean"] == pytest.approx(2.0, abs=0.7)
    assert 0 <= first["diagnostics"]["acceptance_rate"] <= 1
    assert first["diagnostics"]["finite"] is True


def test_direct_bayesian_chain_exports_actual_draws_only_when_requested():
    result = infer(bayesian(cfg={"return_samples": True}))
    values = np.asarray(result["samples"]["a"])
    assert values.shape == (80 * result["diagnostics"]["chains"],)
    assert np.mean(values) == pytest.approx(result["posterior"]["a"]["mean"])
    assert np.quantile(values, 0.5) == pytest.approx(result["posterior"]["a"]["median"])


@pytest.mark.parametrize("override,match", [
    ({"observations": []}, "observations"),
    ({"observations": [1.0]}, "observations"),
    ({"observations": [[1.0, 2.0], [3.0, 4.0]]}, "observations"),
    ({"data": {"x": [0.0]}}, "must be finite scalar or match observations"),
    ({"sigma": "undefined"}, "sigma parameter name is unknown"),
    ({"draws": 10}, "draws must be"),
    ({"burn": -1}, "burn"),
    ({"sigma": 0}, "zero/invalid posterior"),
])
def test_bayesian_invalid_evidence_is_rejected_not_backfilled(override, match):
    with pytest.raises(ValueError, match=match):
        infer(bayesian(cfg=override))


def test_bayesian_missing_mean_expression_without_equation_is_refused():
    model = bayesian(cfg={"mean_expression": None}, equation={"target": "y", "kind": "update", "expression": "0"})
    with pytest.raises(ValueError, match="requires mean_expression"):
        infer(model)


def test_bayesian_without_sampled_parameters_is_refused():
    with pytest.raises(ValueError, match="at least one parameter"):
        infer(bayesian(parameters=[]))


def causal(*, cfg=None, identification=None):
    data = {
        "treat": [0.0, 1.0, 0.0, 1.0, 0.0, 1.0],
        "covariate": [1.0, 0.0, 2.0, 0.0, 3.0, 1.0],
    }
    data["outcome"] = [1 + 2 * a + 0.5 * b for a, b in zip(data["treat"], data["covariate"], strict=True)]
    metadata = {"treatment": "treat", "outcome": "outcome", "data": data,
                "covariates": ["covariate"], "intervention_values": [0.0, 1.0]}
    if identification is not None:
        metadata["identification"] = identification
    if cfg:
        metadata.update(cfg)
    return ModelIR.from_dict({
        "schema_version": "1.0", "domain": "general", "name": "controlled-adjustment-model",
        "family": "causal", "variables": [{"name": "out", "role": "output", "initial": 0.0}],
        "equations": [{"target": "out", "kind": "causal", "expression": "0"}],
        "metadata": {"causal": metadata},
    })


def estimate(model):
    return engine._estimate_causal(model, t_span=(0.0, 1.0), points=20, parameter_overrides=None, seed=37)


def test_unidentified_observations_cannot_be_renamed_causal_evidence():
    result = estimate(causal())
    assert result["status"] == "INSUFFICIENT_CAUSAL_EVIDENCE"
    assert "causal conclusion unavailable" in result["detail"]


def test_randomized_identification_permits_actual_adjusted_effect_and_do_predictions():
    result = estimate(causal(identification={"randomized": True}))
    assert result["status"] == "PASS", result
    assert result["causal_effect"]["estimate"] == pytest.approx(2.0, abs=1e-12)
    assert result["diagnostics"]["binary_treatment"] is True
    assert result["causal_effect"]["method"] == "aipw_doubly_robust"
    assert result["diagnostics"]["warnings"]
    assert result["diagnostics"]["n"] == 6
    assert len(result["counterfactuals"]) == 2
    difference = (result["counterfactuals"][1]["predicted_outcome_mean"]
                  - result["counterfactuals"][0]["predicted_outcome_mean"])
    assert difference == pytest.approx(2.0, abs=1e-12)
    assert "conditional" in result["causal_scope"]


def test_declared_adjustment_set_with_assumptions_is_necessary_for_nonrandomized_identification():
    result = estimate(causal(identification={"adjustment_set": ["covariate"],
                                                     "assumptions": ["no unmeasured confounding"]}))
    assert result["status"] == "PASS"
    assert result["causal_effect"]["estimate"] == pytest.approx(2.0)


@pytest.mark.parametrize("override, match", [
    ({"data": None}, "causal.data must be an object"),
    ({"treatment": "missing"}, "missing from data"),
    ({"covariates": "missing"}, "adjustment_set must be an array"),
    ({"data": {"treat": [0, 1, 0], "outcome": [1, 2]}}, "must be a 1D array"),
    ({"data": {"treat": [0, 1, 0], "outcome": [1, 2, 3]},
      "covariates": ["missing"]}, "missing from data"),
    ({"data": {"treat": [0, 1, 0], "outcome": [1, 2, 3], "covariate": [0, 1]},
      "covariates": ["covariate"]}, "must be a 1D array"),
])
def test_identified_causal_executor_refuses_incomplete_direct_data(override, match):
    with pytest.raises(ValueError, match=match):
        estimate(causal(cfg=override, identification={"randomized": True}))


def test_declared_empty_interventions_produce_no_fabricated_counterfactuals():
    result = estimate(causal(cfg={"intervention_values": []}, identification={"randomized": True}))
    assert result["status"] == "PASS"
    assert result["counterfactuals"] == []
