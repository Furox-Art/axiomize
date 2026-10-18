"""Direct scientific constraints, uncertainty decomposition and design checks."""
from __future__ import annotations

import math

import pytest

from axiomize import general_engine_core as core
from axiomize.model_ir import ConstraintSpec, ModelIR


def decay(k=0.4):
    return ModelIR.from_dict({
        "schema_version": "1.0", "domain": "physics", "name": "physical-decay",
        "family": "ode", "independent_variable": "t",
        "variables": [{"name": "x", "initial": 1.0}],
        "parameters": [{"name": "k", "value": k}],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    })


def c_spec(relation, threshold, *, upper=None, tolerance=1e-8):
    return ConstraintSpec.from_dict({
        "name": "known-physical-constraint", "expression": "x",
        "relation": relation, "threshold": threshold, "upper": upper,
        "tolerance": tolerance, "scientific_basis": "explicitly stated physical limit",
    })


@pytest.mark.parametrize("relation, threshold, upper, expected", [
    ("ge", 0.0, None, "PASS"),
    ("ge", 0.2, None, "FAIL"),
    ("le", 2.0, None, "PASS"),
    ("le", -0.2, None, "FAIL"),
    ("eq", 0.0, None, "PASS"),
    ("eq", 0.05, None, "FAIL"),
    ("between", -0.1, 0.1, "PASS"),
    ("between", -0.1, -0.05, "FAIL"),
])
def test_actual_constraint_evaluation_respects_relation(relation, threshold, upper, expected):
    checked = core._evaluate_constraint(
        c_spec(relation, threshold, upper=upper), [{"x": 0.0}]
    )
    assert checked["status"] == expected
    assert checked["relation"] == relation
    assert checked["scientific_basis"] == "explicitly stated physical limit"
    assert checked["detail"]


def test_constraint_tolerance_applies_at_declared_boundary():
    constraint = c_spec("eq", 1.0, tolerance=0.001)
    inside = core._evaluate_constraint(constraint, [{"x": 1.0001}])
    outside = core._evaluate_constraint(constraint, [{"x": 1.01}])
    assert inside["status"] == "PASS"
    assert outside["status"] == "FAIL"


def test_nonfinite_constraint_value_refuses_false_pass():
    observed = core._evaluate_constraint(c_spec("ge", 0), [{"x": float("nan")}])
    assert observed["status"] == "FAIL"
    assert "non-finite" in observed["detail"]


def test_constraint_context_uses_observed_trajectory_instead_of_initial_condition():
    m = decay()
    measured = {
        "time": [0, 1, 2],
        "states": {"x": [1.0, 0.7, 0.4]},
        "parameters": {"k": 0.5},
    }
    contexts = core._constraint_context(m, measured)
    assert [row["x"] for row in contexts] == [1.0, 0.7, 0.4]
    assert [row["t"] for row in contexts] == [0.0, 1.0, 2.0]
    assert all(row["k"] == 0.5 for row in contexts)


def test_constraint_context_supports_single_result_and_unmeasured_initial_state():
    m = decay()
    assert core._constraint_context(m, {"states": {"x": 0.7}})[0]["x"] == 0.7
    initial = core._constraint_context(m, None)
    assert initial == [{"k": 0.4, "x": 1.0}]


def test_validity_scan_executes_real_parameter_values_and_records_interval():
    result = core.validity_scan(
        decay(), parameter="k", values=[0.0, 0.2, 0.5],
        t_span=(0.0, 1.0), points=14, approve_heavy=True,
    )
    assert result["status"] == "PASS"
    assert result["parameter"] == "k"
    assert len(result["evaluations"]) == 3
    assert [row["value"] for row in result["evaluations"]] == [0.0, 0.2, 0.5]
    assert all(row["status"] == "PASS" for row in result["evaluations"])
    assert result["valid_interval_observed"] == [0.0, 0.5]


def test_validity_scan_has_no_invented_interval_after_failed_solver(monkeypatch):
    monkeypatch.setattr(core, "simulate_model", lambda *args, **kwargs: {"status": "FAIL"})
    result = core.validity_scan(
        decay(), parameter="k", values=[0.0, 0.5],
        t_span=(0.0, 1.0), points=14, approve_heavy=True,
    )
    assert result["valid_interval_observed"] is None
    assert len(result["evaluations"]) == 2
    assert all(r["status"] == "FAIL" for r in result["evaluations"])


def test_nondimensionalization_does_not_modify_original_IR():
    model = decay(0.4)
    before = model.to_dict()
    plan = core.nondimensionalization_plan(model)
    assert plan["applied"] is False
    assert plan["recommended"] is False
    assert plan["variable_scales"]["x"] == 1.0
    assert plan["parameter_scales"]["k"] == 0.4
    assert model.to_dict() == before


def test_nondimensionalization_flags_wide_dynamic_range_without_acting():
    m = decay(1e-8)
    result = core.nondimensionalization_plan(m)
    assert result["recommended"] is True
    assert result["dynamic_range"] >= 1e8
    assert result["applied"] is False


def test_uncertainty_sources_are_not_collapsed_into_one_confidence():
    report = core.split_uncertainty(
        residual_std=0.2, parameter_covariance=[[0.09, 0.0], [0.0, 0.16]]
    )
    assert report["aleatoric"]["estimate"] == pytest.approx(0.2)
    assert report["epistemic"]["estimate"] == pytest.approx(0.5)
    assert "separately" in report["note"]
    assert core.split_uncertainty()["epistemic"]["estimate"] is None


def test_real_experiment_design_ranks_larger_decay_times_as_more_informative():
    model = decay(0.4)
    report = core.rank_experiment_times(
        model, parameter="k", candidate_times=[0.0, 0.5, 1.0],
        horizon=1.0, approve_heavy=True,
    )
    assert report["status"] == "PASS"
    assert len(report["ranked_tests"]) == 3
    assert report["ranked_tests"][-1]["time"] == 0.0
    assert report["ranked_tests"][-1]["information_proxy"] == pytest.approx(0.0, abs=1e-8)
    assert [r["rank"] for r in report["ranked_tests"]] == [1, 2, 3]
    assert all(math.isfinite(r["information_proxy"]) for r in report["ranked_tests"])


def test_experiment_design_rejects_undeclared_parameter():
    with pytest.raises(ValueError, match="needs a baseline value"):
        core.rank_experiment_times(
            decay(), parameter="undeclared", candidate_times=[0.5],
            horizon=1.0, approve_heavy=True,
        )


def test_experiment_design_does_not_report_results_after_failed_sensitivity(monkeypatch):
    monkeypatch.setattr(core, "simulate_model", lambda *args, **kwargs: {"status": "FAIL"})
    output = core.rank_experiment_times(
        decay(), parameter="k", candidate_times=[0.5],
        horizon=1.0, approve_heavy=True,
    )
    assert output["status"] == "FAIL"
    assert "simulation failed" in output["detail"]
    assert "ranked_tests" not in output
