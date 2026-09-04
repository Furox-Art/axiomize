"""REST API adapter (PHASE 8, API v1).

Stdlib-only HTTP layer over the shared application services.
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
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def _send(handler: BaseHTTPRequestHandler, code: int, payload: Any) -> None:
    body = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _strip_api_prefix(path: str) -> str:
    return path[3:] if path.startswith("/v1/") else path


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
        elif path.startswith("/runs/"):
            run_dir = path[len("/runs/"):]
            from axiomize.runs.state import RunState

            try:
                run = RunState.load(run_dir)
            except (OSError, ValueError) as exc:
                _send(self, 404, {"error": str(exc)})
                return
            _send(self, 200, {"input_hash": run.input_hash(),
                              "results": run.results})
        else:
            _send(self, 404, {"error": f"unknown route: {path}"})

    def do_POST(self) -> None:
        from axiomize.application import services

        path = _strip_api_prefix(urlparse(self.path).path)
        try:
            payload = _read_json(self)
            if path in ("/model", "/solve", "/simulate"):
                _send(self, 200, services.solve_sir_service(payload))
            elif path == "/fit":
                _send(self, 200, services.fit_logistic_service(payload))
            elif path == "/validate":
                _send(self, 200, services.validate_sir_service(payload))
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
                _send(self, 200, {"input_hash": run.input_hash(),
                                  "results": run.results})
            else:
                _send(self, 404, {"error": f"unknown route: {path}"})
        except (ValueError, KeyError) as exc:
            _send(self, 400, {"error": f"{type(exc).__name__}: {exc}"})
        except Exception as exc:
            _send(self, 500, {"error": f"{type(exc).__name__}: {exc}"})


def start_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)
