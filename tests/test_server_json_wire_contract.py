"""Reject ambiguous JSON at both exposed API transport boundaries."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from axiomize.server.rest_server import start_server
from axiomize.server.strict_json import loads


@pytest.mark.parametrize(
    "raw",
    [
        b'{"jsonrpc":"2.0","method":"ping","method":"tools/list"}',
        b'{"params":{"a":1,"a":2}}',
        b'{"value":NaN}',
        b'{"value":Infinity}',
        b'{"value":-Infinity}',
        b'{"value":1e9999}',
        b'{"nested":{"key":true,"key":false}}',
    ],
)
def test_ambiguous_json_must_fail_at_the_shared_decoder(raw: bytes) -> None:
    with pytest.raises(ValueError):
        loads(raw)


def test_legitimate_unicode_and_nested_json_still_parse() -> None:
    obj = {"text": "Türkçe 日本語", "nested": [{"n": 1.5, "ok": True}]}
    assert loads(json.dumps(obj, ensure_ascii=False).encode()) == obj


@pytest.mark.parametrize(
    "raw",
    [
        b'{"input":1,"input":2}',
        b'{"parameters":{"beta":0.1,"beta":0.9}}',
        b'{"value":NaN}',
        b'{"value":1e9999}',
    ],
)
def test_rest_rejects_ambiguous_json_before_service_execution(
    tmp_path: Path, raw: bytes
) -> None:
    server = start_server("127.0.0.1", 0, run_root=tmp_path)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/workflow-policy",
            data=raw,
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as failure:
            urllib.request.urlopen(request, timeout=4)
        assert failure.value.code == 400
        payload = json.loads(failure.value.read())
        assert "invalid JSON request body" in payload["error"]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def test_mcp_stdio_recovers_after_invalid_frames() -> None:
    frames = [
        '{"jsonrpc":"2.0","id":1,"method":"ping","method":"tools/list"}',
        '{"jsonrpc":"2.0","id":2,"method":"ping","params":{"n":NaN}}',
        '{"jsonrpc":"2.0","id":3,"method":"ping","params":{"n":1e9999}}',
        '{"jsonrpc":"2.0","id":4,"method":"ping"}',
    ]
    code = "from axiomize.server.mcp_server import serve_stdio; serve_stdio()"
    run = subprocess.run(
        [sys.executable, "-c", code],
        input="\n".join(frames) + "\n",
        text=True, capture_output=True, timeout=10,
    )
    assert run.returncode == 0, run.stderr
    responses = [json.loads(line) for line in run.stdout.splitlines()]
    assert len(responses) == 4
    assert [response["error"]["code"] for response in responses[:3]] == [-32700] * 3
    assert responses[3]["result"] == {}
