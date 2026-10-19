"""Actual localhost HTTP contracts: authorization, parsing and scientific routing."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from axiomize.server.rest_server import MAX_JSON_BYTES, start_server


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    root = tmp_path_factory.mktemp("http-scientific-claims")
    token = "this-is-a-unique-operator-auth-token"
    server = start_server(
        "127.0.0.1", 0, run_root=root,
        auth_token=token, connection_timeout_s=5,
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", token
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=10)


def request(server, route, payload=None, *, method="GET", token=True, raw=None, headers=None):
    url, credential = server
    request_headers = {"Accept": "application/json"}
    if token:
        request_headers["Authorization"] = f"Bearer {credential}"
    if headers:
        request_headers.update(headers)
    if raw is not None:
        data = raw
    elif payload is not None:
        data = json.dumps(payload, allow_nan=False).encode("utf-8")
    else:
        data = None
    if method == "POST" and data is None:
        data = b""
    if data is not None:
        request_headers.setdefault("Content-Type", "application/json")
    outgoing = urllib.request.Request(
        url + route, data=data, headers=request_headers, method=method,
    )
    try:
        response = urllib.request.urlopen(outgoing, timeout=5)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        status = response.status
        content = response.read()
        result = json.loads(content) if content else {}
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("Cache-Control") == "no-store"
    return status, result


@pytest.mark.parametrize("path", ["/tools", "/capabilities", "/workflow-policy",
                                  "/v1/tools", "/v1/capabilities"])
def test_real_server_exposes_only_known_read_endpoints(live_server, path):
    status, body = request(live_server, path)
    assert status == 200
    assert isinstance(body, dict)


def test_unknown_routes_and_nonexistent_run_have_correct_typed_status(live_server):
    assert request(live_server, "/not-a-route")[0] == 404
    assert request(live_server, "/runs/no-such-run")[0] == 404
    assert request(live_server, "/v1/runs/no-such-run")[0] == 404


@pytest.mark.parametrize("path", ["/intake", "/workflow-policy", "/model",
                                  "/model/compare", "/model/repair", "/model/export",
                                  "/model/stability", "/model/validity-scan",
                                  "/model/discover", "/model/experiment-design",
                                  "/model/numerical-verify", "/model/surrogate",
                                  "/model/uncertainty", "/model/bifurcation",
                                  "/model/stop-check", "/cross-validate",
                                  "/falsify", "/compare", "/sensitivity", "/uncertainty",
                                  "/fit", "/validate", "/solve", "/simulate"])
def test_real_post_routes_refuse_invalid_models_without_http_500(live_server, path):
    status, body = request(live_server, path, payload={}, method="POST")
    assert status in {200, 400, 404, 422}, (path, status, body)
    assert isinstance(body, dict)


def test_authentication_is_required_for_scientific_mutation(live_server):
    status, body = request(live_server, "/model", {}, method="POST", token=False)
    assert status == 401
    assert "error" in body


@pytest.mark.parametrize("path", ["/model", "/v1/model"])
def test_malformed_json_fails_as_bad_request(live_server, path):
    status, body = request(live_server, path, method="POST", raw=b"{bad_json",
                           headers={"Content-Type": "application/json"})
    assert status == 400
    assert "invalid JSON" in body["error"]


def test_oversized_body_is_refused_before_any_request_processing(live_server):
    status, body = request(live_server, "/intake", method="POST",
                           raw=b"{}", headers={"Content-Length": str(MAX_JSON_BYTES + 1)})
    assert status == 413
    assert "hard limit" in body["error"]


def test_real_path_traversal_never_escapes_run_root(live_server):
    status, body = request(live_server, "/compare-runs", method="POST",
                           payload={"before_dir": "../outside", "after_dir": "../outside"})
    assert status in {400, 404}, body
    assert "error" in body


def test_unknown_post_is_explicit_not_found(live_server):
    status, body = request(live_server, "/not-a-route", method="POST", payload={})
    assert status == 404
    assert body["error"] == "unknown route"
