"""Exercise REST route selection and response framing without opening sockets."""

from __future__ import annotations

import json
from email.message import Message
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from axiomize.server.rest_server import (
    Handler,
    _has_model_ir,
    _is_loopback_host,
    _read_json,
    _send,
    _strip_api_prefix,
    start_server,
)


def fake_handler(*, path="/tools", body=b"", token=None, auth=None, length=None):
    handler = Handler.__new__(Handler)
    headers = Message()
    if length is not None or body:
        headers.add_header("Content-Length", str(len(body) if length is None else length))
    if auth is not None:
        headers.add_header("Authorization", auth)
    handler.headers = headers
    handler.path = path
    handler.rfile = BytesIO(body)
    handler.wfile = BytesIO()
    handler.server = SimpleNamespace(auth_token=token, run_root=Path("/tmp"))
    handler.sent_code = None
    handler.sent_headers = []
    handler.send_response = lambda code: setattr(handler, "sent_code", code)
    handler.send_header = lambda k, v: handler.sent_headers.append((k, v))
    handler.end_headers = lambda: None
    return handler


@pytest.mark.parametrize(
    ("host", "loopback"),
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("localhost", True),
        ("  LOCALHOST ", True),
        ("0.0.0.0", False),
        ("192.168.0.1", False),
        ("example.com", False),
        ("invalid hostname", False),
    ],
)
def test_rest_loopback_auth_boundary_uses_ip_addresses(host, loopback):
    assert _is_loopback_host(host) is loopback


@pytest.mark.parametrize(
    ("route", "expected"),
    [
        ("/v1/tools", "/tools"),
        ("/v1/solve", "/solve"),
        ("/tools", "/tools"),
        ("/v1/", "/"),
        ("/v11/solve", "/v11/solve"),
    ],
)
def test_version_prefix_is_not_overbroad(route, expected):
    assert _strip_api_prefix(route) == expected


@pytest.mark.parametrize(
    "payload",
    [
        {"model_ir": {}},
        {"model": {}},
        {"model_ir": {"family": "ode"}},
    ],
)
def test_model_ir_discriminator_is_structural(payload):
    assert _has_model_ir(payload) is True


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"model_ir": "fake"},
        {"model": None},
        {"model_ir": []},
    ],
)
def test_nonstruc_payload_never_claims_model_ir(payload):
    assert _has_model_ir(payload) is False


@pytest.mark.parametrize(
    ("raw", "expected", "status"),
    [
        (b"", {}, None),
        (b"{}", {}, None),
        (b'{"a":3}', {"a": 3}, None),
    ],
)
def test_json_body_unambiguous_framing(raw, expected, status):
    handler = fake_handler(body=raw, length=len(raw) if raw else None)
    assert _read_json(handler) == expected


@pytest.mark.parametrize(
    ("body", "length", "error"),
    [
        (b"{}", 3, "ended before Content-Length"),
        (b"[1]", 3, "must be a JSON object"),
        (b'{"a":NaN}', 9, "invalid JSON"),
        (b'{"a":1,"a":2}', 13, "invalid JSON"),
    ],
)
def test_json_body_rejects_truncated_and_semantically_unsafe_input(body, length, error):
    handler = fake_handler(body=body, length=length)
    with pytest.raises(ValueError, match=error):
        _read_json(handler)


def test_json_response_is_utf8_noncacheable_and_length_exact():
    handler = fake_handler()
    _send(handler, 201, {"message": "Türkçe", "count": 2})
    decoded = json.loads(handler.wfile.getvalue())
    assert decoded == {"message": "Türkçe", "count": 2}
    assert handler.sent_code == 201
    headers = dict(handler.sent_headers)
    assert headers["Content-Length"] == str(len(handler.wfile.getvalue()))
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Connection"] == "close"


@pytest.mark.parametrize(
    "payload",
    [
        {"n": float("nan")},
        {"n": float("inf")},
    ],
)
def test_server_cannot_emit_nonfinite_json_success(payload):
    with pytest.raises(ValueError, match="Out of range float"):
        _send(fake_handler(), 200, payload)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/tools", "tools_service"),
        ("/capabilities", "capabilities_service"),
        ("/workflow-policy", "workflow_policy_service"),
    ],
)
def test_get_routes_require_no_scientific_execution(path, expected, monkeypatch):
    from axiomize.application import services

    monkeypatch.setattr(services, expected, lambda *args, **kwargs: {"handler": expected})
    handler = fake_handler(path=path)
    Handler.do_GET(handler)
    assert handler.sent_code == 200
    assert json.loads(handler.wfile.getvalue()) == {"handler": expected}


def test_get_missing_run_does_not_leak_filesystem(monkeypatch):
    handler = fake_handler(path="/v1/runs/../../secrets")
    handler._load_run = lambda key: (_ for _ in ()).throw(ValueError("secret path detail"))
    Handler.do_GET(handler)
    assert handler.sent_code == 404
    assert json.loads(handler.wfile.getvalue()) == {"error": "run not found or failed integrity checks"}


def test_get_existing_run_returns_hash_and_stored_result():
    handler = fake_handler(path="/runs/run-01")
    handler._load_run = lambda key: SimpleNamespace(input_hash=lambda: "sha256", results={"ok": True})
    Handler.do_GET(handler)
    assert handler.sent_code == 200
    assert json.loads(handler.wfile.getvalue()) == {"input_hash": "sha256", "results": {"ok": True}}


@pytest.mark.parametrize("path", ["/missing", "/v1/missing", "/runs", "/v1/"])
def test_unknown_get_path_is_404(path):
    handler = fake_handler(path=path)
    Handler.do_GET(handler)
    assert handler.sent_code == 404
    assert json.loads(handler.wfile.getvalue()) == {"error": "unknown route"}


def test_token_auth_rejects_missing_and_wrong_token_without_execution(monkeypatch):
    for auth in (None, "Bearer invalid"):
        handler = fake_handler(path="/tools", token="secret-token-123456", auth=auth)
        Handler.do_GET(handler)
        assert handler.sent_code == 401
        assert handler.wfile.getvalue() == b'{"error": "unauthorized"}'


@pytest.mark.parametrize(
    ("path", "module", "method"),
    [
        ("/model", "general_services", "model_plan_service"),
        ("/model/compare", "general_services", "model_compare_service"),
        ("/model/repair", "general_services", "model_repair_service"),
        ("/model/export", "general_services", "model_export_service"),
        ("/model/stability", "general_services", "model_stability_service"),
        ("/model/validity-scan", "general_services", "model_validity_service"),
        ("/model/discover", "general_services", "model_discovery_service"),
        ("/model/experiment-design", "general_services", "experiment_design_service"),
        ("/model/numerical-verify", "advanced_services", "model_numerical_verification_service"),
        ("/model/uncertainty", "advanced_services", "model_uncertainty_service"),
        ("/model/bifurcation", "advanced_services", "model_bifurcation_service"),
        ("/model/stop-check", "advanced_services", "model_stopping_service"),
        ("/model/surrogate", "surrogate_services", "model_surrogate_service"),
        ("/intake", "services", "intake_service"),
        ("/clean-data", "services", "clean_data_service"),
        ("/falsify", "services", "falsify_service"),
        ("/compare", "services", "compare_service"),
        ("/sensitivity", "services", "sensitivity_service"),
        ("/uncertainty", "services", "uncertainty_service"),
    ],
)
def test_post_route_dispatch_is_exact_and_gates_backend(path, module, method, monkeypatch):
    import importlib

    backend = importlib.import_module("axiomize.application." + module)
    monkeypatch.setattr(backend, method, lambda payload: {"dispatched": method, "payload": payload})
    body = b'{"test":1}'
    handler = fake_handler(path="/v1" + path, body=body)
    Handler.do_POST(handler)
    assert handler.sent_code == 200
    assert json.loads(handler.wfile.getvalue()) == {"dispatched": method, "payload": {"test": 1}}


@pytest.mark.parametrize(
    ("path", "backend", "method"),
    [
        ("/solve", "services", "solve_sir_service"),
        ("/fit", "services", "fit_logistic_service"),
        ("/validate", "services", "validate_sir_service"),
    ],
)
def test_legacy_science_routes_are_never_misidentified_as_general_ir(path, backend, method, monkeypatch):
    from axiomize.application import services

    monkeypatch.setattr(services, method, lambda payload: {"legacy": method})
    handler = fake_handler(path=path, body=b'{"old":true}')
    Handler.do_POST(handler)
    assert handler.sent_code == 200
    assert json.loads(handler.wfile.getvalue()) == {"legacy": method}


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/solve", "model_simulate_service"),
        ("/fit", "model_fit_service"),
        ("/validate", "model_validate_service"),
    ],
)
def test_model_ir_routes_never_fallback_to_legacy_engine(path, method, monkeypatch):
    from axiomize.application import general_services

    monkeypatch.setattr(general_services, method, lambda payload: {"ir": method})
    handler = fake_handler(path=path, body=b'{"model_ir":{}}')
    Handler.do_POST(handler)
    assert handler.sent_code == 200
    assert json.loads(handler.wfile.getvalue()) == {"ir": method}


def test_invalid_post_body_returns_bad_request_not_success():
    handler = fake_handler(path="/model", body=b'["not object"]')
    Handler.do_POST(handler)
    assert handler.sent_code == 400


def test_request_too_large_returns_413_and_never_executes_backend():
    handler = fake_handler(path="/model", body=b"{}", length=99999999999999999999)
    Handler.do_POST(handler)
    assert handler.sent_code == 413


def test_post_backend_failure_does_not_expose_internal_exception(monkeypatch):
    from axiomize.application import general_services

    def broken(_payload):
        raise RuntimeError("secret backend traceback")

    monkeypatch.setattr(general_services, "model_plan_service", broken)
    handler = fake_handler(path="/model", body=b"{}")
    Handler.do_POST(handler)
    assert handler.sent_code == 500
    assert json.loads(handler.wfile.getvalue()) == {"error": "internal server error"}


def test_post_unauthorized_does_not_read_or_evaluate_payload():
    handler = fake_handler(path="/model", body=b'{"unsafe":NaN}', token="secret-token-123456")
    Handler.do_POST(handler)
    assert handler.sent_code == 401


def test_remote_bind_without_approval_or_strong_token_is_rejected(tmp_path):
    for kwargs in (
        {"host": "0.0.0.0"},
        {"host": "0.0.0.0", "allow_remote": True},
        {"host": "0.0.0.0", "allow_remote": True, "auth_token": "short"},
    ):
        with pytest.raises(ValueError, match="non-loopback|auth token"):
            start_server(port=0, run_root=tmp_path, **kwargs)
