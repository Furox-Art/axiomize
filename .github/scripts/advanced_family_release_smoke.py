#!/usr/bin/env python3
"""Installed-wheel CLI smoke gate for all advanced Model IR families."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
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


def _run_model(work: Path, name: str, model_ir: dict[str, Any], **extra: Any) -> dict[str, Any]:
    request = work / f"{name}.json"
    request.write_text(json.dumps({"model_ir": model_ir, **extra}), encoding="utf-8")
    proc = subprocess.run(
        [_exe(), "model", "--action", "simulate", "--input-json", str(request)],
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if proc.returncode != 0:
        raise SmokeFailure(f"{name}: CLI exited {proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(f"{name}: CLI stdout is not JSON: {proc.stdout}") from exc
    if not isinstance(payload, dict):
        raise SmokeFailure(f"{name}: CLI returned non-object JSON")
    return payload


def _base(name: str, family: str, variables: list[dict[str, Any]], parameters: list[dict[str, Any]],
          equations: list[dict[str, Any]], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "name": name,
        "domain": "general",
        "family": family,
        "independent_variable": "t",
        "independent_unit": "dimensionless",
        "variables": variables,
        "parameters": parameters,
        "equations": equations,
        "metadata": metadata or {},
    }


def _test_pde(work: Path) -> None:
    model = _base(
        "smoke-pde", "pde", [{"name": "u", "initial": 1.0}], [{"name": "k", "value": 0.5}],
        [{"target": "u", "expression": "-k*u", "kind": "derivative"}],
        {"pde": {"grid_points": 8, "diffusion": {"u": 0.1}}},
    )
    out = _run_model(work, "pde", model, t_span=[0.0, 0.5], points=12)
    _assert(out.get("status") == "PASS", f"PDE failed: {out}")
    final = sum(out["states"]["u"][-1]) / len(out["states"]["u"][-1])
    _assert(abs(final - math.exp(-0.25)) < 2e-3, f"PDE numeric mismatch: {final}")


def _test_dae(work: Path) -> None:
    model = _base(
        "smoke-dae", "dae",
        [{"name": "x", "initial": 1.0}, {"name": "z", "role": "latent", "initial": 1.0}],
        [{"name": "k", "value": 1.0}],
        [
            {"target": "x", "expression": "-z", "kind": "derivative"},
            {"target": "", "expression": "z-k*x", "kind": "residual"},
        ],
    )
    out = _run_model(work, "dae", model, t_span=[0.0, 0.5], points=12)
    _assert(out.get("status") == "PASS", f"DAE failed: {out}")
    _assert(out["diagnostics"]["max_algebraic_residual"] < 1e-6, "DAE algebraic residual too large")


def _test_optimization(work: Path) -> None:
    model = _base(
        "smoke-opt", "optimization",
        [{"name": "x", "role": "decision", "initial": 0.0, "bounds": [-10.0, 10.0]}], [],
        [{"target": "", "expression": "(x-2)**2", "kind": "objective"}],
        {"optimization": {"objective": "(x-2)**2"}},
    )
    out = _run_model(work, "optimization", model)
    _assert(out.get("status") == "PASS", f"optimization failed: {out}")
    _assert(abs(float(out["states"]["x"]) - 2.0) < 1e-3, "optimization optimum mismatch")


def _test_control(work: Path) -> None:
    model = _base(
        "smoke-control", "control", [{"name": "x", "initial": 1.0}], [],
        [{"target": "x", "expression": "0", "kind": "state_space"}],
        {"control": {"A": [[-1.0]], "B": [[0.0]], "C": [[1.0]], "D": [[0.0]], "input": 0.0}},
    )
    out = _run_model(work, "control", model, t_span=[0.0, 0.5], points=12)
    _assert(out.get("status") == "PASS", f"control failed: {out}")
    _assert(out["diagnostics"]["stability"] == "stable", "control stability mismatch")


def _test_network(work: Path) -> None:
    model = _base(
        "smoke-network", "network", [{"name": "x", "initial": 0.5}], [{"name": "c", "value": 0.5}],
        [{"target": "x", "expression": "c*laplacian_x", "kind": "derivative"}],
        {"network": {"nodes": ["a", "b"], "edges": [["a", "b"]], "initial": {"x": [1.0, 0.0]}}},
    )
    out = _run_model(work, "network", model, t_span=[0.0, 0.5], points=12)
    _assert(out.get("status") == "PASS", f"network failed: {out}")
    _assert(len(out["states"]["x"][-1]) == 2, "network node state shape mismatch")


def _test_bayesian(work: Path) -> None:
    model = _base(
        "smoke-bayes", "bayesian", [{"name": "y", "role": "output", "initial": 0.0}],
        [{"name": "a", "value": 0.5, "fit": True, "prior": {"dist": "normal", "mu": 0.0, "sigma": 3.0}}],
        [{"target": "y", "expression": "a*x", "kind": "observation"}],
        {"bayesian": {
            "data": {"x": [0.0, 1.0, 2.0, 3.0]},
            "observations": [0.0, 2.0, 4.0, 6.0],
            "mean_expression": "a*x", "sigma": 0.2,
            "draws": 200, "burn": 60, "proposal_scale": {"a": 0.1},
        }},
    )
    blocked = _run_model(work, "bayesian-blocked", model, seed=17)
    _assert(blocked.get("status") == "APPROVAL_REQUIRED", "Bayesian compute must require explicit approval")
    out = _run_model(work, "bayesian", model, seed=17, approve_heavy=True)
    _assert(out.get("status") == "PASS", f"Bayesian failed: {out}")
    _assert(abs(float(out["posterior"]["a"]["mean"]) - 2.0) < 0.35, "Bayesian posterior mismatch")


def _test_agent_based(work: Path) -> None:
    model = _base(
        "smoke-abm", "agent_based", [{"name": "x", "initial": 1.0}], [{"name": "k", "value": 0.5}],
        [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
        {"agents": {"count": 3}},
    )
    out = _run_model(work, "agent-based", model, t_span=[0.0, 0.5], points=12, seed=3)
    _assert(out.get("status") == "PASS", f"agent-based failed: {out}")
    _assert(len(out["states"]["x"][-1]) == 3, "agent state shape mismatch")


def _test_discrete_event(work: Path) -> None:
    model = _base(
        "smoke-des", "discrete_event", [{"name": "n", "initial": 0.0}], [{"name": "lam", "value": 10.0}],
        [{"target": "n", "expression": "0", "kind": "event_state"}],
        {"discrete_event": {"events": [{"name": "arrival", "rate": "lam", "delta": {"n": 1.0}}]}},
    )
    out = _run_model(work, "discrete-event", model, t_span=[0.0, 1.0], points=12, seed=9)
    _assert(out.get("status") == "PASS", f"discrete-event failed: {out}")
    _assert(out["diagnostics"]["total_events"] > 0, "discrete-event produced no events")


def _test_hybrid(work: Path) -> None:
    model = _base(
        "smoke-hybrid", "hybrid", [{"name": "x", "initial": 1.0}], [],
        [{"target": "x", "expression": "-1", "kind": "derivative"}],
        {"hybrid": {"events": [{"name": "reset", "expression": "x", "direction": -1, "reset": {"x": "1"}}]}},
    )
    out = _run_model(work, "hybrid", model, t_span=[0.0, 1.3], points=18)
    _assert(out.get("status") == "PASS", f"hybrid failed: {out}")
    _assert(out["diagnostics"]["event_count"] >= 1, "hybrid event did not fire")


def _test_causal(work: Path) -> None:
    model = _base(
        "smoke-causal", "causal", [{"name": "y", "role": "output", "initial": 0.0}], [],
        [{"target": "y", "expression": "0", "kind": "causal"}],
        {
            "causal_identification": {"randomized": True},
            "causal": {
                "treatment": "treat", "outcome": "outcome", "identification": {"randomized": True},
                "data": {"treat": [0.0, 1.0, 0.0, 1.0], "outcome": [1.0, 3.0, 1.0, 3.0]},
            },
        },
    )
    out = _run_model(work, "causal", model)
    _assert(out.get("status") == "PASS", f"causal failed: {out}")
    _assert(abs(float(out["causal_effect"]["estimate"]) - 2.0) < 1e-9, "causal effect mismatch")


def _test_multiphysics(work: Path) -> None:
    source = _base(
        "source", "ode", [{"name": "x", "initial": 2.0}], [],
        [{"target": "x", "expression": "0", "kind": "derivative"}],
    )
    target = _base(
        "target", "ode", [{"name": "y", "initial": 1.0}], [{"name": "k", "value": 1.0}],
        [{"target": "y", "expression": "-k*y", "kind": "derivative"}],
    )
    model = _base(
        "smoke-multiphysics", "multiphysics", [{"name": "q", "initial": 0.0}], [],
        [{"target": "q", "expression": "0", "kind": "coupling"}],
        {"multiphysics": {
            "components": {"source": source, "target": target},
            "couplings": [{
                "from_component": "source", "from_state": "x",
                "to_component": "target", "to_parameter": "k",
                "reduction": "final", "scale": 0.5,
            }],
            "max_iterations": 4, "tolerance": 1e-10,
        }},
    )
    blocked = _run_model(work, "multiphysics-blocked", model, t_span=[0.0, 0.5], points=10)
    _assert(blocked.get("status") == "APPROVAL_REQUIRED", "multiphysics must require approval")
    out = _run_model(work, "multiphysics", model, t_span=[0.0, 0.5], points=10, approve_heavy=True)
    _assert(out.get("status") == "PASS", f"multiphysics failed: {out}")
    _assert(out["diagnostics"]["converged"] is True, "multiphysics coupling did not converge")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="axiomize-advanced-family-smoke-") as tmp:
        work = Path(tmp)
        tests = [
            _test_pde, _test_dae, _test_optimization, _test_control, _test_network,
            _test_bayesian, _test_agent_based, _test_discrete_event, _test_hybrid,
            _test_causal, _test_multiphysics,
        ]
        for test in tests:
            test(work)
            print(f"PASS {test.__name__.removeprefix('_test_')}")
    print("RESULT: PASS - installed CLI executes every advanced Model IR family")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeFailure as exc:
        print(f"RESULT: FAIL - {exc}", file=sys.stderr)
        raise SystemExit(1)
