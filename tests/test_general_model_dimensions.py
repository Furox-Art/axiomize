from __future__ import annotations

from axiomize.application.general_services import model_simulate_service, model_validate_service


def _model(k_unit: str) -> dict:
    return {
        "schema_version": "1.0",
        "name": "decay",
        "domain": "physics",
        "family": "ode",
        "independent_variable": "t",
        "independent_unit": "day",
        "variables": [{"name": "x", "unit": "dimensionless", "initial": 1.0}],
        "parameters": [{"name": "k", "unit": k_unit, "value": 0.5}],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    }


def test_equation_dimension_pass_is_visible() -> None:
    out = model_validate_service({"model_ir": _model("1/day")})
    assert out["status"] == "PASS"
    checks = out["validation"]["equation_dimension_checks"]
    assert checks == [{
        "name": "equation_dimension:x",
        "status": "PASS",
        "detail": "actual={'T': -1.0}; expected={'T': -1.0}; basis=d(x)/d(t)",
    }]


def test_dimensionally_invalid_model_is_blocked_before_execution() -> None:
    out = model_simulate_service({"model_ir": _model("dimensionless"), "t_span": [0.0, 1.0]})
    assert out["status"] == "FAIL"
    assert out["stage"] == "pre_validation"
    failed = [c for c in out["validation"]["equation_dimension_checks"] if c["status"] == "FAIL"]
    assert failed and failed[0]["name"] == "equation_dimension:x"
