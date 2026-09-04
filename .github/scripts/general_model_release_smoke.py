#!/usr/bin/env python3
"""Installed-wheel smoke gate for the general Model IR engine.

This is intentionally separate from unit tests: it exercises the real installed
``axiomize`` console entry point plus REST and MCP adapters after the exact wheel
artifact has been installed. Any regression here must block CI and release.
"""

from __future__ import annotations

import json
import math
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any


class SmokeFailure(RuntimeError):
    pass


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def _exe() -> str:
    path = shutil.which("axiomize")
    if not path:
        raise SmokeFailure("installed axiomize console entry point not found")
    return path


def _run(args: list[str], *, timeout: int = 60) -> dict[str, Any]:
    proc = subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        raise SmokeFailure(
            f"command failed ({proc.returncode}): {' '.join(args)}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(f"expected JSON stdout, got:\n{proc.stdout}\nstderr:\n{proc.stderr}") from exc
    if not isinstance(payload, dict):
        raise SmokeFailure("expected JSON object")
    return payload


def _model() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "name": "release-decay",
        "domain": "physics",
        "family": "ode",
        "independent_variable": "t",
        "independent_unit": "day",
        "variables": [
            {"name": "x", "unit": "dimensionless", "initial": 1.0, "bounds": [0.0, None]},
        ],
        "parameters": [
            {"name": "k", "unit": "1/day", "value": 0.5, "bounds": [0.0, 2.0]},
        ],
        "equations": [
            {"target": "x", "expression": "-k*x", "kind": "derivative"},
        ],
        "constraints": [
            {
                "name": "nonnegative_state",
                "expression": "x",
                "relation": "ge",
                "threshold": 0.0,
                "scientific_basis": "nonnegative admissible state",
            },
        ],
        "assumptions": ["first-order decay"],
    }


def _test_cli(work: Path) -> None:
    axiomize = _exe()
    help_text = subprocess.run([axiomize, "--help"], text=True, capture_output=True, timeout=30, check=True).stdout
    _assert("model" in help_text, "installed CLI help is missing the general model command")

    request = work / "model-request.json"
    request.write_text(json.dumps({
        "model_ir": _model(),
        "t_span": [0.0, 2.0],
        "points": 40,
    }), encoding="utf-8")

    validated = _run([axiomize, "model", "--action", "validate", "--input-json", str(request)])
    _assert(validated.get("status") == "PASS", f"general validation failed: {validated}")
    eq_checks = validated.get("validation", {}).get("equation_dimension_checks", [])
    _assert(eq_checks and eq_checks[0].get("status") == "PASS", "equation dimensional check did not pass")

    simulated = _run([axiomize, "model", "--action", "simulate", "--input-json", str(request)])
    _assert(simulated.get("status") == "PASS", f"general simulation failed: {simulated}")
    final = float(simulated["states"]["x"][-1])
    _assert(abs(final - math.exp(-1.0)) < 5e-5, f"unexpected ODE result: {final}")
    _assert(simulated.get("solver", {}).get("backend") == "scipy", "generic ODE did not use SciPy backend")

    export_request = work / "export-request.json"
    export_request.write_text(json.dumps({"model_ir": _model(), "format": "json"}), encoding="utf-8")
    exported = _run([axiomize, "model", "--action", "export", "--input-json", str(export_request)])
    _assert(exported.get("format") == "json", "general model JSON export failed")
    decoded = json.loads(exported["content"])
    _assert(decoded.get("schema_version") == "1.0", "export lost Model IR schema version")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not isinstance(body, dict):
        raise SmokeFailure("REST returned non-object JSON")
    return body


def _test_rest() -> None:
    axiomize = _exe()
    port = _free_port()
    proc = subprocess.Popen(
        [axiomize, "serve", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        url = f"http://127.0.0.1:{port}/v1/simulate"
        last: Exception | None = None
        for _ in range(50):
            if proc.poll() is not None:
                stderr = proc.stderr.read() if proc.stderr else ""
                raise SmokeFailure(f"REST server exited early: {stderr}")
            try:
                result = _post(url, {"model_ir": _model(), "t_span": [0.0, 1.0], "points": 20})
                break
            except Exception as exc:
                last = exc
                time.sleep(0.1)
        else:
            raise SmokeFailure(f"REST general-model endpoint never became ready: {last!r}")
        _assert(result.get("status") == "PASS" and result.get("family") == "ode", f"REST model failed: {result}")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def _test_mcp() -> None:
    axiomize = _exe()
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "axiomize.model_simulate",
                "arguments": {"model_ir": _model(), "t_span": [0.0, 1.0], "points": 20},
            },
        },
    ]
    proc = subprocess.run(
        [axiomize, "mcp"],
        input="".join(json.dumps(item) + "\n" for item in requests),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        raise SmokeFailure(f"MCP process failed: {proc.stderr}")
    responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    by_id = {item.get("id"): item for item in responses}
    tools = by_id.get(2, {}).get("result", {}).get("tools", [])
    names = {tool.get("name") for tool in tools}
    _assert("axiomize.model_simulate" in names, "MCP tools/list missing general model simulator")
    call = by_id.get(3, {})
    _assert("result" in call and "error" not in call, f"MCP model call failed: {call}")
    text = call["result"]["content"][0]["text"]
    result = json.loads(text)
    _assert(result.get("status") == "PASS" and result.get("family") == "ode", f"MCP general model failed: {result}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="axiomize-general-model-smoke-") as tmp:
        _test_cli(Path(tmp))
        print("PASS installed general-model CLI")
        _test_rest()
        print("PASS installed general-model REST")
        _test_mcp()
        print("PASS installed general-model MCP")
    print("RESULT: PASS - installed general Model IR contract")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeFailure as exc:
        print(f"RESULT: FAIL - {exc}", file=sys.stderr)
        raise SystemExit(1)
