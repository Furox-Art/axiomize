"""Round-2 coverage hardening for ``axiomize.server.rest_server``.

Covers request parsing, loopback classification, run lookup/reproduce routes,
service routing (clean-data, compare-runs, model fit/validate), concurrency-slot
backpressure and bind-time validation. All servers bind to 127.0.0.1 on an
ephemeral port.
"""
from __future__ import annotations

import io
import json
import threading
import urllib.error
import urllib.request
from socketserver import ThreadingMixIn
from types import SimpleNamespace

import pytest

from axiomize.runs.state import RunState
from axiomize.server.rest_server import (
    BoundedThreadingHTTPServer,
    Handler,
    _is_loopback_host,
    _read_json,
    start_server,
)

MODEL_IR = {
    "schema_version": "1.0",
    "name": "r2a-model",
    "domain": "general",
    "family": "algebraic",
    "variables": [{"name": "x", "role": "state", "initial": 1.0}],
    "equations": [{"target": "x", "kind": "algebraic", "expression": "1"}],
}


@pytest.fixture
def live_server(tmp_path):
    server = start_server("127.0.0.1", 0, run_root=tmp_path, connection_timeout_s=10)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", tmp_path
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=10)


def _request(base, path, payload=None, *, method="GET", raw=None, headers=None):
    data = raw
    if data is None and payload is not None:
        data = json.dumps(payload, allow_nan=False).encode("utf-8")
    if method == "POST" and data is None:
        data = b""
    request = urllib.request.Request(
        base + path, data=data, headers=headers or {}, method=method
    )
    try:
        response = urllib.request.urlopen(request, timeout=60)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        body = response.read()
    return response.status, (json.loads(body) if body else {})


def _fake_handler(headers: dict[str, str], body: bytes) -> SimpleNamespace:
    return SimpleNamespace(headers=headers, rfile=io.BytesIO(body))


def test_read_json_parsing_contracts() -> None:
    assert _read_json(_fake_handler({}, b"")) == {}
    assert _read_json(_fake_handler({"Content-Length": "0"}, b"")) == {}
    with pytest.raises(ValueError, match="invalid Content-Length"):
        _read_json(_fake_handler({"Content-Length": "abc"}, b""))
    with pytest.raises(ValueError, match="cannot be negative"):
        _read_json(_fake_handler({"Content-Length": "-2"}, b""))
    with pytest.raises(ValueError, match="ended before Content-Length"):
        _read_json(_fake_handler({"Content-Length": "4"}, b"ab"))
    with pytest.raises(ValueError, match="must be a JSON object"):
        _read_json(_fake_handler({"Content-Length": "3"}, b"[1]"))
    assert _read_json(_fake_handler({"Content-Length": "8"}, b'{"a": 1}')) == {"a": 1}


def test_loopback_host_classification() -> None:
    assert _is_loopback_host("localhost") is True
    assert _is_loopback_host("  LOCALHOST  ") is True
    assert _is_loopback_host("127.0.0.1") is True
    assert _is_loopback_host("::1") is True
    assert _is_loopback_host("example.invalid") is False
    assert _is_loopback_host("") is False


def test_start_server_rejects_unsafe_bindings_and_limits() -> None:
    with pytest.raises(ValueError, match="host must be non-empty"):
        start_server("")
    with pytest.raises(ValueError, match="requires allow_remote=True"):
        start_server("0.0.0.0", 0)
    with pytest.raises(ValueError, match="auth token of at least 16 characters"):
        start_server("0.0.0.0", 0, allow_remote=True)
    with pytest.raises(ValueError, match="auth token of at least 16 characters"):
        start_server("0.0.0.0", 0, allow_remote=True, auth_token="short")
    with pytest.raises(ValueError, match="port must be between 0 and 65535"):
        start_server("127.0.0.1", 70000)
    with pytest.raises(ValueError, match="max_concurrent_requests must be between 1 and 256"):
        start_server("127.0.0.1", 0, max_concurrent_requests=0)
    with pytest.raises(ValueError, match="connection_timeout_s must be numeric"):
        start_server("127.0.0.1", 0, connection_timeout_s="abc")
    with pytest.raises(ValueError, match="between 1 and 300 seconds"):
        start_server("127.0.0.1", 0, connection_timeout_s=0.5)
    with pytest.raises(ValueError, match="between 1 and 300 seconds"):
        start_server("127.0.0.1", 0, connection_timeout_s=301)


def test_run_lookup_and_reproduce_share_the_same_contract(live_server) -> None:
    base, root = live_server
    run = RunState(problem_definition="cov100", parameters={"k": 0.5}, results={"peak": 1.25})
    run.save(root / "run-a")

    status, body = _request(base, "/runs/run-a")
    assert status == 200
    assert body["input_hash"] == run.input_hash()
    assert body["results"] == {"peak": 1.25}

    status, body = _request(base, "/runs/run-a/reproduce", method="POST")
    assert status == 200
    assert body["input_hash"] == run.input_hash()
    assert body["results"] == {"peak": 1.25}

    status, body = _request(base, "/runs/absent/reproduce", method="POST")
    assert status == 404
    assert body["error"] == "run not found or failed integrity checks"


def test_clean_data_route_returns_the_cleaned_series(live_server) -> None:
    base, _ = live_server
    status, body = _request(
        base, "/clean-data", {"t": [2.0, 1.0, 3.0], "y": [20.0, 10.0, 30.0]}, method="POST"
    )
    assert status == 200
    assert body["cleaned_t"] == [1.0, 2.0, 3.0]
    assert body["cleaned_y"] == [10.0, 20.0, 30.0]
    assert body["audit"][0]["operation"] == "sort_by_time"
    assert body["material_change"] is False


def test_compare_runs_requires_both_confined_directories(live_server) -> None:
    base, root = live_server
    status, body = _request(base, "/compare-runs", {"after_dir": "run-b"}, method="POST")
    assert status == 400
    assert body["error"] == "before_dir is required"

    RunState(parameters={"k": 0.5}, results={"peak": 1.0}).save(root / "run-a")
    RunState(parameters={"k": 0.8}, results={"peak": 1.5}).save(root / "run-b")
    status, body = _request(
        base, "/compare-runs", {"before_dir": "run-a", "after_dir": "run-b"}, method="POST"
    )
    assert status == 200
    assert body["same_input_hash"] is False
    assert body["same_results"] is False
    assert body["differences"]["parameters"]["k"] == {"before": 0.5, "after": 0.8}


def test_model_ir_payloads_route_to_general_fit_and_validate_services(live_server) -> None:
    base, _ = live_server
    status, body = _request(base, "/validate", {"model_ir": MODEL_IR}, method="POST")
    assert status == 200
    assert body["model_ir"]["name"] == "r2a-model"
    assert body["validation"]["status"] in {"PASS", "WARN", "FAIL"}

    status, body = _request(base, "/fit", {"model_ir": MODEL_IR}, method="POST")
    assert status in {200, 400}
    assert isinstance(body, dict)
    assert status != 500


def test_unexpected_service_failure_maps_to_internal_server_error(
    live_server, monkeypatch: pytest.MonkeyPatch
) -> None:
    from axiomize.application import services

    def explode(payload: dict) -> dict:
        raise RuntimeError("unexpected service fault")

    monkeypatch.setattr(services, "intake_service", explode)
    base, _ = live_server
    status, body = _request(base, "/intake", {}, method="POST")
    assert status == 500
    assert body == {"error": "internal server error"}


class _FakeRequest:
    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.closed = False
        self.shutdown_called = False

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)

    def shutdown(self, how: int) -> None:
        self.shutdown_called = True

    def close(self) -> None:
        self.closed = True


def test_exhausted_concurrency_slots_receive_503_and_connection_close(tmp_path) -> None:
    server = BoundedThreadingHTTPServer(
        ("127.0.0.1", 0), Handler, run_root=tmp_path, auth_token=None,
        max_concurrent_requests=1, connection_timeout_s=1.0,
    )
    try:
        assert server._request_slots.acquire(blocking=False) is True
        request = _FakeRequest()
        server.process_request(request, ("127.0.0.1", 12345))
        assert request.sent == [
            b"HTTP/1.1 503 Service Unavailable\r\n"
            b"Content-Length: 0\r\nConnection: close\r\n\r\n"
        ]
        assert request.shutdown_called is True
        assert request.closed is True
    finally:
        server.server_close()


def test_thread_dispatch_failure_releases_the_concurrency_slot(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_dispatch(self, request, client_address):  # noqa: ANN001 - test double
        raise RuntimeError("dispatch failed")

    monkeypatch.setattr(ThreadingMixIn, "process_request", fail_dispatch)
    server = BoundedThreadingHTTPServer(
        ("127.0.0.1", 0), Handler, run_root=tmp_path, auth_token=None,
        max_concurrent_requests=1, connection_timeout_s=1.0,
    )
    try:
        with pytest.raises(RuntimeError, match="dispatch failed"):
            server.process_request(_FakeRequest(), ("127.0.0.1", 12345))
        assert server._request_slots.acquire(blocking=False) is True
    finally:
        server.server_close()
