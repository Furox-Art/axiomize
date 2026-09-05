"""Regression tests for Axiomize trust-boundary and resource hardening.

These tests intentionally exercise hostile or malformed inputs. They are kept
separate from scientific-regression tests so release CI cannot accidentally
remove the security contract while refactoring numerical code.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from axiomize.execution.sandbox import UnsafeExecutionDenied, run_python
from axiomize.model_ir import ModelIR, UnsupportedSchemaVersion
from axiomize.safe_expression import sympy_expression, validate_expression


def _decay_model() -> dict:
    return {
        "schema_version": "1.0",
        "name": "decay",
        "domain": "physics",
        "family": "ode",
        "variables": [{"name": "x", "unit": "dimensionless", "initial": 1.0}],
        "parameters": [{"name": "k", "value": 1.0, "unit": "1/second"}],
        "equations": [{"target": "x", "kind": "derivative", "expression": "-k*x"}],
        "independent_variable": "t",
        "independent_unit": "second",
    }


@pytest.mark.parametrize(
    "payload",
    [
        "().__class__.__mro__",
        "__import__('os').system('echo nope')",
        "x[0]",
        "(lambda: 1)()",
        "open('secret')",
    ],
)
def test_expression_parser_rejects_python_escape_syntax(payload: str) -> None:
    with pytest.raises(ValueError):
        validate_expression(payload, allowed_names={"x"})


def test_expression_parser_accepts_bounded_math() -> None:
    import sympy as sp

    x = sp.Symbol("x", real=True)
    expr = sympy_expression("sqrt(x**2) + exp(-x)", {"x": x})
    assert expr is not None


def test_direct_general_engine_core_uses_hardened_parser() -> None:
    from axiomize import general_engine_core as core

    with pytest.raises(ValueError):
        core._sympy_expression("__import__('os').system('echo nope')", {})


def test_model_ir_rejects_duplicate_derivative_targets() -> None:
    payload = _decay_model()
    payload["equations"].append({"target": "x", "kind": "derivative", "expression": "0"})
    with pytest.raises(ValueError, match="unique_derivative_targets"):
        ModelIR.from_dict(payload)


def test_future_model_ir_never_silently_migrates() -> None:
    payload = _decay_model()
    payload["schema_version"] = "99.0"
    with pytest.raises(UnsupportedSchemaVersion):
        ModelIR.from_dict(payload)
    with pytest.raises(UnsupportedSchemaVersion):
        ModelIR.from_dict(payload, allow_migration=True)


def test_pde_result_allocation_is_bounded_before_solver_runs() -> None:
    from axiomize.general_engine import simulate_model

    payload = {
        "schema_version": "1.0",
        "name": "large-pde",
        "domain": "physics",
        "family": "pde",
        "variables": [{"name": "u", "unit": "dimensionless", "initial": 1.0}],
        "parameters": [],
        "equations": [{"target": "u", "kind": "derivative", "expression": "0"}],
        "metadata": {"pde": {"grid_points": 4096}},
    }
    model = ModelIR.from_dict(payload)
    with pytest.raises(ValueError, match="PDE trajectory"):
        simulate_model(model, points=200_000, approve_heavy=True)


def test_causal_design_matrix_has_hard_dimension_bound() -> None:
    from axiomize.general_engine import simulate_model

    n = 10_000
    covariates = [f"c{i}" for i in range(2048)]
    # The guard derives matrix width from the adjustment set before the native
    # estimator can allocate a dense design matrix. We do not need to materialize
    # 2,048 full covariate vectors to prove that ceiling.
    payload = {
        "schema_version": "1.0",
        "name": "large-causal",
        "domain": "general",
        "family": "causal",
        "variables": [{"name": "y", "unit": "dimensionless", "initial": 0.0}],
        "parameters": [],
        "equations": [{"target": "y", "kind": "causal", "expression": "y"}],
        "metadata": {
            "causal": {
                "data": {"treatment": [0.0] * n, "outcome": [0.0] * n},
                "treatment": "treatment",
                "outcome": "outcome",
                "adjustment_set": covariates,
                "identification": {"randomized": True},
            }
        },
    }
    model = ModelIR.from_dict(payload)
    with pytest.raises(ValueError, match="design matrix"):
        simulate_model(model, points=2, approve_heavy=True)


def test_untrusted_python_execution_is_blocked() -> None:
    with pytest.raises(UnsafeExecutionDenied):
        run_python("print('should not execute')")


def test_trusted_python_execution_does_not_forward_secret_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret")
    monkeypatch.setenv("AXIOMIZE_TEST_SECRET", "super-secret-2")
    code = "import os; print(os.getenv('OPENAI_API_KEY')); print(os.getenv('AXIOMIZE_TEST_SECRET'))"
    rec = run_python(code, timeout_s=10, allow_unsafe_code=True)
    assert rec.exit_code == 0
    assert "super-secret" not in rec.stdout
    assert "super-secret-2" not in rec.stdout
    assert rec.environment_inherited is False


def test_rest_json_body_limit_constant_is_positive() -> None:
    from axiomize.server.rest_server import MAX_JSON_BYTES

    assert MAX_JSON_BYTES > 0


def test_rest_connections_have_bounded_io_timeout(tmp_path: Path) -> None:
    from axiomize.server.rest_server import start_server

    server = start_server("127.0.0.1", 0, run_root=tmp_path, connection_timeout_s=5)
    try:
        assert server.connection_timeout_s == 5.0
    finally:
        server.server_close()


def test_run_state_detects_tampering(tmp_path: Path) -> None:
    from axiomize.runs.state import RunState

    run = RunState(problem_definition="tamper-test")
    run.save(tmp_path)
    run_file = tmp_path / "run.json"
    payload = json.loads(run_file.read_text(encoding="utf-8"))
    payload["results"] = {"forged": True}
    run_file.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        RunState.load(tmp_path)
