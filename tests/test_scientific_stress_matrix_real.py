"""Run each native family on small real instances and reject false matrix PASS."""

from __future__ import annotations

import math

import pytest

import axiomize.scientific_stress as stress
from axiomize.model_ir import ModelFamily


def test_stress_matrix_covers_every_native_family_with_actual_numerical_execution():
    result = stress.run_stress_matrix()
    assert result["status"] == "PASS", result
    assert result["families_covered"] == sorted(family.value for family in ModelFamily)
    assert result["total"] == len(ModelFamily) + 1
    assert result["passed"] == result["total"]
    assert all(row["status"] == "PASS" for row in result["results"])


@pytest.mark.parametrize("family", list(ModelFamily))
def test_each_native_science_family_has_a_versioned_ir_family_contract(family):
    models = stress._models()
    scientific = models[family]
    assert scientific.family is family
    assert scientific.schema_version == "1.0"
    assert scientific.variables
    assert scientific.equations
    assert scientific.metadata["numerical_verification"]["enabled"] is False


def test_stress_failure_does_not_become_matrix_success(monkeypatch):
    real = stress._execute_family

    def broken(family, model):
        if family == ModelFamily.PDE:
            raise RuntimeError("numerical solver rejected")
        return real(family, model)

    monkeypatch.setattr(stress, "_execute_family", broken)
    report = stress.run_stress_matrix()
    assert report["status"] == "FAIL"
    failure = next(item for item in report["results"] if item.get("family") == "pde")
    assert failure["status"] == "FAIL"
    assert "numerical solver rejected" in failure["error"]


def test_each_runtime_budget_is_hard_failure_not_warning(monkeypatch):
    monkeypatch.setattr(stress, "_CASE_BUDGET_S", -1.0)
    monkeypatch.setattr(stress, "_TOTAL_BUDGET_S", -1.0)
    monkeypatch.setattr(stress, "_execute_family", lambda family, model: None)
    monkeypatch.setattr(stress, "_edge_contracts", lambda models: None)
    out = stress.run_stress_matrix()
    assert out["status"] == "FAIL"
    assert out["passed"] < out["total"]
    assert next(x for x in out["results"] if x["name"] == "total_runtime_budget")["status"] == "FAIL"
    assert all(row["status"] == "FAIL" for row in out["results"] if row["name"].startswith("family:"))
    assert all(math.isfinite(row["elapsed_s"]) for row in out["results"] if "elapsed_s" in row)


def test_stress_contract_failure_is_reported_without_silently_repairing(monkeypatch):
    monkeypatch.setattr(stress, "_execute_family", lambda family, model: None)

    def broken_contract(_models):
        raise ValueError("verification refused")

    monkeypatch.setattr(stress, "_edge_contracts", broken_contract)
    out = stress.run_stress_matrix()
    assert out["status"] == "FAIL"
    assert out["results"][-1]["name"] == "cross_cutting_contracts"
    assert out["results"][-1]["status"] == "FAIL"
    assert "verification refused" in out["results"][-1]["error"]
