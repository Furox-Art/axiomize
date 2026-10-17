"""REST connection limits, trusted run access, and framing error status codes."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace

import pytest

from axiomize.server import rest_server as rest
from tests.test_rest_route_contracts_exact import fake_handler


@pytest.mark.parametrize(
    ("bad", "pattern"),
    [
        ("", "non-empty"),
        ("0.0.0.0", "non-loopback"),
    ],
)
def test_rest_start_refuses_unapproved_listeners(bad, pattern, tmp_path):
    with pytest.raises(ValueError, match=pattern):
        rest.start_server(host=bad, run_root=tmp_path)


@pytest.mark.parametrize(
    ("kwargs", "pattern"),
    [
        ({"port": -1}, "port must be"),
        ({"port": 65536}, "port must be"),
        ({"max_concurrent_requests": 0}, "max_concurrent_requests"),
        ({"max_concurrent_requests": 257}, "max_concurrent_requests"),
        ({"connection_timeout_s": 0.0}, "connection_timeout_s"),
        ({"connection_timeout_s": 301.0}, "connection_timeout_s"),
        ({"connection_timeout_s": "not-a-time"}, "numeric"),
        ({"connection_timeout_s": float("nan")}, "between 1 and 300"),
    ],
)
def test_rest_server_concurrency_and_io_budget_hard_limits(kwargs, pattern, tmp_path):
    with pytest.raises(ValueError, match=pattern):
        rest.start_server(run_root=tmp_path, **kwargs)


def test_rest_server_uses_explicit_confined_root_and_auth(monkeypatch, tmp_path):
    captured = []

    def fake_class(address, handler, **kwargs):
        captured.append((address, handler, kwargs))
        return SimpleNamespace(server_address=address)

    monkeypatch.setattr(rest, "BoundedThreadingHTTPServer", fake_class)
    server = rest.start_server(
        host="127.0.0.1", port=5000, run_root=tmp_path, auth_token="secret", max_concurrent_requests=2
    )
    assert server.server_address == ("127.0.0.1", 5000)
    assert captured[0][1] is rest.Handler
    assert captured[0][2]["auth_token"] == "secret"
    assert captured[0][2]["run_root"] == tmp_path.resolve()


@pytest.mark.parametrize(
    "fields",
    [
        {"Content-Length": ["1", "1"]},
        {"Transfer-Encoding": ["chunked"]},
        {"Content-Length": ["-1"]},
        {"Content-Length": ["3.5"]},
        {"Content-Length": ["noninteger"]},
    ],
)
def test_http_request_framing_rejects_smuggling_ambiguity(fields):
    handler = fake_handler(body=b"{}")
    for field, values in fields.items():
        for value in values:
            handler.headers.add_header(field, value)
    with pytest.raises(ValueError, match="framing|Content-Length"):
        rest._read_json(handler)


def test_content_length_zero_yields_empty_request_not_read():
    handler = fake_handler(body=b"anything", length=0)
    assert rest._read_json(handler) == {}
    assert handler.rfile.tell() == 0


def test_reproduce_get_and_post_access_only_prevalidated_runs():
    for method in (rest.Handler.do_GET, rest.Handler.do_POST):
        handler = fake_handler(
            path="/v1/runs/record-01/reproduce" if method == rest.Handler.do_POST else "/v1/runs/record-01"
        )
        handler._load_run = lambda key: SimpleNamespace(input_hash=lambda: "digest", results={"status": "UNVERIFIED"})
        method(handler)
        assert handler.sent_code == 200
        assert json.loads(handler.wfile.getvalue()) == {"input_hash": "digest", "results": {"status": "UNVERIFIED"}}


@pytest.mark.parametrize(
    "exception",
    [
        ValueError("invalid run identifier"),
        OSError("missing run"),
    ],
)
def test_post_reproduce_missing_or_tampered_run_is_404(exception):
    handler = fake_handler(path="/runs/missing/reproduce")

    def load(_key):
        raise exception

    handler._load_run = load
    rest.Handler.do_POST(handler)
    assert handler.sent_code == 404
    assert json.loads(handler.wfile.getvalue()) == {"error": "run not found or failed integrity checks"}


def test_rest_cross_validate_keeps_engine_cross_validation_exact(monkeypatch):
    from axiomize.application import services

    monkeypatch.setattr(services, "solve_sir_service", lambda _p: {"cross_validation": {"status": "UNVERIFIED"}})
    handler = fake_handler(path="/cross-validate")
    rest.Handler.do_POST(handler)
    assert handler.sent_code == 200
    assert json.loads(handler.wfile.getvalue()) == {"status": "UNVERIFIED"}


def test_rest_unknown_post_route_reports_404_not_2xx():
    handler = fake_handler(path="/v1/nothing")
    rest.Handler.do_POST(handler)
    assert handler.sent_code == 404


@pytest.mark.parametrize("auth", ["Bearer correct-token", "correct-token"])
def test_authenticated_remote_requests_require_correct_header(auth):
    handler = fake_handler(path="/v1/tools", token="correct-token", auth=auth)
    if auth.startswith("Bearer "):
        assert handler._authorized() is True
    else:
        assert handler._authorized() is False


def test_token_header_is_still_supported_for_external_clients():
    handler = fake_handler(path="/tools", token="secret-token")
    handler.headers.add_header("X-Axiomize-Token", "secret-token")
    assert handler._authorized() is True


def test_duplicate_auth_channels_are_rejected():
    handler = fake_handler(path="/tools", token="secret-token", auth="Bearer secret-token")
    handler.headers.add_header("X-Axiomize-Token", "secret-token")
    assert handler._authorized() is False


def test_bounded_server_busy_queue_returns_503_without_running_request(monkeypatch):
    from http.server import ThreadingHTTPServer

    listener = rest.BoundedThreadingHTTPServer.__new__(rest.BoundedThreadingHTTPServer)
    listener._request_slots = threading.BoundedSemaphore(1)
    assert listener._request_slots.acquire(blocking=False)
    sent = []
    request = SimpleNamespace(sendall=lambda data: sent.append(data))
    closed = []
    listener.shutdown_request = lambda _req: closed.append(True)
    monkeypatch.setattr(ThreadingHTTPServer, "process_request", lambda *args: pytest.fail("queue limit bypassed"))
    listener.process_request(request, ("127.0.0.1", 10001))
    assert closed == [True]
    assert b"503 Service Unavailable" in sent[0]
    listener._request_slots.release()


def test_bounded_server_releases_slot_after_processing_error(monkeypatch):
    from http.server import ThreadingHTTPServer

    listener = rest.BoundedThreadingHTTPServer.__new__(rest.BoundedThreadingHTTPServer)
    listener._request_slots = threading.BoundedSemaphore(1)

    def broken(*args):
        raise RuntimeError("simulated connection error")

    monkeypatch.setattr(ThreadingHTTPServer, "process_request", broken)
    with pytest.raises(RuntimeError, match="simulated connection error"):
        listener.process_request(object(), ("127.0.0.1", 1))
    assert listener._request_slots.acquire(blocking=False)
    listener._request_slots.release()
