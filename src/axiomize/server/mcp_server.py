"""MCP stdio adapter over shared Axiomize application services."""

from __future__ import annotations

import json
import sys
from typing import Any

SERVER_NAME = "axiomize"
API_VERSION = "v1"

_NUMBER = {"type": "number"}
_NUMBER_ARRAY = {"type": "array", "items": {"type": "number"}, "minItems": 2}
_OBJECT = {"type": "object", "additionalProperties": True}


def _schema(description: str, properties: dict[str, Any] | None = None,
            required: list[str] | None = None, *, additional: bool = False) -> dict[str, Any]:
    body: dict[str, Any] = {"type": "object", "properties": properties or {}, "additionalProperties": additional}
    if required:
        body["required"] = required
    return {"description": description, "inputSchema": body}


_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "axiomize.intake": _schema(
        "Clarify a vague idea and return the next modeling question or ready plan.",
        {"idea": {"type": "string", "minLength": 1}, "context": _OBJECT, "signals": _OBJECT,
         "rigor": {"type": "string"}, "question_mode": {"type": "string"},
         "preferred_question_mode": {"type": "string"}, "permissions": _OBJECT}, ["idea"]),
    "axiomize.workflow_policy": _schema(
        "Return workflow policy, rigor recommendation and explicit consent boundaries.",
        {"signals": _OBJECT, "question_mode": {"type": "string"}, "permissions": _OBJECT}),
    "axiomize.clean_data": _schema(
        "Clean paired numeric observations with an audit trail.",
        {"t": _NUMBER_ARRAY, "y": _NUMBER_ARRAY, "drop_nonfinite": {"type": "boolean"},
         "sort_time": {"type": "boolean"}, "duplicate_policy": {"type": "string"}}, ["t", "y"]),
    "axiomize.compare_runs": _schema(
        "Compare two stored reproducible runs.",
        {"before_dir": {"type": "string"}, "after_dir": {"type": "string"}}, ["before_dir", "after_dir"]),
    "axiomize.solve": _schema(
        "Solve the backward-compatible reference SIR model.",
        {"beta": _NUMBER, "gamma": _NUMBER, "I0": _NUMBER,
         "N": {"type": "number", "exclusiveMinimum": 0}, "days": _NUMBER}),
    "axiomize.fit_model": _schema(
        "Fit backward-compatible logistic or SIR data.",
        {"t": _NUMBER_ARRAY, "y": _NUMBER_ARRAY, "model": {"type": "string"},
         "N": _NUMBER, "I0": _NUMBER}, ["t", "y"]),
    "axiomize.simulate": _schema("Simulate the backward-compatible reference SIR model.",
        {"beta": _NUMBER, "gamma": _NUMBER, "I0": _NUMBER, "N": _NUMBER, "days": _NUMBER}),
    "axiomize.validate": _schema("Validate the backward-compatible reference SIR model.",
        {"beta": _NUMBER, "gamma": _NUMBER, "I0": _NUMBER, "N": _NUMBER, "days": _NUMBER}),
    "axiomize.cross_validate": _schema("Cross-check SIR numerical output against theory.",
        {"beta": _NUMBER, "gamma": _NUMBER, "I0": _NUMBER, "N": _NUMBER}),
    "axiomize.sensitivity_analysis": _schema("Run SIR sensitivity analysis.",
        {"params": _OBJECT, "N": _NUMBER, "I0": _NUMBER, "target": {"type": "string"}}, ["params"]),
    "axiomize.uncertainty_analysis": _schema("Compute parameter uncertainty intervals.",
        {"fit": _OBJECT, "params": _OBJECT}),
    "axiomize.falsify": _schema("Evaluate explicit falsifiers.",
        {"falsifiers": {"type": "array", "items": _OBJECT}, "observations": _OBJECT}),
    "axiomize.compare_models": _schema("Compare reference logistic/SIR fits.",
        {"t": _NUMBER_ARRAY, "y": _NUMBER_ARRAY, "N": _NUMBER, "I0": _NUMBER}, ["t", "y"]),
    "axiomize.select_tools": _schema("Select scientific tools from explicit signals.",
        {"signals": {"type": "array", "items": {"type": "string"}}}, ["signals"]),
    "axiomize.list_tools": _schema("List live scientific backends."),
    "axiomize.get_capabilities": _schema("Return machine-readable engine capabilities."),
    "axiomize.inspect_run": _schema("Inspect a recorded reproducible run.",
        {"run_dir": {"type": "string"}}, ["run_dir"]),
    "axiomize.reproduce": _schema("Load a recorded run for reproducibility inspection.",
        {"run_dir": {"type": "string"}}, ["run_dir"]),

    "axiomize.model_plan": _schema(
        "Infer a scientific domain and rank 2-3 model families from an idea, or build an execution plan from Model IR.",
        {"idea": {"type": "string"}, "domain": {"type": "string"}, "signals": _OBJECT,
         "model_ir": _OBJECT, "model": _OBJECT, "action": {"type": "string"},
         "points": {"type": "integer"}, "samples": {"type": "integer"},
         "approve_migration": {"type": "boolean"}}, additional=True),
    "axiomize.model_validate": _schema(
        "Validate versioned Model IR structure, units, scientific constraints and causal-identification claims.",
        {"model_ir": _OBJECT, "model": _OBJECT, "approve_migration": {"type": "boolean"}}, additional=True),
    "axiomize.model_simulate": _schema(
        "Simulate a versioned Model IR with visible solver attempts and scientific checks.",
        {"model_ir": _OBJECT, "model": _OBJECT, "t_span": _NUMBER_ARRAY, "points": {"type": "integer"},
         "parameter_overrides": _OBJECT, "seed": {"type": "integer"},
         "approve_heavy": {"type": "boolean"}, "approve_migration": {"type": "boolean"}}, additional=True),
    "axiomize.model_fit": _schema(
        "Fit parameters marked fit=true in a versioned ODE Model IR with identifiability and residual diagnostics.",
        {"model_ir": _OBJECT, "model": _OBJECT, "time": _NUMBER_ARRAY,
         "observations": _OBJECT, "approve_heavy": {"type": "boolean"},
         "approve_migration": {"type": "boolean"}}, additional=True),
    "axiomize.model_compare": _schema(
        "Rank fitted model candidates by AIC/BIC/SSE.",
        {"fits": _OBJECT, "criterion": {"type": "string"}}, ["fits"]),
    "axiomize.model_repair": _schema(
        "Request constraint-driven rebuild/refit; never applies a repair without explicit approval.",
        {"model_ir": _OBJECT, "model": _OBJECT, "validation": _OBJECT,
         "approve_repair": {"type": "boolean"}, "approve_migration": {"type": "boolean"}}, additional=True),
    "axiomize.model_export": _schema(
        "Export Model IR as JSON/Python/YAML/notebook or explicit versioned SBML/CellML subsets.",
        {"model_ir": _OBJECT, "model": _OBJECT, "format": {"type": "string"},
         "approve_migration": {"type": "boolean"}}, additional=True),
    "axiomize.model_stability": _schema(
        "Linearize an ODE Model IR at a supplied state and report eigenvalue stability.",
        {"model_ir": _OBJECT, "model": _OBJECT, "state": _OBJECT, "parameter_overrides": _OBJECT}, additional=True),
    "axiomize.model_validity": _schema(
        "Scan an explicit parameter range to estimate the observed validity region; approval-gated.",
        {"model_ir": _OBJECT, "model": _OBJECT, "parameter": {"type": "string"},
         "values": _NUMBER_ARRAY, "t_span": _NUMBER_ARRAY, "points": {"type": "integer"},
         "approve_heavy": {"type": "boolean"}}, additional=True),
    "axiomize.model_discovery": _schema(
        "Discover sparse candidate dynamics from data; output remains scientifically unverified until validation.",
        {"time": _NUMBER_ARRAY, "state": _NUMBER_ARRAY, "degree": {"type": "integer"},
         "threshold": _NUMBER, "approve_heavy": {"type": "boolean"}}, ["time", "state"]),
    "axiomize.experiment_design": _schema(
        "Rank candidate observation times by an information-gain proxy; approval-gated.",
        {"model_ir": _OBJECT, "model": _OBJECT, "parameter": {"type": "string"},
         "candidate_times": _NUMBER_ARRAY, "horizon": _NUMBER,
         "delta_fraction": _NUMBER, "approve_heavy": {"type": "boolean"}}, additional=True),
    "axiomize.model_surrogate": _schema(
        "Fit, generate, or evaluate a holdout-validated surrogate. Full-model training-data generation is approval-gated and extrapolation is blocked by default.",
        {"mode": {"type": "string", "enum": ["fit", "generate", "evaluate"]},
         "model_ir": _OBJECT, "model": _OBJECT, "training_data": _OBJECT,
         "surrogate": _OBJECT, "inputs": _OBJECT, "parameter_ranges": _OBJECT,
         "output_specs": {"type": "array", "items": _OBJECT}, "t_span": _NUMBER_ARRAY,
         "points": {"type": "integer"}, "samples": {"type": "integer"},
         "degree": {"type": "integer"}, "holdout_fraction": _NUMBER,
         "minimum_r2": _NUMBER, "maximum_nrmse": _NUMBER, "seed": {"type": "integer"},
         "approve_heavy": {"type": "boolean"}, "allow_extrapolation": {"type": "boolean"},
         "allow_unvalidated": {"type": "boolean"}, "approve_migration": {"type": "boolean"}}, additional=True),
}

_LEGACY_TOOL_NAMES = {
    "solve_sir": "axiomize.solve",
    "validate_sir": "axiomize.validate",
    "fit_model": "axiomize.fit_model",
    "list_tools": "axiomize.list_tools",
    "get_capabilities": "axiomize.get_capabilities",
}


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from axiomize.application import general_services as gs
    from axiomize.application import surrogate_services as ss
    from axiomize.application import services
    from axiomize.routing.router import classify
    from axiomize.runs.state import RunState

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
        "axiomize.model_surrogate": ss.model_surrogate_service,
    }
    if name in general:
        return general[name](arguments)
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
    aliases = [{"name": name} for name in sorted(_LEGACY_TOOL_NAMES)]
    canonical = [{"name": name, **_TOOL_SCHEMAS[name]} for name in sorted(_TOOL_SCHEMAS)]
    return aliases + canonical


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
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
                    {"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]}
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
                "result": {"content": [{"type": "text", "text": json.dumps(result, default=str)}],
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
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                         "error": {"code": -32700, "message": str(exc)}}) + "\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps(handle_message(message), default=str) + "\n")
        sys.stdout.flush()
