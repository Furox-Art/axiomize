"""MCP server adapter over stdio (PHASE 8).

Newline-delimited JSON-RPC 2.0. A thin adapter: every tool calls the
same application services as the CLI and REST layers.
"""

from __future__ import annotations

import json
import sys
from typing import Any

SERVER_NAME = "axiomize"
API_VERSION = "v1"

_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "axiomize.solve": {"params": ["beta", "gamma", "I0", "N", "days"]},
    "axiomize.fit_model": {"params": ["t", "y", "model"]},
    "axiomize.simulate": {"params": ["beta", "gamma", "I0", "N", "days"]},
    "axiomize.validate": {"params": ["beta", "gamma", "I0", "N", "days"]},
    "axiomize.cross_validate": {"params": ["beta", "gamma", "I0", "N"]},
    "axiomize.sensitivity_analysis": {"params": ["params", "N", "I0"]},
    "axiomize.uncertainty_analysis": {"params": ["fit"]},
    "axiomize.falsify": {"params": ["falsifiers", "observations"]},
    "axiomize.compare_models": {"params": ["t", "y", "N"]},
    "axiomize.select_tools": {"params": ["signals"]},
    "axiomize.list_tools": {"params": []},
    "axiomize.get_capabilities": {"params": []},
    "axiomize.inspect_run": {"params": ["run_dir"]},
    "axiomize.reproduce": {"params": ["run_dir"]},
}

_LEGACY_TOOL_NAMES = {
    "solve_sir": "axiomize.solve",
    "validate_sir": "axiomize.validate",
    "fit_model": "axiomize.fit_model",
    "list_tools": "axiomize.list_tools",
    "get_capabilities": "axiomize.get_capabilities",
}


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from axiomize.application import services
    from axiomize.routing.router import classify
    from axiomize.runs.state import RunState

    name = _LEGACY_TOOL_NAMES.get(name, name)
    if name in ("axiomize.solve", "axiomize.simulate"):
        return services.solve_sir_service(arguments)
    if name == "axiomize.validate":
        return services.validate_sir_service(arguments)
    if name == "axiomize.fit_model":
        if arguments.get("model", "logistic") == "sir" and "N" in arguments:
            import numpy as np
            from axiomize.fitting.estimator import fit_sir_curve

            t = np.asarray(arguments["t"], dtype=float)
            y = np.asarray(arguments["y"], dtype=float)
            return fit_sir_curve(t, y, float(arguments["N"]),
                                 float(arguments.get("I0", y[0]))).to_dict()
        return services.fit_logistic_service(arguments)
    if name == "axiomize.cross_validate":
        return services.solve_sir_service(arguments)["cross_validation"]
    if name == "axiomize.sensitivity_analysis":
        return services.sensitivity_service(arguments)
    if name == "axiomize.uncertainty_analysis":
        return services.uncertainty_service(arguments)
    if name == "axiomize.falsify":
        return services.falsify_service(arguments)
    if name == "axiomize.compare_models":
        return services.compare_service(arguments)
    if name == "axiomize.select_tools":
        return classify({"signals": arguments.get("signals", [])}).to_dict()
    if name == "axiomize.list_tools":
        return services.tools_service()
    if name == "axiomize.get_capabilities":
        return services.capabilities_service()
    if name in ("axiomize.inspect_run", "axiomize.reproduce"):
        run = RunState.load(arguments["run_dir"])
        return {"input_hash": run.input_hash(), "results": run.results,
                "problem_definition": run.problem_definition}
    raise KeyError(f"unknown tool: {name}")


def list_tools() -> list[dict[str, Any]]:
    """Compatibility helper used by direct Python integrations."""
    aliases = [{"name": name} for name in sorted(_LEGACY_TOOL_NAMES)]
    canonical = [{"name": name} for name in sorted(_TOOL_SCHEMAS)]
    return aliases + canonical


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Compatibility helper returning an error object instead of raising."""
    try:
        return _call_tool(name, arguments)
    except KeyError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def handle_message(message: dict[str, Any]) -> dict[str, Any]:
    method = message.get("method", "")
    msg_id = message.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": msg_id,
                "result": {"protocolVersion": "2024-11-05",
                           "serverInfo": {"name": SERVER_NAME, "version": API_VERSION},
                           "capabilities": {"tools": {}}}}
    if method in ("notifications/initialized", "notifications/cancelled"):
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id,
                "result": {"tools": [
                    {"name": name, "description": f"Axiomize {name} ({API_VERSION})",
                     "inputSchema": {"type": "object"}}
                    for name in sorted(_TOOL_SCHEMAS)]}}
    if method == "tools/call":
        params = message.get("params", {})
        try:
            result = _call_tool(params["name"], params.get("arguments", {}))
        except KeyError as exc:
            return {"jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32601, "message": str(exc)}}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32000, "message": f"{type(exc).__name__}: {exc}"}}
        return {"jsonrpc": "2.0", "id": msg_id,
                "result": {"content": [{"type": "text",
                                        "text": json.dumps(result, default=str)}],
                           "isError": False,
                           **({"status": result["status"]} if "status" in result else {})}}
    return {"jsonrpc": "2.0", "id": msg_id,
            "error": {"code": -32601, "message": f"unknown method: {method}"}}


def serve_stdio() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            sys.stdout.write(json.dumps(
                {"jsonrpc": "2.0", "id": None,
                 "error": {"code": -32700, "message": str(exc)}}) + "\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps(handle_message(message), default=str) + "\n")
        sys.stdout.flush()
