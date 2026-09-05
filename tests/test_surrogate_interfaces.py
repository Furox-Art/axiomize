from __future__ import annotations

import json

import numpy as np


def _payload() -> dict:
    x = np.linspace(-1.0, 1.0, 50)
    y = 2.0 + 3.0 * x + 0.5 * x**2
    return {
        "mode": "fit",
        "training_data": {"inputs": {"x": x.tolist()}, "outputs": {"y": y.tolist()}},
        "degree": 2,
        "seed": 9,
        "minimum_r2": 0.99999,
        "maximum_nrmse": 1e-5,
    }


def test_surrogate_cli_surface(tmp_path, capsys) -> None:
    from axiomize.cli import main

    request = tmp_path / "surrogate.json"
    request.write_text(json.dumps(_payload()), encoding="utf-8")
    rc = main(["model", "--action", "surrogate", "--input-json", str(request)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "PASS"
    assert out["validation_status"] == "PASS"
    assert out["qualified_for_acceleration"] is True


def test_surrogate_mcp_surface() -> None:
    from axiomize.server import mcp_server

    names = {item["name"] for item in mcp_server.list_tools()}
    assert "axiomize.model_surrogate" in names
    out = mcp_server._call_tool("axiomize.model_surrogate", _payload())
    assert out["status"] == "PASS"
    assert out["validation_status"] == "PASS"


def test_surrogate_rest_surface() -> None:
    import threading
    import urllib.request

    from axiomize.server.rest_server import start_server

    server = start_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/v1/model/surrogate",
            data=json.dumps(_payload()).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            out = json.loads(response.read().decode("utf-8"))
        assert out["status"] == "PASS"
        assert out["validation_status"] == "PASS"
    finally:
        server.shutdown()
        server.server_close()
