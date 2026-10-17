"""Real event-driven integration and explicitly identified causal contrasts."""

from __future__ import annotations

import numpy as np
import pytest

from axiomize.advanced_family_engine import (
    _estimate_causal,
    _reduction,
    _simulate_hybrid,
)
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, VariableSpec


def _model(family, *, variables=(), equations=(), metadata=None):
    return ModelIR(
        name="direct-check",
        domain="physics",
        family=family,
        variables=list(variables),
        parameters=[],
        equations=list(equations),
        metadata=metadata or {},
    )


def _simulate(fn, m):
    return fn(m, t_span=(0.0, 0.5), points=5, parameter_overrides=None, seed=17)


def test_hybrid_event_reset_preserves_actual_piecewise_trajectory():
    m = _model(
        ModelFamily.HYBRID,
        variables=[VariableSpec("x", initial=0.0)],
        equations=[EquationSpec("x", "1")],
        metadata={
            "hybrid": {
                "events": [{"name": "reset_at_threshold", "expression": "x-0.2", "reset": {"x": "0"}, "direction": 1.0}]
            }
        },
    )
    result = _simulate(_simulate_hybrid, m)
    assert result["status"] == "PASS", result
    events = result["events"]
    assert len(events) == 2
    assert [e["name"] for e in events] == ["reset_at_threshold"] * 2
    np.testing.assert_allclose([e["time"] for e in events], [0.2, 0.4], atol=1e-6)
    for event in events:
        assert event["state_after"]["x"] == pytest.approx(0.0)
    assert result["states"]["x"][-1] == pytest.approx(0.1, abs=1e-5)


def test_continuous_hybrid_does_not_invent_unrequested_events():
    m = _model(ModelFamily.HYBRID, variables=[VariableSpec("x", initial=1.0)], equations=[EquationSpec("x", "-x")])
    out = _simulate(_simulate_hybrid, m)
    assert out["status"] == "PASS", out
    assert out["events"] == []
    np.testing.assert_allclose(out["states"]["x"], np.exp(-np.asarray(out["time"])), atol=1e-6)


@pytest.mark.parametrize(
    ("cfg", "equations", "variables", "error"),
    [
        ({}, [], [VariableSpec("x", initial=1.0)], "missing derivative equations"),
        ({"hybrid": "bad"}, [EquationSpec("x", "0")], [VariableSpec("x", initial=1.0)], "metadata.hybrid"),
        (
            {"hybrid": {"events": "bad"}},
            [EquationSpec("x", "0")],
            [VariableSpec("x", initial=1.0)],
            "events must be an array",
        ),
        (
            {"hybrid": {"events": [{"reset": {"x": "0"}}]}},
            [EquationSpec("x", "0")],
            [VariableSpec("x", initial=1.0)],
            "requires expression",
        ),
        (
            {"hybrid": {"events": [{"expression": "x-1", "reset": []}]}},
            [EquationSpec("x", "0")],
            [VariableSpec("x", initial=1.0)],
            "reset must be an object",
        ),
        (
            {"hybrid": {"events": [{"expression": "x-1", "reset": {"unknown": "0"}}]}},
            [EquationSpec("x", "0")],
            [VariableSpec("x", initial=1.0)],
            "unknown states",
        ),
        ({}, [EquationSpec("x", "0")], [VariableSpec("x")], "finite initial"),
    ],
)
def test_hybrid_refuses_unrequested_or_unphysical_execution(cfg, equations, variables, error):
    m = _model(ModelFamily.HYBRID, variables=variables, equations=equations, metadata=cfg)
    with pytest.raises(ValueError, match=error):
        _simulate(_simulate_hybrid, m)


def _causal_data():
    # Nontrivial nonrandomized treatment/covariate relation. Direct generated
    # data have an exactly identifiable linear backdoor coefficient of 2.
    covariate = np.asarray([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
    treatment = np.asarray([0.0, 2.0, 1.0, 4.0, 5.0, 3.0, 8.0, 6.0])
    outcome = 1.0 + 2.0 * treatment + 3.0 * covariate
    return {"t": treatment.tolist(), "y": outcome.tolist(), "z": covariate.tolist()}


def test_identified_backdoor_adjustment_recovers_exact_ols_effect():
    m = _model(
        ModelFamily.CAUSAL,
        metadata={
            "causal": {
                "identification": {"adjustment_set": ["z"], "assumptions": ["conditional exchangeability"]},
                "data": _causal_data(),
                "treatment": "t",
                "outcome": "y",
                "intervention_values": [0.0, 1.0, 5.0],
            }
        },
    )
    r = _simulate(_estimate_causal, m)
    assert r["status"] == "PASS", r
    assert r["causal_effect"]["estimate"] == pytest.approx(2.0, abs=1e-10)
    assert r["causal_effect"]["std_error"] == pytest.approx(0.0, abs=1e-10)
    assert r["diagnostics"]["n"] == 8
    assert r["identification"]["adjustment_set_used"] == ["z"]
    assert r["diagnostics"]["binary_treatment"] is False
    assert len(r["counterfactuals"]) == 3
    assert r["counterfactuals"][1]["predicted_outcome_mean"] - r["counterfactuals"][0][
        "predicted_outcome_mean"
    ] == pytest.approx(2.0)


def test_unidentified_causal_model_must_not_claim_intervention_effect():
    m = _model(
        ModelFamily.CAUSAL,
        metadata={
            "causal": {
                "data": _causal_data(),
                "treatment": "t",
                "outcome": "y",
            }
        },
    )
    out = _simulate(_estimate_causal, m)
    assert out["status"] == "INSUFFICIENT_CAUSAL_EVIDENCE"
    assert "causal_effect" not in out


@pytest.mark.parametrize(
    ("cfg", "error"),
    [
        ({"causal": "bad"}, "metadata.causal"),
        ({"causal": {"identification": {"randomized": True}, "data": []}}, "causal.data"),
        (
            {
                "causal": {
                    "identification": {"randomized": True},
                    "data": _causal_data(),
                    "treatment": "missing",
                    "outcome": "y",
                }
            },
            "missing from data",
        ),
        (
            {
                "causal": {
                    "identification": {"randomized": True},
                    "data": {"t": [0.0, 1.0], "y": [1.0, 2.0]},
                    "treatment": "t",
                    "outcome": "y",
                }
            },
            "at least 3",
        ),
        (
            {
                "causal": {
                    "identification": {"adjustment_set": "z", "randomized": True},
                    "data": _causal_data(),
                    "treatment": "t",
                    "outcome": "y",
                }
            },
            "must be an array",
        ),
        (
            {
                "causal": {
                    "identification": {"randomized": True, "adjustment_set": ["z"]},
                    "data": {"t": [0, 1, 2], "y": [0, 1, 2]},
                    "treatment": "t",
                    "outcome": "y",
                }
            },
            "missing from data",
        ),
    ],
)
def test_causal_analysis_rejects_missing_identification_or_data(cfg, error):
    with pytest.raises(ValueError, match=error):
        _simulate(_estimate_causal, _model(ModelFamily.CAUSAL, metadata=cfg))


@pytest.mark.parametrize(
    ("raw", "mode", "expected"),
    [
        ([1.0, 3.0], "mean", 2.0),
        ([1.0, 3.0], "max", 3.0),
        ([1.0, 3.0], "min", 1.0),
        ([[1.0, 2.0], [3.0, 4.0]], "final_mean", 3.5),
        ([1.0, 3.0], "final_mean", 3.0),
        ([[1.0, 2.0], [3.0, 4.0]], "final", 3.5),
        ([1.0, 3.0], "final", 3.0),
    ],
)
def test_multiphysics_reduction_obeys_declared_statistic(raw, mode, expected):
    assert _reduction(raw, mode) == pytest.approx(expected)


def test_empty_multiphysics_state_is_rejected():
    with pytest.raises(ValueError, match="empty coupled state"):
        _reduction([], "mean")
