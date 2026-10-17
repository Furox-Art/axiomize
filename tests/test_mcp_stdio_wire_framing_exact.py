"""MCP stdio frame boundaries retain JSON-RPC errors and recover after oversized input."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest

from axiomize.server import mcp_server as mcp


def _execute(monkeypatch, frames, *, limit=None):
    stdin = SimpleNamespace(buffer=io.BytesIO(frames))
    stdout = io.StringIO()
    monkeypatch.setattr(mcp.sys, "stdin", stdin)
    monkeypatch.setattr(mcp.sys, "stdout", stdout)
    if limit is not None:
        monkeypatch.setattr(mcp, "MAX_MCP_MESSAGE_BYTES", limit)
    mcp.serve_stdio(run_root=".")
    return [json.loads(row) for row in stdout.getvalue().splitlines()]


def test_mcp_stream_multiple_json_rpc_requests_are_independent(monkeypatch):
    lines = b'{"jsonrpc":"2.0","id":1,"method":"ping"}\n{"jsonrpc":"2.0","id":2,"method":"initialize"}\n'
    results = _execute(monkeypatch, lines)
    assert [row["id"] for row in results] == [1, 2]
    assert results[0]["result"] == {}
    assert results[1]["result"]["serverInfo"]["name"] == "axiomize"


def test_blank_lines_are_not_unverified_scientific_messages(monkeypatch):
    assert _execute(monkeypatch, b"\n  \n") == []


@pytest.mark.parametrize(
    "invalid",
    [
        b'{"method":',
        b"\xff",
        b'{"a":NaN}',
        b'{"a":1,"a":2}',
    ],
)
def test_nonstandard_malformed_frames_cannot_be_accepted(monkeypatch, invalid):
    results = _execute(monkeypatch, invalid + b"\n")
    assert len(results) == 1
    assert results[0]["error"]["code"] == -32700


def test_mcp_message_length_ceiling_consumes_entire_corrupt_frame(monkeypatch):
    oversized = b"X" * 70 + b"\n"
    short = b'{"id":2,"method":"ping"}\n'
    results = _execute(monkeypatch, oversized + short, limit=35)
    assert len(results) == 2
    assert results[0]["error"]["code"] == -32600
    assert "too large" in results[0]["error"]["message"]
    assert results[1]["result"] == {}
    assert results[1]["id"] == 2


def test_mcp_stream_recovers_after_oversized_multiple_read_chunks(monkeypatch):
    oversized = b"A" * 101 + b"\n"
    valid = b'{"id":4,"method":"ping"}\n'
    results = _execute(monkeypatch, oversized + valid, limit=32)
    assert [row["error"]["code"] if "error" in row else row["id"] for row in results] == [-32600, 4]


def test_mcp_status_and_nonfinite_are_standard_json_not_invalid_numeric_claims(monkeypatch):
    monkeypatch.setattr(
        mcp,
        "_call_tool",
        lambda *a, **kw: {
            "status": "UNVERIFIED",
            "numeric_error": float("nan"),
        },
    )
    frame = (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "axiomize.solve", "arguments": {}},
            }
        ).encode()
        + b"\n"
    )
    rows = _execute(monkeypatch, frame)
    assert rows[0]["result"]["status"] == "UNVERIFIED"
    decoded = json.loads(rows[0]["result"]["content"][0]["text"])
    assert decoded == {"status": "UNVERIFIED", "numeric_error": "NaN"}


def test_mcp_empty_stream_returns_without_sending_a_response(monkeypatch):
    assert _execute(monkeypatch, b"") == []
