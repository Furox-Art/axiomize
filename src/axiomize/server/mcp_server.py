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

_NUMBER = {"type": "number"}
_NUMBER_ARRAY = {"type": "array", "items": {"type": "number"}, "minItems": 2}
_OBJECT = {"type": "object", "additionalProperties": True}

_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "axiomize.intake": {
        "description": "Clarify a vague idea, recommend weak/medium/strong depth, and return the next plain-language question or a ready workflow plan.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "idea": {"type": "string", "minLength": 1},
                "context": _OBJECT,
                "signals": _OBJECT,
                "rigor": {"type": "string", "enum": ["weak", "medium", "strong", "basic", "standard", "research"]},
                "question_mode": {"type": "string", "enum": ["one_by_one", "all_at_once", "adaptive"]},
                "preferred_question_mode": {"type": "string", "enum": ["one_by_one", "all_at_once"]},
                "permissions": _OBJECT,
            },
            "required": ["idea"],
            "additionalProperties": False,
        },
    },
    "axiomize.workflow_policy": {
        "description": "Return the deterministic Axiomize workflow policy, rigor recommendation, and user-consent boundaries for extra agent/API work.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "signals": _OBJECT,
                "question_mode": {"type": "string", "enum": ["one_by_one", "all_at_once", "adaptive"]},
                "permissions": _OBJECT,
            },
            "additionalProperties": False,
        },
    },
    "axiomize.clean_data": {
        "description": "Conservatively clean paired numeric observations while preserving originals and returning a complete audit trail.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "t": _NUMBER_ARRAY,
                "y": _NUMBER_ARRAY,
                "drop_nonfinite": {"type": "boolean"},
                "sort_time": {"type": "boolean"},
                "duplicate_policy": {"type": "string", "enum": ["mean", "first", "error"]},
            },
            "required": ["t", "y"],
            "additionalProperties": False,
        },
    },
    "axiomize.compare_runs": {
        "description": "Compare two stored reproducible runs and explain whether data, parameters, assumptions, solver settings, tool versions, policy, model choice or results changed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "before_dir": {"type": "string", "minLength": 1},
                "after_dir": {"type": "string", "minLength": 1},
            },
            "required": ["before_dir", "after_dir"],
            "additionalProperties": False,
        },
    },
    "axiomize.solve": {
        "description": "Solve the reference SIR model with numerical and theoretical validation.",
        "inputSchema": {"type": "object", "properties": {
            "beta": _NUMBER, "gamma": _NUMBER, "I0": _NUMBER,
            "N": {"type": "number", "exclusiveMinimum": 0},
            "days": {"type": "number", "exclusiveMinimum": 0},
        }, "additionalProperties": False},
    },
    "axiomize.fit_model": {
        "description": "Fit logistic or SIR data with parameter uncertainty and diagnostics.",
        "inputSchema": {"type": "object", "properties": {
            "t": _NUMBER_ARRAY, "y": _NUMBER_ARRAY,
            "model": {"type": "string", "enum": ["logistic", "sir"]},
            "N": {"type": "number", "exclusiveMinimum": 0}, "I0": _NUMBER,
        }, "required": ["t", "y"], "additionalProperties": False},
    },
    "axiomize.simulate": {
        "description": "Simulate the reference SIR model.",
        "inputSchema": {"type": "object", "properties": {
            "beta": _NUMBER, "gamma": _NUMBER, "I0": _NUMBER,
            "N": {"type": "number", "exclusiveMinimum": 0},
            "days": {"type": "number", "exclusiveMinimum": 0},
        }, "additionalProperties": False},
    },
    "axiomize.validate": {
        "description": "Run SIR numerical, dimensional, conservation and cross-validation checks.",
        "inputSchema": {"type": "object", "properties": {
            "beta": _NUMBER, "gamma": _NUMBER, "I0": _NUMBER,
            "N": {"type": "number", "exclusiveMinimum": 0},
            "days": {"type": "number", "exclusiveMinimum": 0},
        }, "additionalProperties": False},
    },
    "axiomize.cross_validate": {
        "description": "Cross-check SIR numerical output against independent theory.",
        "inputSchema": {"type": "object", "properties": {
            "beta": _NUMBER, "gamma": _NUMBER, "I0": _NUMBER,
            "N": {"type": "number", "exclusiveMinimum": 0},
        }, "additionalProperties": False},
    },
    "axiomize.sensitivity_analysis": {
        "description": "Rank local and Monte-Carlo sensitivity for SIR parameters.",
        "inputSchema": {"type": "object", "properties": {
            "params": {"type": "object", "additionalProperties": {"type": "number"}},
            "N": {"type": "number", "exclusiveMinimum": 0}, "I0": _NUMBER,
            "target": {"type": "string", "enum": ["final_size", "peak"]},
        }, "required": ["params"], "additionalProperties": False},
    },
    "axiomize.uncertainty_analysis": {
        "description": "Build normal 95% uncertainty intervals from fitted value/error pairs.",
        "inputSchema": {"type": "object", "properties": {"fit": _OBJECT, "params": _OBJECT}, "additionalProperties": False},
    },
    "axiomize.falsify": {
        "description": "Evaluate explicit falsifiers against observations.",
        "inputSchema": {"type": "object", "properties": {
            "falsifiers": {"type": "array", "items": _OBJECT},
            "observations": _OBJECT,
        }, "additionalProperties": False},
    },
    "axiomize.compare_models": {
        "description": "Fit and compare logistic and SIR candidates on the same observations.",
        "inputSchema": {"type": "object", "properties": {
            "t": _NUMBER_ARRAY, "y": _NUMBER_ARRAY,
            "N": {"type": "number", "exclusiveMinimum": 0}, "I0": _NUMBER,
        }, "required": ["t", "y"], "additionalProperties": False},
    },
    "axiomize.select_tools": {
        "description": "Select scientific tools from explicit problem signals.",
        "inputSchema": {"type": "object", "properties": {
            "signals": {"type": "array", "items": {"type": "string"}},
        }, "required": ["signals"], "additionalProperties": False},
    },
    "axiomize.list_tools": {
        "description": "List live scientific backends and availability.",
        "inputSchema": {"type": "object", "additionalProperties": False},
    },
    "axiomize.get_capabilities": {
        "description": "Return machine-readable engine capabilities including adaptive intake and cost guards.",
        "inputSchema": {"type": "object", "additionalProperties": False},
    },
    "axiomize.inspect_run": {
        "description": "Inspect a recorded reproducible run.",
        "inputSchema": {"type": "object", "properties": {"run_dir": {"type": "string"}}, "required": ["run_dir"], "additionalProperties": False},
    },
    "axiomize.reproduce": {
        "description": "Load a recorded run configuration for reproducibility inspection.",
        "inputSchema": {"type": "object", "properties": {"run_dir": {"type": "string"}}, "required": ["run_dir"], "additionalProperties": False},
    },
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
    if name == "axiomize.intake":
        return services.intake_service(arguments)
    if name == "axiomize.workflow_policy":
        return services.workflow_policy_service(arguments)
    if name == "axiomize.clean_data":
        return services.clean_data_service(arguments)
    if name == "axiomize.compare_runs":
        return services.compare_runs_service(arguments)
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
    canonical = [{"name": name, **_TOOL_SCHEMAS[name]} for name in sorted(_TOOL_SCHEMAS)]
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
                    {"name": name,
                     "description": spec["description"],
                     "inputSchema": spec["inputSchema"]}
                    for name, spec in sorted(_TOOL_SCHEMAS.items())]}}
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
