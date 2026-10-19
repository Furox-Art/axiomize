"""Demonstrate that absent backends and missing version metadata never become PASS."""
from __future__ import annotations

from importlib import metadata

from axiomize.models.candidates import CandidateModel
from axiomize.routing import router
from axiomize.tools import inventory
from axiomize.validation.status import ValidationStatus


def test_legacy_candidate_family_is_exported_without_inventing_a_new_family():
    candidate = CandidateModel(model_family="ode", structure="dx/dt=-k*x")
    assert candidate.to_dict()["family"] == "ode"
    candidate.family = "stochastic"
    assert candidate.to_dict()["family"] == "stochastic"


def test_backend_absence_is_audited_not_replaced_by_claimed_version(monkeypatch):
    monkeypatch.setattr(inventory.importlib.util, "find_spec", lambda name: None)
    output = inventory._module_tool("scientific-library", "missing_package", "missing_dist", ["science"])
    assert output == {
        "available": False,
        "version": "",
        "capabilities": ["science"],
        "reason": "missing_package not installed",
    }


def test_versionless_installed_backend_reports_unknown_not_fake_version(monkeypatch):
    monkeypatch.setattr(inventory.importlib.util, "find_spec", lambda name: object())

    def absent_version(name):
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(inventory.metadata, "version", absent_version)
    output = inventory._module_tool("numeric", "installed_but_unversioned", "unknown_dist", ["numeric"])
    assert output["available"] is True
    assert output["version"] == "unknown"
    assert output["reason"] == ""


def test_available_backend_reports_true_distribution_version(monkeypatch):
    monkeypatch.setattr(inventory.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(inventory.metadata, "version", lambda name: "4.5.6")
    assert inventory._module_tool("num", "numpy", "numpy", [])["version"] == "4.5.6"


def test_unavailable_formal_verifiers_never_claim_success(monkeypatch):
    monkeypatch.setattr(router, "_is_available", lambda name: False)
    result = router.classify({"signals": ["logic", "constraints"]})
    assert result.problem_type == "constraint_verification"
    assert result.status is ValidationStatus.TOOL_UNAVAILABLE
    assert not result.primary_tools
    assert "z3:TOOL_UNAVAILABLE" in result.alternatives
    assert any("VERIFIER_UNAVAILABLE" in choice for choice in result.alternatives)


def test_missing_backend_uses_explicit_scientific_fallback(monkeypatch):
    monkeypatch.setattr(router, "_is_available", lambda name: name == "scipy")
    decision = router.classify({"signals": ["formal", "proof"]})
    assert decision.problem_type == "formal_verification"
    assert decision.primary_tools == ["scipy"]
    assert decision.status is ValidationStatus.WARNING
    assert "scipy:degraded-fallback" in decision.alternatives


def test_missing_primary_with_existing_scientific_verifier_does_not_double_count(monkeypatch):
    monkeypatch.setattr(router, "_is_available", lambda name: name == "scipy")
    decision = router.classify({"signals": ["optimization"]})
    assert decision.problem_type == "generic_optimization"
    assert decision.primary_tools == []
    assert decision.verification_tools == ["scipy"]
    assert decision.status is ValidationStatus.TOOL_UNAVAILABLE
    assert "casadi:TOOL_UNAVAILABLE" in decision.alternatives


def test_partially_available_regression_backend_remains_warning(monkeypatch):
    monkeypatch.setattr(router, "_is_available", lambda name: name == "scipy")
    decision = router.classify({"signals": ["regression", "data"]})
    assert decision.primary_tools == ["scipy"]
    assert decision.status is ValidationStatus.WARNING
    assert "statsmodels:TOOL_UNAVAILABLE" in decision.alternatives


def test_missing_rules_report_unknown_without_invented_classification():
    decision = router.classify({"signals": ["novel-physics"]})
    assert decision.problem_type == "unknown"
    assert decision.status is ValidationStatus.INCONCLUSIVE
    assert decision.primary_tools == []
