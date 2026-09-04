"""REST API adapter (API v1).

Stdlib-only HTTP layer over shared application services. Legacy SIR/logistic
payloads remain supported while Model IR payloads use the general engine.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", 0) or 0)
    if length <= 0:
        return {}
    payload = json.loads(handler.rfile.read(length).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    return payload


def _send(handler: BaseHTTPRequestHandler, code: int, payload: Any) -> None:
    body = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _strip_api_prefix(path: str) -> str:
    return path[3:] if path.startswith("/v1/") else path


def _has_model_ir(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("model_ir", payload.get("model")), dict)


class Handler(BaseHTTPRequestHandler):
    server_version = "AxiomizeREST/1.0"

    def log_message(self, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        from axiomize.application import services

        path = _strip_api_prefix(urlparse(self.path).path)
        if path == "/tools":
            _send(self, 200, services.tools_service())
        elif path == "/capabilities":
            _send(self, 200, services.capabilities_service())
        elif path == "/workflow-policy":
            _send(self, 200, services.workflow_policy_service({}))
        elif path.startswith("/runs/"):
            run_dir = path[len("/runs/"):]
            from axiomize.runs.state import RunState
            try:
                run = RunState.load(run_dir)
            except (OSError, ValueError) as exc:
                _send(self, 404, {"error": str(exc)})
                return
            _send(self, 200, {"input_hash": run.input_hash(), "results": run.results})
        else:
            _send(self, 404, {"error": f"unknown route: {path}"})

    def do_POST(self) -> None:
        from axiomize.application import general_services, services

        path = _strip_api_prefix(urlparse(self.path).path)
        try:
            payload = _read_json(self)
            if path == "/intake":
                _send(self, 200, services.intake_service(payload))
            elif path == "/workflow-policy":
                _send(self, 200, services.workflow_policy_service(payload))
            elif path == "/clean-data":
                _send(self, 200, services.clean_data_service(payload))
            elif path == "/compare-runs":
                _send(self, 200, services.compare_runs_service(payload))
            elif path == "/model":
                _send(self, 200, general_services.model_plan_service(payload))
            elif path in ("/solve", "/simulate"):
                if _has_model_ir(payload):
                    _send(self, 200, general_services.model_simulate_service(payload))
                else:
                    _send(self, 200, services.solve_sir_service(payload))
            elif path == "/fit":
                if _has_model_ir(payload):
                    _send(self, 200, general_services.model_fit_service(payload))
                else:
                    _send(self, 200, services.fit_logistic_service(payload))
            elif path == "/validate":
                if _has_model_ir(payload):
                    _send(self, 200, general_services.model_validate_service(payload))
                else:
                    _send(self, 200, services.validate_sir_service(payload))
            elif path == "/model/compare":
                _send(self, 200, general_services.model_compare_service(payload))
            elif path == "/model/repair":
                _send(self, 200, general_services.model_repair_service(payload))
            elif path == "/model/export":
                _send(self, 200, general_services.model_export_service(payload))
            elif path == "/model/stability":
                _send(self, 200, general_services.model_stability_service(payload))
            elif path == "/model/validity-scan":
                _send(self, 200, general_services.model_validity_service(payload))
            elif path == "/model/discover":
                _send(self, 200, general_services.model_discovery_service(payload))
            elif path == "/model/experiment-design":
                _send(self, 200, general_services.experiment_design_service(payload))
            elif path == "/cross-validate":
                _send(self, 200, services.solve_sir_service(payload)["cross_validation"])
            elif path == "/falsify":
                _send(self, 200, services.falsify_service(payload))
            elif path == "/compare":
                _send(self, 200, services.compare_service(payload))
            elif path == "/sensitivity":
                _send(self, 200, services.sensitivity_service(payload))
            elif path == "/uncertainty":
                _send(self, 200, services.uncertainty_service(payload))
            elif path.startswith("/runs/") and path.endswith("/reproduce"):
                run_dir = path[len("/runs/"):-len("/reproduce")]
                from axiomize.runs.state import RunState
                run = RunState.load(run_dir)
                _send(self, 200, {"input_hash": run.input_hash(), "results": run.results})
            else:
                _send(self, 404, {"error": f"unknown route: {path}"})
        except (ValueError, KeyError) as exc:
            _send(self, 400, {"error": f"{type(exc).__name__}: {exc}"})
        except Exception as exc:
            _send(self, 500, {"error": f"{type(exc).__name__}: {exc}"})


def start_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)
