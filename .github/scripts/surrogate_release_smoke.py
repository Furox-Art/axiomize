#!/usr/bin/env python3
"""Exact-installed-wheel smoke contract for validated surrogate modeling."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np


def run(payload: dict, *, approve_heavy: bool = False, expect_rc: int = 0) -> dict:
    with tempfile.TemporaryDirectory() as td:
        request = Path(td) / "request.json"
        request.write_text(json.dumps(payload), encoding="utf-8")
        cmd = ["axiomize", "model", "--action", "surrogate", "--input-json", str(request)]
        if approve_heavy:
            cmd.append("--approve-heavy")
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if proc.returncode != expect_rc:
            raise RuntimeError(
                f"surrogate CLI expected rc={expect_rc}, got {proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
            )
        return json.loads(proc.stdout)


def source_model() -> dict:
    return {
        "schema_version": "1.0",
        "name": "release-surrogate-decay",
        "domain": "physics",
        "family": "ode",
        "independent_variable": "t",
        "independent_unit": "day",
        "variables": [{"name": "x", "unit": "dimensionless", "initial": 1.0}],
        "parameters": [{"name": "k", "unit": "1/day", "value": 0.3, "bounds": [0.05, 0.8]}],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    }


def main() -> int:
    x = np.linspace(-1.0, 1.0, 50)
    y = 2.0 + 3.0 * x + 0.5 * x**2
    fit = run({
        "mode": "fit",
        "training_data": {"inputs": {"x": x.tolist()}, "outputs": {"y": y.tolist()}},
        "degree": 2,
        "minimum_r2": 0.99999,
        "maximum_nrmse": 1e-5,
        "seed": 5,
    })
    assert fit["status"] == "PASS" and fit["validation_status"] == "PASS"
    artifact = fit["surrogate"]

    evaluated = run({"mode": "evaluate", "surrogate": artifact, "inputs": {"x": 0.25}})
    assert evaluated["status"] == "PASS"
    assert abs(evaluated["predictions"]["y"] - (2.0 + 3.0 * 0.25 + 0.5 * 0.25**2)) < 1e-8

    blocked = run(
        {"mode": "evaluate", "surrogate": artifact, "inputs": {"x": 10.0}},
        expect_rc=1,
    )
    assert blocked["status"] == "OUT_OF_DOMAIN"

    request = {
        "mode": "generate",
        "model_ir": source_model(),
        "parameter_ranges": {"k": [0.1, 0.6]},
        "output_specs": [{"name": "x_final", "state": "x", "metric": "final"}],
        "samples": 24,
        "points": 25,
        "degree": 3,
        "t_span": [0.0, 2.0],
        "seed": 4,
        "minimum_r2": 0.99,
        "maximum_nrmse": 0.05,
    }
    gated = run(request)
    assert gated["status"] == "APPROVAL_REQUIRED"
    assert gated["cost"]["requires_user_approval"] is True

    generated = run(request, approve_heavy=True)
    assert generated["status"] == "PASS"
    assert generated["validation_status"] == "PASS"
    assert generated["sampling"]["successful_runs"] == 24
    assert generated["surrogate"]["use_policy"]["may_replace_full_model"] is False

    print("RESULT: PASS - installed validated surrogate contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
