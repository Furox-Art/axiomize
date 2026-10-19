"""Run every registered model family and verify stress failures cannot be hidden."""
from __future__ import annotations

import pytest

from axiomize import scientific_stress as stress
from axiomize.model_ir import ModelFamily


def test_every_real_model_family_and_crosscutting_check_passes():
    result = stress.run_stress_matrix()
    assert result["status"] == "PASS", result
    assert result["passed"] == result["total"] == len(ModelFamily) + 1
    assert set(result["families_covered"]) == {family.value for family in ModelFamily}
    assert all(row["status"] == "PASS" for row in result["results"])
    assert result["elapsed_s"] < 120.0
    assert result["results"][-1]["name"] == "cross_cutting_contracts"


def test_synthetic_failure_injection_must_not_claim_scientific_success(monkeypatch):
    original = stress._execute_family

    def checked_executor(family, model):
        if family is ModelFamily.STOCHASTIC:
            raise ArithmeticError("deliberately corrupt trajectory")
        original(family, model)

    monkeypatch.setattr(stress, "_execute_family", checked_executor)
    result = stress.run_stress_matrix()
    assert result["status"] == "FAIL"
    assert result["passed"] == result["total"] - 1
    failure = next(row for row in result["results"] if row["name"] == "family:stochastic")
    assert failure["status"] == "FAIL"
    assert "ArithmeticError" in failure["error"]


def test_missing_model_family_fails_before_any_simulation(monkeypatch):
    actual = stress._models

    def incomplete_catalog():
        models = actual()
        models.pop(ModelFamily.PDE)
        return models

    monkeypatch.setattr(stress, "_models", incomplete_catalog)
    result = stress.run_stress_matrix()
    assert result["status"] == "FAIL"
    assert "pde" in result["detail"]


def test_crosscutting_failed_falsification_is_recorded(monkeypatch):
    def refuse(*args):
        raise ValueError("constraint evidence missing")

    monkeypatch.setattr(stress, "_edge_contracts", refuse)
    result = stress.run_stress_matrix()
    assert result["status"] == "FAIL"
    row = result["results"][-1]
    assert row["name"] == "cross_cutting_contracts"
    assert "ValueError" in row["error"]


def test_per_case_budget_is_an_actual_gate(monkeypatch):
    monkeypatch.setattr(stress, "_CASE_BUDGET_S", -1.0)
    result = stress.run_stress_matrix()
    assert result["status"] == "FAIL"
    assert all(
        row["status"] == "FAIL"
        for row in result["results"] if row["name"].startswith("family:")
    )
    assert any("runtime budget exceeded" in row["error"] for row in result["results"])


def test_total_budget_is_an_actual_gate(monkeypatch):
    monkeypatch.setattr(stress, "_TOTAL_BUDGET_S", -1.0)
    result = stress.run_stress_matrix()
    assert result["status"] == "FAIL"
    assert result["results"][-1]["name"] == "total_runtime_budget"


@pytest.mark.parametrize("family, field", [
    (ModelFamily.ALGEBRAIC, "states"),
    (ModelFamily.ODE, "states"),
    (ModelFamily.PDE, "states"),
    (ModelFamily.BAYESIAN, "diagnostics"),
    (ModelFamily.CAUSAL, "causal_effect"),
])
def test_family_reference_missing_mandatory_data_is_not_pass(monkeypatch, family, field):
    def injected(*args, **kwargs):
        return {"status": "PASS", field: {}}

    monkeypatch.setattr(stress, "simulate_model", injected)
    with pytest.raises((AssertionError, KeyError, TypeError)):
        stress._execute_family(family, stress._models()[family])


def test_nonpass_solvers_fail_real_family_run(monkeypatch):
    monkeypatch.setattr(stress, "simulate_model", lambda *args, **kwargs: {"status": "FAIL"})
    with pytest.raises(AssertionError, match="execution returned FAIL"):
        stress._execute_family(ModelFamily.NETWORK, stress._models()[ModelFamily.NETWORK])


@pytest.mark.parametrize("broken_format, expected", [
    ("modelica-3.6", "Modelica export failed"),
    ("graphml", "GraphML export failed"),
    ("causal-dot", "causal DOT export failed"),
    ("portable-bundle-v1", "portable bundle failed"),
])
def test_broken_export_format_does_not_pass_crosscutting_integrity(monkeypatch, broken_format, expected):
    original = stress.export_model

    def fail_one(model, *, format):
        if format == broken_format:
            return {"status": "FAIL", "reason": "corrupt generated artifact"}
        return original(model, format=format)

    monkeypatch.setattr(stress, "export_model", fail_one)
    with pytest.raises(AssertionError, match=expected):
        stress._edge_contracts(stress._models())


def test_unapproved_numeric_refinement_is_rejected(monkeypatch):
    monkeypatch.setattr(stress, "numerical_refinement", lambda *args, **kw: {"status": "PASS"})
    with pytest.raises(AssertionError, match="not approval-gated"):
        stress._edge_contracts(stress._models())


def test_expression_parser_escape_cannot_report_a_pass(monkeypatch):
    import axiomize.safe_expression as expression

    monkeypatch.setattr(expression, "validate_expression", lambda *args, **kw: None)
    with pytest.raises(AssertionError, match="expression escape accepted"):
        stress._edge_contracts(stress._models())
