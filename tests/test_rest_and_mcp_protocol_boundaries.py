"""UTF-8 and unambiguous framing and authentication at API boundaries."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
from email.message import Message
from io import BytesIO
from pathlib import Path

import pytest

from axiomize.server.rest_server import (
    Handler,
    RequestTooLarge,
    _read_json,
    start_server,
)
from axiomize.server.strict_json import loads


@pytest.mark.parametrize(
    "raw",
    [
        r'{"id":"\ud800"}',
        r'{"nested":{"message":"\udfff"}}',
        r'{"array":["\ud800"]}',
        '{"ok":1}'.encode("utf-16"),
        '{"ok":1}'.encode("utf-32"),
    ],
)
def test_wire_json_refuses_unpaired_surrogates_and_non_utf8_encodings(
    raw: str | bytes,
) -> None:
    with pytest.raises((UnicodeError, ValueError)):
        loads(raw)


def test_normal_multilingual_utf8_and_valid_surrogate_pair_work() -> None:
    assert loads(r'{"id":"\ud83d\ude00"}') == {"id": "😀"}
    assert loads('{"id":"Türkçe 日本語 😀"}'.encode())["id"] == "Türkçe 日本語 😀"


@pytest.mark.parametrize(
    "headers",
    [
        [("Content-Length", "2"), ("Content-Length", "200")],
        [("Content-Length", "2"), ("Content-Length", "2")],
        [("Content-Length", "2"), ("Transfer-Encoding", "chunked")],
        [("Transfer-Encoding", "chunked")],
    ],
)
def test_ambiguous_http_framing_refused_before_parsing(headers: list[tuple[str, str]]) -> None:
    values = Message()
    for name, value in headers:
        values.add_header(name, value)
    request = type("Request", (), {"headers": values, "rfile": BytesIO(b"{}")})()
    with pytest.raises(ValueError, match="framing"):
        _read_json(request)


@pytest.mark.parametrize("value", ["-1", "+2", "1,2", "2.0", "2junk"])
def test_invalid_http_request_lengths_are_rejected(value: str) -> None:
    headers = Message()
    headers.add_header("Content-Length", value)
    request = type("Request", (), {"headers": headers, "rfile": BytesIO(b"{}")})()
    with pytest.raises(ValueError):
        _read_json(request)


def test_extremely_long_content_length_fails_before_integer_parse() -> None:
    headers = Message()
    headers.add_header("Content-Length", "9" * 6000)
    request = type("Request", (), {"headers": headers, "rfile": BytesIO()})()
    with pytest.raises(RequestTooLarge):
        _read_json(request)


def test_valid_http_json_body_is_unaffected() -> None:
    headers = Message()
    body = b'{"message":"ok"}'
    headers.add_header("Content-Length", str(len(body)))
    request = type("Request", (), {"headers": headers, "rfile": BytesIO(body)})()
    assert _read_json(request) == {"message": "ok"}


@pytest.mark.parametrize(
    "auth_fields",
    [
        [("Authorization", "Bearer secret-token"), ("Authorization", "Bearer wrong")],
        [("Authorization", "Bearer wrong"), ("Authorization", "Bearer secret-token")],
        [("X-Axiomize-Token", "secret-token"), ("X-Axiomize-Token", "wrong")],
        [("Authorization", "Bearer secret-token"), ("X-Axiomize-Token", "secret-token")],
    ],
)
def test_duplicate_or_competing_authentication_rejected(
    auth_fields: list[tuple[str, str]],
) -> None:
    fields = Message()
    for key, value in auth_fields:
        fields.add_header(key, value)
    fake = type("AuthRequest", (), {})()
    fake.headers = fields
    fake._server = type("Server", (), {"auth_token": "secret-token"})()
    assert Handler._authorized(fake) is False


def test_single_authentication_header_remains_supported() -> None:
    for key, value in (
        ("Authorization", "Bearer secret-token"),
        ("X-Axiomize-Token", "secret-token"),
    ):
        fields = Message()
        fields.add_header(key, value)
        fake = type("AuthRequest", (), {})()
        fake.headers = fields
        fake._server = type("Server", (), {"auth_token": "secret-token"})()
        assert Handler._authorized(fake) is True


def test_live_rest_refuses_conflicting_framing(tmp_path: Path) -> None:
    server = start_server("127.0.0.1", 0, run_root=tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = b"{}"
        header = (
            b"POST /workflow-policy HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 2\r\nContent-Length: 99\r\n"
            b"Connection: close\r\n\r\n"
        )
        with socket.create_connection(("127.0.0.1", server.server_port), timeout=5) as sock:
            sock.settimeout(5)
            sock.sendall(header + body)
            received = sock.makefile("rb").read()
        assert received.split(b"\r\n", 1)[0].startswith(b"HTTP/1.1 400")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_mcp_stdio_recovers_after_unpaired_surrogate_id() -> None:
    script = "from axiomize.server.mcp_server import serve_stdio; serve_stdio()"
    source = (
        b'{"jsonrpc":"2.0","id":"\\ud800","method":"ping"}\n'
        b'{"jsonrpc":"2.0","id":9,"method":"ping"}\n'
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        input=source,
        capture_output=True,
        timeout=15,
    )
    assert proc.returncode == 0, proc.stderr
    replies = [json.loads(line) for line in proc.stdout.splitlines()]
    assert replies[0]["error"]["code"] == -32700
    assert replies[1] == {"jsonrpc": "2.0", "id": 9, "result": {}}
