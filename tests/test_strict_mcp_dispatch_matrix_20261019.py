"""Explicit MCP transport routing and auditable failure classification.

Injected spies prove dispatch identity, not numerical scientific performance.
The latter remains covered by independent executable model and benchmark tests.
"""
from __future__ import annotations

import json

import pytest

from axiomize.application import advanced_services, general_services, services, surrogate_services
from axiomize.server import mcp_server

_GENERAL_DISPATCH = [
    ("model_plan", general_services, "model_plan_service"),
    ("model_validate", general_services, "model_validate_service"),
    ("model_simulate", general_services, "model_simulate_service"),
    ("model_fit", general_services, "model_fit_service"),
    ("model_compare", general_services, "model_compare_service"),
    ("model_repair", general_services, "model_repair_service"),
    ("model_export", general_services, "model_export_service"),
    ("model_stability", general_services, "model_stability_service"),
    ("model_validity", general_services, "model_validity_service"),
    ("model_discovery", general_services, "model_discovery_service"),
    ("experiment_design", general_services, "experiment_design_service"),
    ("model_uncertainty", advanced_services, "model_uncertainty_service"),
    ("model_bifurcation", advanced_services, "model_bifurcation_service"),
    ("model_numerical_verify", advanced_services, "model_numerical_verification_service"),
    ("model_stop_check", advanced_services, "model_stopping_service"),
    ("model_surrogate", surrogate_services, "model_surrogate_service"),
]


@pytest.mark.parametrize("name,module,function_name", _GENERAL_DISPATCH)
def test_each_scientific_dispatch_reaches_exact_registered_service(
    monkeypatch, name, module, function_name,
):
    got = []
    monkeypatch.setattr(
        module, function_name,
        lambda request: (got.append(request) or {"status": "PASS", "adapter": name}),
    )
    request = {"tracking": "explicit-integration-probe"}
    result = mcp_server._call_tool("axiomize." + name, request)
    assert result == {"status": "PASS", "adapter": name}
    assert got == [request]


_LEGACY_SERVICES = [
    ("intake", "intake_service"),
    ("workflow_policy", "workflow_policy_service"),
    ("clean_data", "clean_data_service"),
    ("solve", "solve_sir_service"),
    ("simulate", "solve_sir_service"),
    ("validate", "validate_sir_service"),
    ("sensitivity_analysis", "sensitivity_service"),
    ("uncertainty_analysis", "uncertainty_service"),
    ("falsify", "falsify_service"),
    ("compare_models", "compare_service"),
]


@pytest.mark.parametrize("name,function_name", _LEGACY_SERVICES)
def test_each_legacy_dispatch_preserves_service_response(monkeypatch, name, function_name):
    requests = []
    returned = {"trace": name, "status": "UNVERIFIED"}
    monkeypatch.setattr(services, function_name, lambda request: (
        requests.append(request) or returned
    ))
    request = {"request_id": 42}
    assert mcp_server._call_tool("axiomize." + name, request) is returned
    assert requests == [request]


def test_mcp_declared_legacy_alias_selects_actual_canonical_route(monkeypatch):
    called = []
    monkeypatch.setattr(
        services, "solve_sir_service",
        lambda request: (called.append(request) or {"status": "PASS"}),
    )
    request = {"beta": 0.3, "gamma": 0.1}
    assert mcp_server._call_tool("solve_sir", request)["status"] == "PASS"
    assert called == [request]


def test_mcp_unknown_tool_and_missing_input_are_not_success():
    with pytest.raises(KeyError, match="unknown tool"):
        mcp_server._call_tool("axiomize.invalid", {})
    with pytest.raises(ValueError, match="JSON object"):
        mcp_server._call_tool("axiomize.intake", "invalid")


def test_mcp_sir_fit_uses_actual_numeric_model_branch(monkeypatch):
    from axiomize.fitting import estimator

    got = []

    class FitEvidence:
        def to_dict(self):
            return {"fit_status": "PASS", "iterations": 5}

    def solver(t, y, population, first):
        got.append((t.tolist(), y.tolist(), population, first))
        return FitEvidence()

    monkeypatch.setattr(estimator, "fit_sir_curve", solver)
    actual = mcp_server._call_tool("axiomize.fit_model", {
        "model": "sir", "N": 300, "I0": 4,
        "t": [0.0, 1.0], "y": [4.0, 5.0],
    })
    assert actual["fit_status"] == "PASS"
    assert got == [([0.0, 1.0], [4.0, 5.0], 300.0, 4.0)]


def test_cross_validation_returns_only_actual_scientific_check(monkeypatch):
    monkeypatch.setattr(
        services, "solve_sir_service",
        lambda request: {"status": "PASS", "cross_validation": {
            "status": "WARNING", "reason": "not independently supported",
        }},
    )
    result = mcp_server._call_tool("axiomize.cross_validate", {})
    assert result == {"status": "WARNING", "reason": "not independently supported"}


@pytest.mark.parametrize("error,expected_code", [
    (KeyError("unknown"), -32601),
    (ValueError("invalid numerical bound"), -32602),
    (OSError("run unavailable"), -32602),
    (RuntimeError("secret internal exception"), -32000),
])
def test_rpc_error_translation_preserves_protocol_boundary(
    monkeypatch, error, expected_code,
):
    def erroring(*args, **kwargs):
        raise error

    monkeypatch.setattr(mcp_server, "_call_tool", erroring)
    response = mcp_server.handle_message({
        "method": "tools/call", "id": 101,
        "params": {"name": "axiomize.model_validate", "arguments": {}},
    })
    assert response["id"] == 101
    assert response["error"]["code"] == expected_code
    if expected_code == -32000:
        assert response["error"]["message"] == "internal tool error"
        assert "secret" not in json.dumps(response)


@pytest.mark.parametrize("error,expected", [
    (KeyError("unknown"), "unknown"),
    (ValueError("not finite"), "not finite"),
    (OSError("missing run"), "missing run"),
    (RuntimeError("secret trace"), "internal tool error"),
])
def test_public_tool_wrapper_cannot_expose_internal_errors(
    monkeypatch, error, expected,
):
    def erroring(*args, **kwargs):
        raise error

    monkeypatch.setattr(mcp_server, "_call_tool", erroring)
    result = mcp_server.call_tool("axiomize.model_validate", {})
    assert expected in result["error"]


def test_mcp_failed_scientific_result_remains_explicitly_failed(monkeypatch):
    monkeypatch.setattr(mcp_server, "_call_tool", lambda *args, **kwargs: {
        "status": "FAIL", "error": "measurement falsified",
    })
    result = mcp_server.handle_message({
        "method": "tools/call", "id": 31,
        "params": {"name": "axiomize.model_validate", "arguments": {}},
    })
    assert result["result"]["status"] == "FAIL"
    saved = json.loads(result["result"]["content"][0]["text"])
    assert saved == {"status": "FAIL", "error": "measurement falsified"}


def test_reproduce_and_inspect_do_not_escape_authorized_run_root(tmp_path):
    from axiomize.runs.state import RunState

    root = tmp_path / "runs"
    root.mkdir()
    RunState(parameters={"k": 0.5}, results={"observed": [1.0, 0.5]}).save(root / "model-1")
    for tool_name in ("axiomize.inspect_run", "axiomize.reproduce"):
        outcome = mcp_server._call_tool(tool_name, {"run_dir": "model-1"}, run_root=root)
        assert outcome["results"]["observed"] == [1.0, 0.5]
        with pytest.raises((ValueError, OSError)):
            mcp_server._call_tool(tool_name, {"run_dir": "../outside"}, run_root=root)


def test_compare_runs_records_real_parameter_difference_inside_root(tmp_path):
    from axiomize.runs.state import RunState

    root = tmp_path / "run-root"
    root.mkdir()
    RunState(parameters={"k": 0.5}).save(root / "first")
    RunState(parameters={"k": 0.8}).save(root / "second")
    report = mcp_server._call_tool(
        "axiomize.compare_runs",
        {"before_dir": "first", "after_dir": "second"}, run_root=root,
    )
    assert report["differences"]["parameters"]["k"] == {"before": 0.5, "after": 0.8}
