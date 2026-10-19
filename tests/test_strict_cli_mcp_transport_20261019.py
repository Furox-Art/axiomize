"""Real JSON-RPC framing, CLI filesystem and failure-propagation contracts."""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from axiomize import cli
from axiomize.server import mcp_server


def test_dump_valid_json_stdout_and_disk(tmp_path, capsys):
    item = {"status": "PASS", "count": 4}
    assert cli._dump(item, None) == 0
    assert json.loads(capsys.readouterr().out) == item
    file = tmp_path / "output.json"
    assert cli._dump(item, str(file)) == 0
    assert json.loads(file.read_text()) == item
    assert "wrote " in capsys.readouterr().out


def test_cli_input_rejects_nonobject_invalid_json_and_oversize(tmp_path, monkeypatch):
    file = tmp_path / "request.json"
    assert cli._load_object(None) == {}
    file.write_text("[1, 2]")
    with pytest.raises(ValueError, match="JSON object"):
        cli._load_object(str(file))
    file.write_text("{bad JSON")
    with pytest.raises(json.JSONDecodeError):
        cli._load_object(str(file))
    file.write_text('{"x": 1}')
    monkeypatch.setattr(cli, "MAX_RUN_JSON_BYTES", 4)
    with pytest.raises(ValueError, match="hard JSON input limit"):
        cli._load_object(str(file))


def test_logistic_csv_missing_rows_and_columns_are_not_invented(tmp_path):
    file = tmp_path / "observed.csv"
    for data, message in (
        ("time,value\n", "at least two data rows"),
        ("time,value\n0,1\n", "at least two data rows"),
        ("time,value\n0\n1,2\n", "needs at least two columns"),
    ):
        file.write_text(data)
        with pytest.raises(ValueError, match=message):
            cli.cmd_fit(argparse.Namespace(data=str(file), json=None))


def test_logistic_csv_requires_hard_row_limit(tmp_path, monkeypatch):
    file = tmp_path / "observed.csv"
    file.write_text("time,value\n0,2\n1,4\n")
    monkeypatch.setattr(cli, "MAX_ARRAY_ITEMS", 1)
    with pytest.raises(ValueError, match="hard row limit"):
        cli.cmd_fit(argparse.Namespace(data=str(file), json=None))


def test_logistic_csv_forwards_recorded_measurements(tmp_path, capsys, monkeypatch):
    from axiomize.application import services

    recorded = []
    monkeypatch.setattr(
        services, "fit_logistic_service",
        lambda request: recorded.append(request) or {"status": "PASS"},
    )
    file = tmp_path / "observed.csv"
    file.write_text("time,value\n0,1\n\n1,3\n2,5\n")
    assert cli.cmd_fit(argparse.Namespace(data=str(file), json=None)) == 0
    assert recorded == [{"t": [0, 1, 2], "y": [1, 3, 5]}]
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"


def test_logistic_csv_refuses_oversize_without_parsing(tmp_path, monkeypatch):
    file = tmp_path / "observed.csv"
    file.write_text("time,value\n0,1\n")
    old = Path.stat

    def size_check(self, *args, **kwargs):
        value = old(self, *args, **kwargs)
        if self == file:
            return SimpleNamespace(st_size=65 * 1024 * 1024)
        return value

    monkeypatch.setattr(Path, "stat", size_check)
    with pytest.raises(ValueError, match="64 MiB"):
        cli.cmd_fit(argparse.Namespace(data=str(file), json=None))


def test_clean_data_cli_preserves_original_order_and_duplicate_choice(tmp_path, capsys):
    file = tmp_path / "data.json"
    file.write_text(json.dumps({"t": [1, 0, 1], "y": [2, 0, 4]}))
    args = argparse.Namespace(input_json=str(file), reject_nonfinite=True,
                              keep_order=True, duplicate_policy="first", json=None)
    assert cli.cmd_clean_data(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["cleaned_t"] == [1, 0]
    assert result["audit"][0]["policy"] == "first"


def test_cli_serve_always_closes_and_uses_explicit_auth(monkeypatch, capsys):
    from axiomize.server import rest_server

    events = []

    class Stub:
        server_address = ("127.0.0.1", 39391)
        generated_token = None

        def serve_forever(self):
            events.append("running")
            raise KeyboardInterrupt

        def server_close(self):
            events.append("closed")

    def factory(*args, **kwargs):
        events.append((args, kwargs))
        return Stub()

    monkeypatch.setattr(rest_server, "start_server", factory)
    monkeypatch.setenv("AXIOMIZE_TEST_TOKEN", "secret")
    args = argparse.Namespace(host="127.0.0.1", port=0, run_root=".",
                              allow_remote=False, auth_token=None,
                              auth_token_env="AXIOMIZE_TEST_TOKEN",
                              max_concurrent_requests=2)
    assert cli.cmd_serve(args) == 0
    assert events[0][1]["auth_token"] == "secret"
    assert events[1:] == ["running", "closed"]
    assert "39391" in capsys.readouterr().out


def test_cli_mcp_dispatch_forwards_run_root_without_running_server(monkeypatch):
    got = []
    monkeypatch.setattr(mcp_server, "serve_stdio", lambda *, run_root: got.append(run_root))
    assert cli.cmd_mcp(argparse.Namespace(run_root="/tmp/recorded-runs")) == 0
    assert got == ["/tmp/recorded-runs"]


def test_mcp_returns_precise_invalid_rpc_codes():
    assert mcp_server.handle_message(None)["error"]["code"] == -32600
    assert mcp_server.handle_message({"method": "unsupported"})["error"]["code"] == -32601
    for params in (None, {}, {"name": None}):
        response = mcp_server.handle_message({
            "id": 7, "method": "tools/call", "params": params,
        })
        assert response["id"] == 7
        assert response["error"]["code"] == -32602
    invalid = mcp_server.handle_message({
        "method": "tools/call",
        "params": {"name": "axiomize.clean_data", "arguments": []},
    })
    assert invalid["error"]["code"] == -32602


def test_mcp_initialization_ping_and_tool_list_have_real_schemas():
    init = mcp_server.handle_message({"id": 1, "method": "initialize"})
    assert init["result"]["capabilities"] == {"tools": {}}
    assert mcp_server.handle_message({"method": "ping"})["result"] == {}
    tools = mcp_server.handle_message({"method": "tools/list"})["result"]["tools"]
    assert any(tool["name"] == "axiomize.clean_data" for tool in tools)
    assert any(tool["name"] == "axiomize.model_simulate" for tool in tools)


def test_mcp_real_service_has_machine_readable_measured_output(tmp_path):
    result = mcp_server.handle_message({
        "method": "tools/call", "id": 2,
        "params": {"name": "axiomize.clean_data",
                   "arguments": {"t": [0, 1], "y": [3.0, 5.0]}},
    }, run_root=tmp_path)
    assert result["result"]["isError"] is False
    content = json.loads(result["result"]["content"][0]["text"])
    assert content["cleaned_y"] == [3, 5]
    assert content["material_change"] is False


def test_mcp_unknown_tool_and_bad_chart_dir_are_explicit_errors():
    unknown = mcp_server.handle_message({
        "method": "tools/call", "params": {"name": "not_a_real_tool", "arguments": {}},
    })
    assert unknown["error"]["code"] == -32601
    invalid = mcp_server.handle_message({
        "method": "tools/call",
        "params": {"name": "axiomize.model_visualize", "arguments": {"run_dir": None}},
    })
    names = {tool["name"] for tool in mcp_server.list_tools()}
    assert invalid["error"]["code"] == (-32602 if "axiomize.model_visualize" in names else -32601)


def test_mcp_stdio_recovers_after_invalid_bytes_and_blank_lines(monkeypatch):
    frames = b"\nnot-json\n\xff\n" + json.dumps({"method": "ping", "id": 2}).encode() + b"\n"
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(frames)))
    monkeypatch.setattr(sys, "stdout", output)
    mcp_server.serve_stdio()
    rows = [json.loads(row) for row in output.getvalue().splitlines()]
    assert [row["error"]["code"] for row in rows[:2]] == [-32700, -32700]
    assert rows[-1]["id"] == 2
    assert rows[-1]["result"] == {}


def test_mcp_oversized_frame_resynchronizes_with_next_request(monkeypatch):
    monkeypatch.setattr(mcp_server, "MAX_MCP_MESSAGE_BYTES", 32)
    frames = b"x" * 60 + b"\n" + b'{"method":"ping","id":8}' + b"\n"
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(frames)))
    monkeypatch.setattr(sys, "stdout", output)
    mcp_server.serve_stdio()
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    assert rows[0]["error"]["message"] == "MCP message too large"
    assert rows[1]["id"] == 8
