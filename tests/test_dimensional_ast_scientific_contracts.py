"""Dimension arithmetic is checked symbolically, never inferred from a fit."""

from __future__ import annotations

import pytest

from axiomize.dimensional_engine import (
    ModelDimensionMismatch,
    _parse_dimension,
    _register_advanced_symbols,
    equation_dimension_checks,
    merge_dimension_checks,
)
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, VariableSpec


@pytest.fixture
def dimensions():
    return {
        "x": {"L": 1.0},
        "t": {"T": 1.0},
        "v": {"L": 1.0, "T": -1.0},
        "n": {},
    }


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("x/t", {"L": 1.0, "T": -1.0}),
        ("x+x", {"L": 1.0}),
        ("x-x", {"L": 1.0}),
        ("x*1", {"L": 1.0}),
        ("x**2", {"L": 2.0}),
        ("x**0", {}),
        ("sqrt(x*x)", {"L": 1.0}),
        ("Abs(x)", {"L": 1.0}),
        ("Min(x,x)", {"L": 1.0}),
        ("Max(x,x)", {"L": 1.0}),
        ("sin(n)", {}),
        ("log(n)", {}),
        ("exp(1)", {}),
        ("x/t * t", {"L": 1.0}),
        ("+x", {"L": 1.0}),
        ("-x", {"L": 1.0}),
    ],
)
def test_valid_dimension_expression_is_derived_not_guessed(dimensions, expression, expected):
    assert _parse_dimension(expression, dimensions) == expected


@pytest.mark.parametrize(
    ("expression", "pattern"),
    [
        ("x+t", "additive dimension mismatch"),
        ("x-t", "additive dimension mismatch"),
        ("x%t", "additive dimension mismatch"),
        ("x**t", "dimensional exponent"),
        ("x**(1+1)", "exponent must be a numeric constant"),
        ("sin(x)", "requires dimensionless"),
        ("exp(x)", "requires dimensionless"),
        ("Min(x,t)", "equal dimensions"),
        ("Max(x,t)", "equal dimensions"),
        ("Abs(x,t)", "expects one"),
        ("sqrt(x,t)", "expects one"),
        ("x>1", "unsupported syntax"),
        ("bad+x", "unknown symbol"),
    ],
)
def test_invalid_dimension_operations_fail_instead_of_canceling_units(dimensions, expression, pattern):
    with pytest.raises(ValueError, match=pattern):
        _parse_dimension(expression, dimensions)


def test_network_generated_symbols_inherit_state_unit_exactly():
    model = ModelIR(
        name="network",
        domain="physics",
        family=ModelFamily.NETWORK,
        variables=[VariableSpec("x", unit="metre", initial=1.0)],
        parameters=[],
        equations=[],
    )
    dimensions = {"x": {"length": 1.0}}
    units = {"x": "metre"}
    _register_advanced_symbols(model, dimensions, units)
    for name in ("mean_x", "neighbor_x_sum", "neighbor_x_mean", "laplacian_x"):
        assert dimensions[name] == dimensions["x"]
        assert units[name] == "metre"
    assert dimensions["degree"] == {}
    assert units["degree"] == "dimensionless"


def test_agent_generated_mean_inherits_original_dimensions():
    model = ModelIR(
        name="agents",
        domain="biology",
        family=ModelFamily.AGENT_BASED,
        variables=[VariableSpec("x", unit="metre", initial=1.0)],
        parameters=[],
        equations=[],
    )
    dims = {"x": {"length": 1.0}}
    units = {"x": "metre"}
    _register_advanced_symbols(model, dims, units)
    assert dims["mean_x"] == dims["x"]
    assert "laplacian_x" not in dims


def test_dimension_validation_catches_undeclared_unit_mismatch():
    model = ModelIR(
        name="bad-units",
        domain="physics",
        family=ModelFamily.ODE,
        variables=[VariableSpec("x", unit="metre", initial=1.0)],
        parameters=[],
        equations=[EquationSpec("x", "x", kind="derivative")],
        independent_unit="second",
    )
    rows = equation_dimension_checks(model)
    assert len(rows) == 1
    assert rows[0]["status"] == "FAIL"
    combined = merge_dimension_checks({"status": "PASS", "checks": [{"status": "PASS", "name": "structure"}]}, model)
    assert combined["status"] == "FAIL"
    assert combined["checks"][0]["name"] == "structure"
    assert combined["equation_dimension_checks"][0]["status"] == "FAIL"


def test_dimension_validation_accepts_correct_inverse_time_parameter():
    model = ModelIR(
        name="decay",
        domain="physics",
        family=ModelFamily.ODE,
        variables=[VariableSpec("x", unit="metre", initial=1.0)],
        parameters=[],
        equations=[EquationSpec("x", "-x/t", kind="derivative")],
        independent_unit="second",
    )
    result = equation_dimension_checks(model)
    assert result[0]["status"] == "PASS", result


def test_dimension_mismatch_error_exposes_proof_of_failure():
    validation = {
        "status": "FAIL",
        "checks": [
            {"name": "equation_dimension:x", "status": "FAIL", "detail": "wrong dimensionality"},
        ],
    }
    error = ModelDimensionMismatch("unphysical dynamics", validation=validation)
    assert len(error.failed_checks) == 1
    assert error.failed_checks[0]["name"] == "equation_dimension:x"
    assert error.validation is validation
