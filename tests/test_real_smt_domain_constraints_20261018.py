"""Actual SMT satisfiability and parser-domain regression checks.

All assertions are computed by Z3 with real bounded variables; unsupported
syntax and singular denominators must be rejected rather than approximated.
"""
from __future__ import annotations

import math

import pytest

from axiomize.tools.logic import z3_tool
from axiomize.validation.status import ValidationStatus


@pytest.mark.parametrize("expression, expected", [
    ("x > 0", True),
    ("x >= 0", True),
    ("x < 0", False),
    ("x <= 1", True),
    ("x == 0.5", True),
    ("x != 0.5", True),
    ("0 <= x <= 1", True),
    ("(x >= 0) and (x <= 1)", True),
    ("(x < 0) or (x > 1)", False),
    ("And(x >= 0, x <= 1)", True),
    ("Or(x < 0, x > 1)", False),
    ("Not(x < 0)", True),
    ("not (x < 0)", True),
    ("x*x >= 0", True),
    ("x**2 >= 0", True),
    ("(x+1)-x == 1", True),
    ("x/1 == x", True),
])
def test_smt_relations_use_real_solver_semantics(expression, expected):
    result = z3_tool.check_constraints([expression], {"x": [0.0, 1.0]})
    assert result["sat"] is expected
    assert result["status"] is (
        ValidationStatus.PASS if expected else ValidationStatus.FAIL
    )
    if expected:
        assert isinstance(result["model"]["x"], (int, float))
        assert math.isfinite(result["model"]["x"])
        assert 0.0 <= result["model"]["x"] <= 1.0
    else:
        assert result["model"] is None


def test_contradictory_constraints_are_genuinely_unsatisfiable():
    out=z3_tool.check_constraints(["x > 0", "x < 0"], {"x": [-1.0, 1.0]})
    assert out["sat"] is False
    assert out["status"] is ValidationStatus.FAIL


def test_division_by_zero_must_not_be_solved_via_smt_totalization():
    out=z3_tool.check_constraints(["x == 0", "1/x > 2"], {"x": [0.0, 1.0]})
    assert out["sat"] is False
    assert out["model"] is None


@pytest.mark.parametrize("constraint,pattern", [
    ("", "non-empty"),
    (None, "non-empty"),
    ("unknown > 0", "unknown variable"),
    ("x + 1", "Boolean relation"),
    ("x // 2 > 0", "unsupported"),
    ("x**33 > 0", "powers require"),
    ("x**(-1) > 0", "powers require"),
    ("x**1.5 > 0", "powers require"),
    ("x in [1,2]", "unsupported"),
    ("eval(x)", "only And"),
    ("And()", "at least one"),
    ("Not(x > 0, x < 1)", "exactly one"),
    ("Or(a=1)", "keyword arguments"),
])
def test_untrusted_smt_syntax_fails_explicitly(constraint, pattern):
    import z3
    with pytest.raises(ValueError, match=pattern):
        z3_tool._parse_constraint(constraint, {"x": z3.Real("x")})


@pytest.mark.parametrize("invalid,pattern", [
    (None, "constraints must be an array"),
    ("x >= 0", "constraints must be an array"),
])
def test_smt_constraint_set_must_be_an_array(invalid, pattern):
    with pytest.raises(ValueError, match=pattern):
        z3_tool.check_constraints(invalid, {"x":[0,1]})


def test_large_smt_constraint_set_is_refused_before_solver_allocation():
    with pytest.raises(ValueError, match="hard limit"):
        z3_tool.check_constraints(["x > 0"] * 10001, {"x": [0,1]})


def test_nonstring_constraint_cannot_be_executed():
    with pytest.raises(ValueError, match="every constraint must be a string"):
        z3_tool.check_constraints([1], {"x": [0,1]})


@pytest.mark.parametrize("variables,pattern", [
    (None, "variables must be an object"),
    ({}, "variables must contain"),
    ({"x": []}, "bounds for"),
    ({"x": [2.0, 1.0]}, "lower bound"),
    ({"x": [float("nan"), 1.0]}, "must be finite"),
    ({"x": [0.0, float("inf")]}, "must be finite"),
])
def test_smt_variable_domain_is_finite_explicit_and_ordered(variables, pattern):
    with pytest.raises(ValueError, match=pattern):
        z3_tool.check_constraints([], variables)


@pytest.mark.parametrize("timeout", [0, -1, True, 1.5, 60001])
def test_smt_timeout_must_be_bounded_exact_integer(timeout):
    with pytest.raises(ValueError, match="timeout"):
        z3_tool.check_constraints([], {"x":[0,1]}, timeout_ms=timeout)


def test_adapter_output_translates_real_status_and_model_without_loss():
    tool=z3_tool.Z3Tool()
    out=tool.execute({"constraints":["x == 0.5"],"variables":{"x":[0,1]},
                      "timeout_ms":2000})
    assert out["status"]=="PASS"
    assert out["sat"] is True
    assert out["timeout_ms"]==2000
    assert out["model"]["x"]==pytest.approx(0.5)


@pytest.mark.parametrize("payload,pattern", [
    (None,"payload must be an object"),
    ({},"needs"),
    ({"constraints":"x>=0","variables":{"x":[0,1]}},"constraints must be an array"),
    ({"constraints":[],"variables":[]},"variables must be an object"),
])
def test_adapter_prevalidates_shape_before_smt_solver(payload,pattern):
    with pytest.raises(ValueError,match=pattern):
        z3_tool.Z3Tool().validate_input(payload)
