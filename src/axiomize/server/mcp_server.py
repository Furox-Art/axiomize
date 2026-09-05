"""MCP stdio adapter over shared Axiomize application services.

The transport accepts one JSON-RPC object per line. Input size is bounded and
filesystem-facing run tools are confined beneath a caller-selected run root.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from axiomize.json_safety import json_safe
from axiomize.limits import MAX_MCP_MESSAGE_BYTES
from axiomize.runs.state import RunState, resolve_run_directory

SERVER_NAME = "axiomize"
API_VERSION = "v1"

_NUMBER = {"type": "number"}
_NUMBER_ARRAY = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 200000}
_OBJECT = {"type": "object", "additionalProperties": True}


def _schema(description: str, properties: dict[str, Any] | None = None,
            required: list[str] | None = None, *, additional: bool = False) -> dict[str, Any]:
    body: dict[str, Any] = {"type": "object", "properties": properties or {}, "additionalProperties": additional}
    if required:
        body["required"] = required
    return {"description": description, "inputSchema": body}


_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "axiomize.intake": _schema("Clarify a vague idea and return the next modeling question or ready plan.",
        {"idea": {"type": "string", "minLength": 1}, "context": _OBJECT, "signals": _OBJECT,
         "rigor": {"type": "string"}, "question_mode": {"type": "string"},
         "preferred_question_mode": {"type": "string"}, "permissions": _OBJECT}, ["idea"]),
    "axiomize.workflow_policy": _schema("Return workflow policy and consent boundaries.",
        {"signals": _OBJECT, "question_mode": {"type": "string"}, "permissions": _OBJECT}),
    "axiomize.clean_data": _schema("Clean paired numeric observations with an audit trail.",
        {"t": _NUMBER_ARRAY, "y": _NUMBER_ARRAY, "drop_nonfinite": {"type": "boolean"},
         "sort_time": {"type": "boolean"}, "duplicate_policy": {"type": "string"}}, ["t", "y"]),
    "axiomize.compare_runs": _schema("Compare two stored reproducible runs beneath the configured run root.",
        {"before_dir": {"type": "string"}, "after_dir": {"type": "string"}}, ["before_dir", "after_dir"]),
    "axiomize.solve": _schema("Solve the backward-compatible reference SIR model.",
        {"beta": _NUMBER, "gamma": _NUMBER, "I0": _NUMBER, "N": {"type": "number", "exclusiveMinimum": 0}, "days": _NUMBER}),
    "axiomize.fit_model": _schema("Fit backward-compatible logistic or SIR data.",
        {"t": _NUMBER_ARRAY, "y": _NUMBER_ARRAY, "model": {"type": "string"}, "N": _NUMBER, "I0": _NUMBER}, ["t", "y"]),
    "axiomize.simulate": _schema("Simulate the backward-compatible reference SIR model.",
        {"beta": _NUMBER, "gamma": _NUMBER, "I0": _NUMBER, "N": _NUMBER, "days": _NUMBER}),
    "axiomize.validate": _schema("Validate the backward-compatible reference SIR model.",
        {"beta": _NUMBER, "gamma": _NUMBER, "I0": _NUMBER, "N": _NUMBER, "days": _NUMBER}),
    "axiomize.cross_validate": _schema("Cross-check SIR asymptotic final size by independent methods.",
        {"beta": _NUMBER, "gamma": _NUMBER, "I0": _NUMBER, "N": _NUMBER}),
    "axiomize.sensitivity_analysis": _schema("Run SIR sensitivity analysis.",
        {"params": _OBJECT, "N": _NUMBER, "I0": _NUMBER, "target": {"type": "string"}}, ["params"]),
    "axiomize.uncertainty_analysis": _schema("Compute parameter uncertainty intervals.", {"fit": _OBJECT, "params": _OBJECT}),
    "axiomize.falsify": _schema("Evaluate explicit falsifiers.", {"falsifiers": {"type": "array", "items": _OBJECT}, "observations": _OBJECT}),
    "axiomize.compare_models": _schema("Compare reference logistic/SIR fits.",
        {"t": _NUMBER_ARRAY, "y": _NUMBER_ARRAY, "N": _NUMBER, "I0": _NUMBER}, ["t", "y"]),
    "axiomize.select_tools": _schema("Select scientific tools from explicit signals.",
        {"signals": {"type": "array", "items": {"type": "string"}, "maxItems": 1000}}, ["signals"]),
    "axiomize.list_tools": _schema("List live scientific backends."),
    "axiomize.get_capabilities": _schema("Return machine-readable engine capabilities."),
    "axiomize.inspect_run": _schema("Inspect a recorded run beneath the configured run root.", {"run_dir": {"type": "string"}}, ["run_dir"]),
    "axiomize.reproduce": _schema("Load a recorded run beneath the configured run root.", {"run_dir": {"type": "string"}}, ["run_dir"]),

    "axiomize.model_plan": _schema("Rank model families or build an execution plan from Model IR.",
        {"idea": {"type": "string"}, "domain": {"type": "string"}, "signals": _OBJECT, "model_ir": _OBJECT,
         "model": _OBJECT, "action": {"type": "string"}, "points": {"type": "integer", "maximum": 200000},
         "samples": {"type": "integer", "maximum": 100000}, "approve_migration": {"type": "boolean"}}, additional=True),
    "axiomize.model_validate": _schema("Validate Model IR structure, units, scientific constraints and causal claims.",
        {"model_ir": _OBJECT, "model": _OBJECT, "approve_migration": {"type": "boolean"}}, additional=True),
    "axiomize.model_simulate": _schema("Simulate Model IR with solver attempts and scientific checks.",
        {"model_ir": _OBJECT, "model": _OBJECT, "t_span": _NUMBER_ARRAY, "points": {"type": "integer", "maximum": 200000},
         "parameter_overrides": _OBJECT, "seed": {"type": "integer"}, "approve_heavy": {"type": "boolean"},
         "approve_migration": {"type": "boolean"}}, additional=True),
    "axiomize.model_fit": _schema("Fit ODE Model IR parameters with identifiability/residual diagnostics.",
        {"model_ir": _OBJECT, "model": _OBJECT, "time": _NUMBER_ARRAY, "observations": _OBJECT,
         "approve_heavy": {"type": "boolean"}, "approve_migration": {"type": "boolean"}}, additional=True),
    "axiomize.model_compare": _schema("Rank fitted model candidates by AIC/BIC/SSE.", {"fits": _OBJECT, "criterion": {"type": "string"}}, ["fits"]),
    "axiomize.model_repair": _schema("Propose/apply constraint-driven repair only with approval.",
        {"model_ir": _OBJECT, "model": _OBJECT, "validation": _OBJECT, "approve_repair": {"type": "boolean"},
         "approve_migration": {"type": "boolean"}}, additional=True),
    "axiomize.model_export": _schema("Export Model IR to portable/versioned formats.",
        {"model_ir": _OBJECT, "model": _OBJECT, "format": {"type": "string"}, "approve_migration": {"type": "boolean"}}, additional=True),
    "axiomize.model_stability": _schema("Linearize an ODE Model IR and report eigenvalue stability.",
        {"model_ir": _OBJECT, "model": _OBJECT, "state": _OBJECT, "parameter_overrides": _OBJECT,
         "approve_migration": {"type": "boolean"}}, additional=True),
    "axiomize.model_validity": _schema("Scan an explicit parameter range; approval-gated.",
        {"model_ir": _OBJECT, "model": _OBJECT, "parameter": {"type": "string"}, "values": _NUMBER_ARRAY,
         "t_span": _NUMBER_ARRAY, "points": {"type": "integer", "maximum": 200000}, "approve_heavy": {"type": "boolean"},
         "approve_migration": {"type": "boolean"}}, additional=True),
    "axiomize.model_discovery": _schema("Discover sparse candidate dynamics from data; output remains unverified.",
        {"time": _NUMBER_ARRAY, "state": _NUMBER_ARRAY, "degree": {"type": "integer"}, "threshold": _NUMBER,
         "approve_heavy": {"type": "boolean"}}, ["time", "state"]),
    "axiomize.experiment_design": _schema("Rank candidate observation times by information-gain proxy; approval-gated.",
        {"model_ir": _OBJECT, "model": _OBJECT, "parameter": {"type": "string"}, "candidate_times": _NUMBER_ARRAY,
         "horizon": _NUMBER, "delta_fraction": _NUMBER, "approve_heavy": {"type": "boolean"},
         "approve_migration": {"type": "boolean"}}, additional=True),
    "axiomize.model_uncertainty": _schema("Propagate parameter uncertainty by approval-gated Monte Carlo.",
        {"model_ir": _OBJECT, "model": _OBJECT, "parameter_uncertainty": _OBJECT, "t_span": _NUMBER_ARRAY,
         "points": {"type": "integer", "maximum": 200000}, "samples": {"type": "integer", "maximum": 100000},
         "quantiles": _NUMBER_ARRAY, "approve_heavy": {"type": "boolean"}, "approve_migration": {"type": "boolean"}}, additional=True),
    "axiomize.model_bifurcation": _schema("Scan ODE equilibria/stability for bifurcation candidates; approval-gated.",
        {"model_ir": _OBJECT, "model": _OBJECT, "parameter": {"type": "string"}, "values": _NUMBER_ARRAY,
         "equilibrium_guess": _OBJECT, "approve_heavy": {"type": "boolean"}, "approve_migration": {"type": "boolean"}}, additional=True),
    "axiomize.model_numerical_verify": _schema("Run an approval-gated mesh/tolerance refinement study.",
        {"model_ir": _OBJECT, "model": _OBJECT, "t_span": _NUMBER_ARRAY, "points": {"type": "integer", "maximum": 200000},
         "tolerance": _NUMBER, "approve_heavy": {"type": "boolean"}, "approve_migration": {"type": "boolean"}}, additional=True),
    "axiomize.model_stop_check": _schema("Apply explicit convergence/budget/uncertainty stopping rules.",
        {"history": _NUMBER_ARRAY, "relative_tolerance": _NUMBER, "absolute_tolerance": _NUMBER,
         "patience": {"type": "integer"}, "budget_used": _NUMBER, "budget_limit": _NUMBER,
         "uncertainty": _NUMBER, "uncertainty_target": _NUMBER}, ["history"], additional=True),
    "axiomize.model_surrogate": _schema("Fit, generate or evaluate a holdout-validated surrogate.",
        {"mode": {"type": "string", "enum": ["fit", "generate", "evaluate"]}, "model_ir": _OBJECT, "model": _OBJECT,
         "training_data": _OBJECT, "surrogate": _OBJECT, "inputs": _OBJECT, "parameter_ranges": _OBJECT,
         "output_specs": {"type": "array", "items": _OBJECT}, "t_span": _NUMBER_ARRAY,
         "points": {"type": "integer", "maximum": 200000}, "samples": {"type": "integer", "maximum": 2000},
         "degree": {"type": "integer"}, "holdout_fraction": _NUMBER, "minimum_r2": _NUMBER, "maximum_nrmse": _NUMBER,
         "seed": {"type": "integer"}, "approve_heavy": {"type": "boolean"}, "allow_extrapolation": {"type": "boolean"},
         "allow_unvalidated": {"type": "boolean"}, "approve_migration": {"type": "boolean"}}, additional=True),
}

_LEGACY_TOOL_NAMES = {
    "solve_sir": "axiomize.solve", "validate_sir": "axiomize.validate", "fit_model": "axiomize.fit_model",
    "list_tools": "axiomize.list_tools", "get_capabilities": "axiomize.get_capabilities",
}


def _call_tool(name: str, arguments: dict[str, Any], *, run_root: str | Path = ".") -> dict[str, Any]:
    from axiomize.application import advanced_services as ads
    from axiomize.application import general_services as gs
    from axiomize.application import surrogate_services as ss
    from axiomize.application import services
    from axiomize.routing.router import classify

    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must be a JSON object")
    name = _LEGACY_TOOL_NAMES.get(name, name)
    general = {
        "axiomize.model_plan": gs.model_plan_service,
        "axiomize.model_validate": gs.model_validate_service,
        "axiomize.model_simulate": gs.model_simulate_service,
        "axiomize.model_fit": gs.model_fit_service,
        "axiomize.model_compare": gs.model_compare_service,
        "axiomize.model_repair": gs.model_repair_service,
        "axiomize.model_export": gs.model_export_service,
        "axiomize.model_stability": gs.model_stability_service,
        "axiomize.model_validity": gs.model_validity_service,
        "axiomize.model_discovery": gs.model_discovery_service,
        "axiomize.experiment_design": gs.experiment_design_service,
        "axiomize.model_uncertainty": ads.model_uncertainty_service,
        "axiomize.model_bifurcation": ads.model_bifurcation_service,
        "axiomize.model_numerical_verify": ads.model_numerical_verification_service,
        "axiomize.model_stop_check": ads.model_stopping_service,
        "axiomize.model_surrogate": ss.model_surrogate_service,
    }
    if name in general:
        return general[name](arguments)
    if name == "axiomize.intake": return services.intake_service(arguments)
    if name == "axiomize.workflow_policy": return services.workflow_policy_service(arguments)
    if name == "axiomize.clean_data": return services.clean_data_service(arguments)
    if name == "axiomize.compare_runs":
        confined = dict(arguments)
        confined["before_dir"] = str(resolve_run_directory(run_root, str(arguments["before_dir"])))
        confined["after_dir"] = str(resolve_run_directory(run_root, str(arguments["after_dir"])))
        return services.compare_runs_service(confined)
    if name in ("axiomize.solve", "axiomize.simulate"): return services.solve_sir_service(arguments)
    if name == "axiomize.validate": return services.validate_sir_service(arguments)
    if name == "axiomize.fit_model":
        if arguments.get("model", "logistic") == "sir" and "N" in arguments:
            import numpy as np
            from axiomize.fitting.estimator import fit_sir_curve
            t = np.asarray(arguments["t"], dtype=float); y = np.asarray(arguments["y"], dtype=float)
            return fit_sir_curve(t, y, float(arguments["N"]), float(arguments.get("I0", y[0]))).to_dict()
        return services.fit_logistic_service(arguments)
    if name == "axiomize.cross_validate": return services.solve_sir_service(arguments)["cross_validation"]
    if name == "axiomize.sensitivity_analysis": return services.sensitivity_service(arguments)
    if name == "axiomize.uncertainty_analysis": return services.uncertainty_service(arguments)
    if name == "axiomize.falsify": return services.falsify_service(arguments)
    if name == "axiomize.compare_models": return services.compare_service(arguments)
    if name == "axiomize.select_tools": return classify({"signals": arguments.get("signals", [])}).to_dict()
    if name == "axiomize.list_tools": return services.tools_service()
    if name == "axiomize.get_capabilities": return services.capabilities_service()
    if name in ("axiomize.inspect_run", "axiomize.reproduce"):
        run = RunState.load_under_root(run_root, str(arguments["run_dir"]))
        return {"input_hash": run.input_hash(), "results": run.results, "problem_definition": run.problem_definition}
    raise KeyError(f"unknown tool: {name}")


def list_tools() -> list[dict[str, Any]]:
    aliases = [{"name": name} for name in sorted(_LEGACY_TOOL_NAMES)]
    canonical = [{"name": name, **_TOOL_SCHEMAS[name]} for name in sorted(_TOOL_SCHEMAS)]
    return aliases + canonical


def call_tool(name: str, arguments: dict[str, Any], *, run_root: str | Path = ".") -> dict[str, Any]:
    try:
        return _call_tool(name, arguments, run_root=run_root)
    except KeyError as exc:
        return {"error": str(exc)}
    except (ValueError, OSError) as exc:
        return {"error": str(exc)}
    except Exception:
        return {"error": "internal tool error"}


def handle_message(message: dict[str, Any], *, run_root: str | Path = ".") -> dict[str, Any]:
    if not isinstance(message, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "request must be an object"}}
    method = message.get("method", ""); msg_id = message.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05",
            "serverInfo": {"name": SERVER_NAME, "version": API_VERSION}, "capabilities": {"tools": {}}}}
    if method in ("notifications/initialized", "notifications/cancelled", "ping"):
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": [
            {"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]}
            for name, spec in sorted(_TOOL_SCHEMAS.items())]}}
    if method == "tools/call":
        params = message.get("params", {})
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32602, "message": "invalid tools/call params"}}
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32602, "message": "arguments must be an object"}}
        try:
            result = _call_tool(params["name"], arguments, run_root=run_root)
        except KeyError as exc:
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": str(exc)}}
        except (ValueError, OSError) as exc:
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32602, "message": str(exc)}}
        except Exception:
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32000, "message": "internal tool error"}}
        safe = json_safe(result)
        return {"jsonrpc": "2.0", "id": msg_id, "result": {
            "content": [{"type": "text", "text": json.dumps(safe, allow_nan=False, separators=(",", ":"))}],
            "isError": False, **({"status": safe["status"]} if isinstance(safe, dict) and "status" in safe else {})}}
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "unknown method"}}


def serve_stdio(*, run_root: str | Path = ".") -> None:
    root = Path(run_root).expanduser().resolve()
    stream = sys.stdin.buffer
    while True:
        raw = stream.readline(MAX_MCP_MESSAGE_BYTES + 1)
        if not raw:
            return
        if len(raw) > MAX_MCP_MESSAGE_BYTES:
            # Consume the remainder of the oversized frame so the next request
            # starts on a clean line.
            while raw and not raw.endswith(b"\n"):
                raw = stream.readline(MAX_MCP_MESSAGE_BYTES + 1)
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "MCP message too large"}}
        else:
            raw = raw.strip()
            if not raw:
                continue
            try:
                message = json.loads(raw.decode("utf-8"))
                response = handle_message(message, run_root=root)
            except (UnicodeError, json.JSONDecodeError):
                response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        sys.stdout.write(json.dumps(json_safe(response), allow_nan=False, separators=(",", ":")) + "\n")
        sys.stdout.flush()
