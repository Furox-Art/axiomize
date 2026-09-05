"""Regression tests for Axiomize trust-boundary and resource hardening.

These tests intentionally exercise hostile or malformed inputs.  They are kept
separate from scientific-regression tests so release CI cannot accidentally
remove the security contract while refactoring numerical code.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from axiomize.execution.sandbox import run_python
from axiomize.model_ir import MigrationApprovalRequired, ModelIR
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


def test_model_ir_rejects_duplicate_derivative_targets() -> None:
    payload = _decay_model()
    payload["equations"].append({"target": "x", "kind": "derivative", "expression": "0"})
    model = ModelIR.from_dict(payload)
    checks = model.validate_structure()
    assert any(c["status"] == "FAIL" and "duplicate" in c["name"] for c in checks)


def test_future_model_ir_never_silently_migrates() -> None:
    payload = _decay_model()
    payload["schema_version"] = "99.0"
    with pytest.raises(MigrationApprovalRequired):
        ModelIR.from_dict(payload)
    with pytest.raises(ValueError):
        ModelIR.from_dict(payload, allow_migration=True)


def test_untrusted_python_execution_is_blocked() -> None:
    rec = run_python("print('should not execute')")
    assert rec.exit_code != 0
    assert "explicit" in rec.stderr.lower() or "trust" in rec.stderr.lower()


def test_trusted_python_execution_does_not_forward_secret_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret")
    monkeypatch.setenv("AXIOMIZE_TEST_SECRET", "super-secret-2")
    code = "import os; print(os.getenv('OPENAI_API_KEY')); print(os.getenv('AXIOMIZE_TEST_SECRET'))"
    rec = run_python(code, timeout_s=10, trusted=True)
    assert rec.exit_code == 0
    assert "super-secret" not in rec.stdout
    assert "super-secret-2" not in rec.stdout


def test_rest_json_body_limit_constant_is_positive() -> None:
    from axiomize.server import rest_server

    assert rest_server.MAX_REQUEST_BYTES > 0


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
