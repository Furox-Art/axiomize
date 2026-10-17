"""MCP JSON-RPC dispatch, errors, and consent boundaries tested deterministically."""

from __future__ import annotations

import json

import pytest

from axiomize.server import mcp_server as mcp


@pytest.mark.parametrize(
    "method",
    [
        "initialize",
        "ping",
        "notifications/initialized",
        "notifications/cancelled",
    ],
)
def test_rpc_handshake_and_notifications_never_launch_scientific_tools(method):
    result = mcp.handle_message({"jsonrpc": "2.0", "id": 7, "method": method})
    assert result["id"] == 7
    assert result["jsonrpc"] == "2.0"
    assert "result" in result
    if method == "initialize":
        assert result["result"]["capabilities"] == {"tools": {}}


def test_list_tools_schema_is_unique_and_sorted():
    response = mcp.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = response["result"]["tools"]
    names = [t["name"] for t in tools]
    assert names == sorted(names)
    assert len(names) == len(set(names))
    assert all(t["inputSchema"]["type"] == "object" for t in tools)
    assert "axiomize.model_numerical_verify" in names
    assert "axiomize.model_surrogate" in names


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ([], -32600),
        ("text", -32600),
        ({}, -32601),
        ({"method": "no-such-method", "id": 3}, -32601),
        ({"method": "tools/call", "id": 3}, -32602),
        ({"method": "tools/call", "id": 3, "params": []}, -32602),
        ({"method": "tools/call", "id": 3, "params": {"name": 7}}, -32602),
        ({"method": "tools/call", "id": 3, "params": {"name": "some", "arguments": []}}, -32602),
    ],
)
def test_rpc_invalid_methods_and_params_return_explicit_errors(message, code):
    result = mcp.handle_message(message)
    assert result["error"]["code"] == code
    assert "result" not in result


@pytest.mark.parametrize(
    ("failure", "code", "expected"),
    [
        (KeyError("not found"), -32601, "not found"),
        (ValueError("scientific contract"), -32602, "scientific contract"),
        (OSError("filesystem unavailable"), -32602, "filesystem unavailable"),
        (RuntimeError("confidential stack details"), -32000, "internal tool error"),
    ],
)
def test_rpc_errors_never_promote_failed_tools_to_success(failure, code, expected, monkeypatch):
    def broken(*args, **kwargs):
        raise failure

    monkeypatch.setattr(mcp, "_call_tool", broken)
    result = mcp.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "axiomize.solve", "arguments": {}},
        }
    )
    assert result["error"]["code"] == code
    assert expected in result["error"]["message"]
    assert "result" not in result
    assert "confidential stack" not in result["error"]["message"]


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "PASS", "estimate": 3.2},
        {"status": "UNVERIFIED", "confidence": None},
        {"status": "FAIL", "proof": {"observed": False}},
    ],
)
def test_rpc_retains_explicit_status_and_json_serializability(payload, monkeypatch):
    monkeypatch.setattr(mcp, "_call_tool", lambda *a, **kw: payload)
    result = mcp.handle_message(
        {
            "jsonrpc": "2.0",
            "id": "id",
            "method": "tools/call",
            "params": {"name": "axiomize.solve", "arguments": {}},
        }
    )
    assert result["result"]["status"] == payload["status"]
    assert json.loads(result["result"]["content"][0]["text"]) == payload
    assert result["result"]["isError"] is False


@pytest.mark.parametrize(
    ("name", "canonical"),
    [
        ("solve_sir", "axiomize.solve"),
        ("validate_sir", "axiomize.validate"),
        ("fit_model", "axiomize.fit_model"),
        ("list_tools", "axiomize.list_tools"),
        ("get_capabilities", "axiomize.get_capabilities"),
    ],
)
def test_legacy_aliases_are_not_reinterpreted_as_other_tools(name, canonical, monkeypatch):
    from axiomize.application import services

    service = {
        "axiomize.solve": "solve_sir_service",
        "axiomize.validate": "validate_sir_service",
        "axiomize.fit_model": "fit_logistic_service",
        "axiomize.list_tools": "tools_service",
        "axiomize.get_capabilities": "capabilities_service",
    }[canonical]
    monkeypatch.setattr(services, service, lambda *a: {"called": service})
    assert mcp._call_tool(name, {}) == {"called": service}


@pytest.mark.parametrize(
    ("name", "module", "method"),
    [
        ("axiomize.model_plan", "general_services", "model_plan_service"),
        ("axiomize.model_validate", "general_services", "model_validate_service"),
        ("axiomize.model_simulate", "general_services", "model_simulate_service"),
        ("axiomize.model_fit", "general_services", "model_fit_service"),
        ("axiomize.model_compare", "general_services", "model_compare_service"),
        ("axiomize.model_repair", "general_services", "model_repair_service"),
        ("axiomize.model_export", "general_services", "model_export_service"),
        ("axiomize.model_stability", "general_services", "model_stability_service"),
        ("axiomize.model_validity", "general_services", "model_validity_service"),
        ("axiomize.model_discovery", "general_services", "model_discovery_service"),
        ("axiomize.experiment_design", "general_services", "experiment_design_service"),
        ("axiomize.model_uncertainty", "advanced_services", "model_uncertainty_service"),
        ("axiomize.model_bifurcation", "advanced_services", "model_bifurcation_service"),
        ("axiomize.model_numerical_verify", "advanced_services", "model_numerical_verification_service"),
        ("axiomize.model_stop_check", "advanced_services", "model_stopping_service"),
        ("axiomize.model_surrogate", "surrogate_services", "model_surrogate_service"),
        ("axiomize.intake", "services", "intake_service"),
        ("axiomize.workflow_policy", "services", "workflow_policy_service"),
        ("axiomize.clean_data", "services", "clean_data_service"),
        ("axiomize.falsify", "services", "falsify_service"),
        ("axiomize.compare_models", "services", "compare_service"),
        ("axiomize.sensitivity_analysis", "services", "sensitivity_service"),
        ("axiomize.uncertainty_analysis", "services", "uncertainty_service"),
    ],
)
def test_mcp_tools_map_to_exact_scientific_service(name, module, method, monkeypatch):
    import importlib

    target = importlib.import_module("axiomize.application." + module)
    monkeypatch.setattr(target, method, lambda *a: {"called": method})
    assert mcp._call_tool(name, {}) == {"called": method}


@pytest.mark.parametrize(
    ("name", "method"),
    [
        ("axiomize.solve", "solve_sir_service"),
        ("axiomize.simulate", "solve_sir_service"),
        ("axiomize.validate", "validate_sir_service"),
    ],
)
def test_legacy_physical_solvers_dispatch_without_model_ir(name, method, monkeypatch):
    from axiomize.application import services

    monkeypatch.setattr(services, method, lambda *a: {"called": method})
    assert mcp._call_tool(name, {}) == {"called": method}


@pytest.mark.parametrize(
    ("name", "method"),
    [
        ("axiomize.list_tools", "tools_service"),
        ("axiomize.get_capabilities", "capabilities_service"),
    ],
)
def test_inventory_tools_do_not_infer_provider_status(name, method, monkeypatch):
    from axiomize.application import services

    monkeypatch.setattr(services, method, lambda *a: {"called": method})
    assert mcp._call_tool(name, {}) == {"called": method}


def test_model_visualization_requires_run_directory_identifier():
    with pytest.raises(ValueError, match="run_dir must be a string"):
        mcp._call_tool("axiomize.model_visualize", {})
    with pytest.raises(ValueError, match="chart_type must be a string"):
        mcp._call_tool("axiomize.model_visualize", {"run_dir": "id", "chart_type": []})


def test_non_object_tool_arguments_rejected_before_any_service_call():
    with pytest.raises(ValueError, match="must be a JSON object"):
        mcp._call_tool("axiomize.model_plan", [])


def test_unknown_tool_has_explicit_key_error_not_fake_result():
    with pytest.raises(KeyError, match="unknown tool"):
        mcp._call_tool("axiomize.not_existing", {})


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (KeyError("missing"), "missing"),
        (ValueError("bad scientific request"), "bad scientific request"),
        (RuntimeError("sensitive runtime detail"), "internal tool error"),
    ],
)
def test_simple_tool_api_returns_error_without_exposing_internal_traceback(exc, expected, monkeypatch):
    def broken(*a, **kw):
        raise exc

    monkeypatch.setattr(mcp, "_call_tool", broken)
    assert expected in mcp.call_tool("axiomize.solve", {})["error"]


def test_mcp_tool_list_contains_all_actual_canonical_entries():
    tools = mcp.list_tools()
    names = {row["name"] for row in tools}
    assert len(names) == len(tools)
    assert names.issuperset(mcp._TOOL_SCHEMAS)
    assert "solve_sir" in names
    assert "axiomize.solve" in names
