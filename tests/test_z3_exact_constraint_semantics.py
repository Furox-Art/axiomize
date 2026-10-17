"""Actual Z3 checks of bounded real constraints and fail-closed parsing."""

from __future__ import annotations

import pytest

from axiomize.tools.logic.z3_tool import Z3Tool, check_constraints
from axiomize.validation.status import ValidationStatus


@pytest.mark.parametrize(
    ("constraints", "expected"),
    [
        (["x+y==1", "x>0", "y>0"], True),
        (["x>=0", "x<=1"], True),
        (["x>3"], False),
        (["x==1", "x==2"], False),
        (["x*x>=0"], True),
        (["x**2==4"], True),
        (["x>0 and y>=0"], True),
        (["x<0 or x>0"], True),
        (["And(x>=0,x<=1)"], True),
        (["Or(x==1,x==-1)"], True),
        (["Not(x==0)"], True),
        (["x+1 > 0"], True),
        (["x-y==0"], True),
        (["x*y < 0"], True),
        (["x/2 == 1"], True),
        (["x!=y"], True),
        (["0<x<2"], True),
        (["x==0", "x!=0"], False),
    ],
)
def test_real_z3_distinguishes_sat_from_unsat(constraints, expected):
    out = check_constraints(constraints, {"x": (-2.0, 2.0), "y": (-2.0, 2.0)}, timeout_ms=1000)
    assert out["sat"] is expected
    assert out["status"] is (ValidationStatus.PASS if expected else ValidationStatus.FAIL)
    if expected:
        assert -2 <= out["model"]["x"] <= 2
        assert -2 <= out["model"]["y"] <= 2
    else:
        assert out["model"] is None


@pytest.mark.parametrize(
    ("constraints", "domain"),
    [
        (["x/x==1"], {"x": (0.0, 0.0)}),
        (["1/(x-1)>0"], {"x": (1.0, 1.0)}),
    ],
)
def test_zero_division_cannot_be_satisfied_by_solver_totalization(constraints, domain):
    out = check_constraints(constraints, domain, timeout_ms=1000)
    assert out["status"] is ValidationStatus.FAIL
    assert out["sat"] is False


@pytest.mark.parametrize(
    ("constraint", "pattern"),
    [
        ("", "non-empty"),
        ("x", "Boolean relation"),
        ("x.__class__", "unsupported constraint syntax"),
        ("x[0] > 0", "unsupported constraint syntax"),
        ("foo(x)", "only And"),
        ("__import__('os')", "only And"),
        ("x**33 > 1", "integer literal exponent"),
        ("x**-1 > 0", "integer literal exponent"),
        ("x%2==1", "unsupported binary operator"),
        ("x//2==1", "unsupported binary operator"),
        ("1 if x>0 else 0", "unsupported constraint syntax"),
        ("other==0", "unknown variable"),
        ("And()", "requires at least one"),
        ("Not(x>0,y>0)", "exactly one"),
        ("And(x>0,y>0,z=1)", "keyword arguments"),
    ],
)
def test_constraints_reject_unverified_syntax_and_variables(constraint, pattern):
    with pytest.raises(ValueError, match=pattern):
        check_constraints([constraint], {"x": (-2.0, 2.0), "y": (-2.0, 2.0)}, timeout_ms=1000)


@pytest.mark.parametrize(
    ("variables", "pattern"),
    [
        ({}, "must contain"),
        ({"sin": [0, 1]}, "reserved mathematical"),
        ({"x": [2.0, 1.0]}, "lower bound"),
        ({"x": [0.0]}, "must contain"),
        ({"x": [float("nan"), 1.0]}, "must be finite"),
        ({"x": [0.0, float("inf")]}, "must be finite"),
        ({"x": [0.0, 1.0], "bad-variable": [0.0, 1.0]}, "must start"),
    ],
)
def test_domain_bounds_must_be_finite_and_valid(variables, pattern):
    with pytest.raises(ValueError, match=pattern):
        check_constraints(["x==0"], variables, timeout_ms=1000)


@pytest.mark.parametrize(
    ("constraints", "variables", "pattern"),
    [
        ("x==0", {"x": [-1.0, 1.0]}, "constraints must be an array"),
        (["x==0", 1], {"x": [-1.0, 1.0]}, "every constraint must be a string"),
        (["x==0"], [], "variables must be an object"),
    ],
)
def test_z3_request_contract_is_explicit(constraints, variables, pattern):
    with pytest.raises(ValueError, match=pattern):
        check_constraints(constraints, variables, timeout_ms=1000)


@pytest.mark.parametrize("timeout", [0, -1, 1.5, True])
def test_z3_timeout_ceiling_and_integrality_are_enforced(timeout):
    with pytest.raises(ValueError, match="z3.timeout_ms"):
        check_constraints(["x==0"], {"x": [-1.0, 1.0]}, timeout_ms=timeout)


def test_z3_tool_dispatch_returns_satisfiable_model_and_honest_status():
    result = Z3Tool().execute(
        {
            "variables": {"x": [0.0, 2.0]},
            "constraints": ["x>0", "x<2"],
            "timeout_ms": 1000,
        }
    )
    assert result["sat"] is True
    assert result["status"] == "PASS"
    assert 0 < result["model"]["x"] < 2
    assert result["timeout_ms"] == 1000


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"variables": {}},
        {"constraints": []},
        {"variables": [], "constraints": []},
        {"variables": {}, "constraints": "x>0"},
    ],
)
def test_z3_tool_rejects_malformed_payload_before_solver(payload):
    with pytest.raises(ValueError):
        Z3Tool().execute(payload)
