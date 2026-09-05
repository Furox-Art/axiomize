#!/usr/bin/env python3
"""Cross-platform smoke test for the exact built wheel and installed CLI.

Runs on Ubuntu/Linux, Windows, and macOS. The script installs the wheel itself
so workflow shell/glob differences cannot hide platform-specific packaging or
entry-point failures.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path


class SmokeFailure(RuntimeError):
    pass


def _run(args: list[str], *, cwd: Path | None = None, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise SmokeFailure(
            f"command failed ({proc.returncode}): {' '.join(args)}\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    return proc


def _json(args: list[str], *, cwd: Path | None = None, timeout: int = 180) -> dict:
    proc = _run(args, cwd=cwd, timeout=timeout)
    try:
        value = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(f"expected JSON from {' '.join(args)}; got:\n{proc.stdout}") from exc
    if not isinstance(value, dict):
        raise SmokeFailure(f"expected JSON object from {' '.join(args)}")
    return value


def _exe(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise SmokeFailure(f"console entry point not found on PATH: {name}")
    return path


def _install_exact_wheel(wheel_dir: Path) -> Path:
    wheels = sorted(wheel_dir.glob("axiomize-*.whl"))
    if len(wheels) != 1:
        raise SmokeFailure(f"expected exactly one axiomize wheel in {wheel_dir}, found {len(wheels)}")
    wheel = wheels[0].resolve()
    _run([sys.executable, "-m", "pip", "install", "--force-reinstall", str(wheel)], timeout=600)
    _run([sys.executable, "-m", "pip", "check"], timeout=120)
    return wheel


def _model_request(path: Path) -> None:
    payload = {
        "model_ir": {
            "schema_version": "1.0",
            "name": "platform-decay",
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
            "assumptions": ["first-order decay"],
        },
        "t_span": [0.0, 1.0],
        "points": 16,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _smoke_cli(work: Path) -> None:
    axiomize = _exe("axiomize")
    secondary = (
        "axiomize-validate",
        "axiomize-fit",
        "axiomize-csv-check",
        "axiomize-benchmark",
        "axiomize-to-latex",
        "axiomize-index-reports",
        "axiomize-sweep",
    )
    for name in secondary:
        _exe(name)

    help_text = _run([axiomize, "--help"], cwd=work, timeout=60).stdout
    for command in ("model", "validate", "capabilities", "tools"):
        if command not in help_text:
            raise SmokeFailure(f"axiomize --help missing {command!r}")

    caps = _json([axiomize, "capabilities"], cwd=work, timeout=90)
    if "cli" not in caps.get("interfaces", []):
        raise SmokeFailure("capabilities does not report CLI interface")

    validation = _json(
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
            "60",
        ],
        cwd=work,
        timeout=120,
    )
    if validation.get("status") != "PASS":
        raise SmokeFailure(f"installed validation failed: {validation}")

    request = work / "model-request.json"
    _model_request(request)
    model = _json(
        [axiomize, "model", "--action", "simulate", "--input-json", str(request)],
        cwd=work,
        timeout=120,
    )
    if model.get("status") != "PASS" or model.get("family") != "ode":
        raise SmokeFailure(f"installed general model simulation failed: {model}")

    _run([_exe("axiomize-to-latex"), "--selftest"], cwd=work, timeout=120)


def _verify_installed_import(work: Path) -> None:
    code = (
        "import axiomize, importlib.metadata as m, pathlib; "
        "print(m.version('axiomize')); "
        "print(pathlib.Path(axiomize.__file__).resolve())"
    )
    proc = _run([sys.executable, "-c", code], cwd=work, timeout=60)
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        raise SmokeFailure("installed package import check produced no output")
    if lines[0] != metadata.version("axiomize"):
        raise SmokeFailure("runtime/importlib metadata version mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel-dir", default="dist")
    args = parser.parse_args()

    wheel = _install_exact_wheel(Path(args.wheel_dir))
    print(f"platform={platform.system()} {platform.release()}")
    print(f"machine={platform.machine()}")
    print(f"python={platform.python_version()}")
    print(f"wheel={wheel.name}")

    with tempfile.TemporaryDirectory(prefix="axiomize-platform-smoke-") as tmp:
        work = Path(tmp)
        _verify_installed_import(work)
        _smoke_cli(work)

    print(f"RESULT: PASS - exact wheel + CLI on {platform.system()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeFailure as exc:
        print(f"RESULT: FAIL - {exc}", file=sys.stderr)
        raise SystemExit(1)
