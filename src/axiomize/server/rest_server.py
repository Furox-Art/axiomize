"""REST API adapter (API v1).

Stdlib-only HTTP layer over shared application services. Legacy SIR/logistic
payloads remain supported while Model IR payloads use the general engine.

Security boundary:
- localhost is the default and requires no token;
- non-loopback binding requires *both* ``allow_remote=True`` and an auth token;
- request bodies, concurrency and run-file access are bounded;
- run identifiers are confined beneath a configured run root.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from axiomize.limits import MAX_JSON_BYTES
from axiomize.runs.state import RunState, resolve_run_directory

_MAX_CONCURRENT_REQUESTS = 32


class RequestTooLarge(ValueError):
    pass


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    raw_length = handler.headers.get("Content-Length")
    if raw_length is None:
        return {}
    try:
        length = int(raw_length)
    except ValueError as exc:
        raise ValueError("invalid Content-Length") from exc
    if length < 0:
        raise ValueError("Content-Length cannot be negative")
    if length > MAX_JSON_BYTES:
        raise RequestTooLarge(f"request body exceeds hard limit of {MAX_JSON_BYTES} bytes")
    if length == 0:
        return {}
    raw = handler.rfile.read(length)
    if len(raw) != length:
        raise ValueError("request body ended before Content-Length bytes were received")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON request body: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    return payload


def _send(handler: BaseHTTPRequestHandler, code: int, payload: Any) -> None:
    body = json.dumps(payload, default=str, allow_nan=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.end_headers()
    handler.wfile.write(body)


def _strip_api_prefix(path: str) -> str:
    return path[3:] if path.startswith("/v1/") else path


def _has_model_ir(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("model_ir", payload.get("model")), dict)


def _is_loopback_host(host: str) -> bool:
    normalized = str(host).strip().lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        *,
        run_root: Path,
        auth_token: str | None,
        max_concurrent_requests: int,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.run_root = run_root.resolve()
        self.auth_token = auth_token
        self._request_slots = threading.BoundedSemaphore(max_concurrent_requests)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._request_slots.acquire(blocking=False):
            try:
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Content-Length: 0\r\nConnection: close\r\n\r\n"
                )
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._request_slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "AxiomizeREST/1.1"

    @property
    def _server(self) -> BoundedThreadingHTTPServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, *args: Any) -> None:
        # Library server stays quiet by default. Never echo request bodies/tokens.
        pass

    def _authorized(self) -> bool:
        expected = self._server.auth_token
        if expected is None:
            return True
        auth = self.headers.get("Authorization", "")
        supplied = auth[7:] if auth.startswith("Bearer ") else self.headers.get("X-Axiomize-Token", "")
        return bool(supplied) and hmac.compare_digest(str(supplied), expected)

    def _require_authorized(self) -> bool:
        if self._authorized():
            return True
        _send(self, 401, {"error": "unauthorized"})
        return False

    def _load_run(self, run_id: str) -> RunState:
        return RunState.load_under_root(self._server.run_root, unquote(run_id))

    def do_GET(self) -> None:
        from axiomize.application import services

        if not self._require_authorized():
            return
        path = _strip_api_prefix(urlparse(self.path).path)
        if path == "/tools":
            _send(self, 200, services.tools_service())
        elif path == "/capabilities":
            _send(self, 200, services.capabilities_service())
        elif path == "/workflow-policy":
            _send(self, 200, services.workflow_policy_service({}))
        elif path.startswith("/runs/"):
            run_id = path[len("/runs/"):]
            try:
                run = self._load_run(run_id)
            except (OSError, ValueError):
                _send(self, 404, {"error": "run not found or failed integrity checks"})
                return
            _send(self, 200, {"input_hash": run.input_hash(), "results": run.results})
        else:
            _send(self, 404, {"error": "unknown route"})

    def do_POST(self) -> None:
        from axiomize.application import advanced_services, general_services, services, surrogate_services

        if not self._require_authorized():
            return
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
                confined = dict(payload)
                for field in ("before_dir", "after_dir"):
                    raw = str(confined.get(field, "")).strip()
                    if not raw:
                        raise ValueError(f"{field} is required")
                    confined[field] = str(resolve_run_directory(self._server.run_root, unquote(raw)))
                _send(self, 200, services.compare_runs_service(confined))
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
            elif path == "/model/numerical-verify":
                _send(self, 200, advanced_services.model_numerical_verification_service(payload))
            elif path == "/model/surrogate":
                _send(self, 200, surrogate_services.model_surrogate_service(payload))
            elif path == "/model/uncertainty":
                _send(self, 200, advanced_services.model_uncertainty_service(payload))
            elif path == "/model/bifurcation":
                _send(self, 200, advanced_services.model_bifurcation_service(payload))
            elif path == "/model/stop-check":
                _send(self, 200, advanced_services.model_stopping_service(payload))
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
                run_id = path[len("/runs/"):-len("/reproduce")]
                run = self._load_run(run_id)
                _send(self, 200, {"input_hash": run.input_hash(), "results": run.results})
            else:
                _send(self, 404, {"error": "unknown route"})
        except RequestTooLarge as exc:
            _send(self, 413, {"error": str(exc)})
        except (ValueError, KeyError) as exc:
            _send(self, 400, {"error": str(exc)})
        except Exception:
            # Do not leak filesystem paths, dependency internals or secrets to a
            # remote caller. Detailed tracebacks belong in the embedding app.
            _send(self, 500, {"error": "internal server error"})


def start_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    run_root: str | Path = ".",
    allow_remote: bool = False,
    auth_token: str | None = None,
    max_concurrent_requests: int = _MAX_CONCURRENT_REQUESTS,
) -> ThreadingHTTPServer:
    host = str(host).strip()
    if not host:
        raise ValueError("host must be non-empty")
    if not _is_loopback_host(host):
        if not allow_remote:
            raise ValueError("non-loopback REST binding requires allow_remote=True")
        if not isinstance(auth_token, str) or len(auth_token) < 16:
            raise ValueError("remote REST binding requires an auth token of at least 16 characters")
    port = int(port)
    if port < 0 or port > 65535:
        raise ValueError("port must be between 0 and 65535")
    max_concurrent_requests = int(max_concurrent_requests)
    if max_concurrent_requests < 1 or max_concurrent_requests > 256:
        raise ValueError("max_concurrent_requests must be between 1 and 256")
    root = Path(run_root).expanduser().resolve()
    return BoundedThreadingHTTPServer(
        (host, port),
        Handler,
        run_root=root,
        auth_token=auth_token,
        max_concurrent_requests=max_concurrent_requests,
    )
