#!/usr/bin/env python3
"""End-to-end smoke test for every installed Axiomize CLI surface.

This script is intentionally executed after installing the built wheel.
It exercises real console entry points, representative numerical workflows,
the REST server, and the MCP stdio server. Any failure blocks release.
"""

from __future__ import annotations

import json
import math
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from importlib import metadata
from pathlib import Path
from typing import Any


CORE_COMMANDS = {
    "intake",
    "policy",
    "clean-data",
    "compare-runs",
    "solve",
    "fit",
    "validate",
    "tools",
    "capabilities",
    "reproduce",
    "benchmark",
    "serve",
    "mcp",
}

SECONDARY_ENTRYPOINTS = {
    "axiomize-validate",
    "axiomize-fit",
    "axiomize-csv-check",
    "axiomize-benchmark",
    "axiomize-to-latex",
    "axiomize-index-reports",
    "axiomize-sweep",
}


class SmokeFailure(RuntimeError):
    pass


def _exe(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise SmokeFailure(f"console entry point not installed: {name}")
    return path


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 180,
    expect: int = 0,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd is not None else None,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != expect:
        raise SmokeFailure(
            f"command failed ({proc.returncode}, expected {expect}): {' '.join(args)}\n"
            f"--- stdout ---\n{proc.stdout}\n"
            f"--- stderr ---\n{proc.stderr}"
        )
    return proc


def _json_stdout(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(
            f"expected JSON stdout, got:\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        ) from exc
    if not isinstance(payload, dict):
        raise SmokeFailure(f"expected JSON object, got {type(payload).__name__}")
    return payload


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def _write_logistic_csv(path: Path) -> None:
    r = 0.35
    k = 500.0
    y0 = 12.0
    rows = ["time,value"]
    for t in range(12):
        y = k / (1.0 + (k / y0 - 1.0) * math.exp(-r * t))
        rows.append(f"{t},{y:.12f}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _test_primary_cli(work: Path) -> None:
    axiomize = _exe("axiomize")

    help_text = _run([axiomize, "--help"], timeout=30).stdout
    for command in CORE_COMMANDS:
        _assert(command in help_text, f"axiomize --help is missing subcommand {command!r}")

    intake = _json_stdout(
        _run([axiomize, "intake", "A city wants to reduce traffic congestion"], timeout=30)
    )
    _assert(intake.get("status") in {"NEEDS_INPUT", "READY"}, "intake returned invalid status")

    policy = _json_stdout(_run([axiomize, "policy"], timeout=30))
    permissions = policy.get("policy", {}).get("permissions", {})
    _assert(
        permissions.get("allow_spawn_subtasks") is False,
        "policy must guard automatic subtask spawning by default",
    )
    _assert(
        permissions.get("allow_extra_paid_model_calls") is False,
        "policy must guard extra paid calls by default",
    )

    tools = _run([axiomize, "tools"], timeout=60).stdout.lower()
    for tool in ("scipy", "sympy", "cvxpy", "casadi", "statsmodels", "z3"):
        _assert(tool in tools, f"tool inventory output is missing {tool}")

    caps = _json_stdout(_run([axiomize, "capabilities"], timeout=60))
    _assert("interfaces" in caps, "capabilities missing interfaces")
    _assert("cli" in caps.get("interfaces", []), "capabilities does not report CLI")

    solved = _json_stdout(
        _run(
            [
                axiomize,
                "solve",
                "--beta",
                "0.3",
                "--gamma",
                "0.1",
                "--I0",
                "10",
                "--N",
                "10000",
                "--days",
                "120",
            ],
            timeout=60,
        )
    )
    _assert(solved.get("status") == "PASS", f"solve smoke failed: {solved}")

    validated = _json_stdout(
        _run(
            [
                axiomize,
                "validate",
                "--beta",
                "0.3",
                "--gamma",
                "0.1",
                "--I0",
                "10",
                "--N",
                "10000",
                "--days",
                "120",
            ],
            timeout=60,
        )
    )
    _assert(validated.get("status") == "PASS", f"validate smoke failed: {validated}")

    csv_path = work / "logistic.csv"
    _write_logistic_csv(csv_path)
    fitted = _json_stdout(_run([axiomize, "fit", "--data", str(csv_path)], timeout=90))
    params = fitted.get("params", {})
    _assert("r" in params and "K" in params, f"fit output missing logistic parameters: {fitted}")

    clean_input = work / "clean-input.json"
    clean_input.write_text(
        json.dumps({"t": [2, 1, 1, 3], "y": [20, 9, 11, 30]}),
        encoding="utf-8",
    )
    cleaned = _json_stdout(
        _run([axiomize, "clean-data", "--input-json", str(clean_input)], timeout=30)
    )
    _assert(cleaned.get("cleaned_t") == [1.0, 2.0, 3.0], f"clean-data failed: {cleaned}")
    _assert(bool(cleaned.get("audit")), "clean-data did not return an audit trail")

    from axiomize.runs.state import RunState

    before = work / "run-before"
    after = work / "run-after"
    RunState(
        problem_definition="release smoke",
        parameters={"alpha": 1.0},
        solver_settings={"rtol": 1e-6},
        results={"score": 1.0},
    ).save(before)
    RunState(
        problem_definition="release smoke",
        parameters={"alpha": 1.5},
        solver_settings={"rtol": 1e-7},
        results={"score": 1.2},
    ).save(after)

    reproduced = _json_stdout(_run([axiomize, "reproduce", str(before)], timeout=30))
    _assert(reproduced.get("results", {}).get("score") == 1.0, "reproduce returned wrong data")

    compared = _json_stdout(
        _run([axiomize, "compare-runs", str(before), str(after)], timeout=30)
    )
    _assert(compared.get("same_results") is False, "compare-runs missed changed results")
    _assert("parameters" in compared.get("differences", {}), "compare-runs missed parameter changes")

    benchmark = _json_stdout(_run([axiomize, "benchmark"], timeout=240))
    _assert(benchmark.get("status") == "PASS", "package-native benchmark failed")


def _test_secondary_entrypoints(work: Path) -> None:
    for name in SECONDARY_ENTRYPOINTS:
        _exe(name)

    _run(
        [
            _exe("axiomize-validate"),
            "--model",
            "sir",
            "--beta",
            "0.3",
            "--gamma",
            "0.1",
        ],
        timeout=90,
    )
    _run([_exe("axiomize-fit"), "--model", "logistic", "--selftest"], timeout=120)

    csv_path = work / "quality.csv"
    _write_logistic_csv(csv_path)
    _run(
        [
            _exe("axiomize-csv-check"),
            "--data",
            str(csv_path),
            "--time-col",
            "time",
            "--value-col",
            "value",
        ],
        timeout=60,
    )

    cases = _run([_exe("axiomize-benchmark"), "--case-list"], timeout=30).stdout
    _assert(bool(cases.strip()), "axiomize-benchmark --case-list returned no cases")

    _run([_exe("axiomize-to-latex"), "--selftest"], timeout=120)
    _run([_exe("axiomize-sweep"), "--job", "sweep"], timeout=120)

    reports_dir = work / "reports"
    reports_dir.mkdir()
    (reports_dir / "smoke.md").write_text(
        "# Model Report: Smoke\n\n"
        "**Date:** 2026-09-04\n\n"
        "**Rigor level:** medium\n\n"
        "**Model in one sentence:** Release smoke model.\n",
        encoding="utf-8",
    )
    _run([_exe("axiomize-index-reports")], cwd=work, timeout=30)
    _assert((reports_dir / "INDEX.md").is_file(), "axiomize-index-reports did not create INDEX.md")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _request_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 2.0,
) -> dict[str, Any]:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not isinstance(body, dict):
        raise SmokeFailure(f"REST endpoint returned non-object JSON: {body!r}")
    return body


def _test_rest_cli() -> None:
    axiomize = _exe("axiomize")
    port = _free_port()
    proc = subprocess.Popen(
        [axiomize, "serve", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}/v1"
        last_error: Exception | None = None
        for _ in range(50):
            if proc.poll() is not None:
                stderr = proc.stderr.read() if proc.stderr else ""
                raise SmokeFailure(f"REST server exited early ({proc.returncode}): {stderr}")
            try:
                caps = _request_json(f"{base}/capabilities")
                _assert("interfaces" in caps, "REST /capabilities missing interfaces")
                break
            except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
                last_error = exc
                time.sleep(0.1)
        else:
            raise SmokeFailure(f"REST server never became ready: {last_error!r}")

        intake = _request_json(
            f"{base}/intake",
            payload={"idea": "Reduce traffic congestion"},
        )
        _assert(intake.get("status") in {"NEEDS_INPUT", "READY"}, "REST /intake failed")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def _test_mcp_cli() -> None:
    axiomize = _exe("axiomize")
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "axiomize.intake",
                "arguments": {"idea": "Reduce traffic congestion"},
            },
        },
    ]
    payload = "".join(json.dumps(item) + "\n" for item in requests)
    proc = subprocess.run(
        [axiomize, "mcp"],
        input=payload,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        raise SmokeFailure(
            f"MCP process failed ({proc.returncode})\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    by_id = {item.get("id"): item for item in responses}
    _assert(1 in by_id and "result" in by_id[1], "MCP initialize failed")
    tools = by_id.get(2, {}).get("result", {}).get("tools", [])
    names = {tool.get("name") for tool in tools}
    _assert("axiomize.intake" in names, "MCP tools/list missing axiomize.intake")
    call = by_id.get(3, {})
    _assert("result" in call and not call.get("error"), f"MCP tools/call failed: {call}")


def main() -> int:
    installed = metadata.version("axiomize")
    print(f"Axiomize installed version: {installed}")
    print(f"Python: {sys.version.split()[0]}")
    with tempfile.TemporaryDirectory(prefix="axiomize-cli-smoke-") as tmp:
        work = Path(tmp)
        _test_primary_cli(work)
        print("PASS primary axiomize CLI")
        _test_secondary_entrypoints(work)
        print("PASS secondary console entry points")
        _test_rest_cli()
        print("PASS REST server CLI")
        _test_mcp_cli()
        print("PASS MCP stdio CLI")
    print("RESULT: PASS - full installed CLI contract")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeFailure as exc:
        print(f"RESULT: FAIL - {exc}", file=sys.stderr)
        raise SystemExit(1)
