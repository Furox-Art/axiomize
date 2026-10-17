"""Symbolic adapters must respect mathematical identities and input ceilings."""

from __future__ import annotations

import math

import pytest

from axiomize.tools.symbolic.sympy_tool import (
    SymPyTool,
    check_equivalence,
    differentiate,
    final_size_symbolic,
    find_singularities,
    jacobian_matrix,
    simplify_expr,
)


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("x+x", "2*x"),
        ("(x+1)*(x-1)", "x**2 - 1"),
        ("sin(x)**2+cos(x)**2", "1"),
    ],
)
def test_symbolic_simplification_retains_exact_identity(expression, expected):
    assert simplify_expr(expression) == expected


@pytest.mark.parametrize(
    ("expression", "variable", "expected"),
    [
        ("x**3 + 2*x", "x", "3*x**2 + 2"),
        ("x*y + sin(y)", "y", "x + cos(y)"),
        ("a*x", "z", "0"),
    ],
)
def test_derivative_is_exact_symbolic_not_finite_difference(expression, variable, expected):
    assert differentiate(expression, variable) == expected


@pytest.mark.parametrize(
    ("a", "b", "equal"),
    [
        ("x + x", "2*x", True),
        ("sin(x)**2+cos(x)**2", "1", True),
        ("(x+1)*(x-1)", "x*x-1", True),
        ("x+1", "x+2", False),
    ],
)
def test_symbolic_equivalence_has_explicit_equal_and_not_equal(a, b, equal):
    assert check_equivalence(a, b) is equal


def test_jacobian_matches_analytic_partial_derivatives():
    assert jacobian_matrix(["x*x+y", "sin(x)*y"], ["x", "y"]) == [["2*x", "1"], ["y*cos(x)", "sin(x)"]]


@pytest.mark.parametrize(
    ("expressions", "variables", "pattern"),
    [
        ([], ["x"], "expressions must contain"),
        (["x"], [], "variables must contain"),
        ([""], ["x"], "non-empty"),
        (["x"], ["x", "x"], "must be unique"),
        (["x"], ["sin"], "reserved"),
        (["x+__import__('os')"], ["x"], "unapproved"),
    ],
)
def test_jacobian_rejects_unsafe_or_ambiguous_symbols(expressions, variables, pattern):
    with pytest.raises(ValueError, match=pattern):
        jacobian_matrix(expressions, variables)


@pytest.mark.parametrize("r0", [0.0, 0.5, 1.0])
def test_subcritical_epidemic_final_size_is_zero(r0):
    assert final_size_symbolic(r0) == 0.0


def test_supercritical_epidemic_size_solves_self_consistency_equation():
    r0 = 2.0
    z = final_size_symbolic(r0)
    assert 0.7 < z < 0.9
    assert z == pytest.approx(1.0 - math.exp(-r0 * z), abs=1e-10)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.1, "unknown"])
def test_epidemic_final_size_rejects_nonphysical_reproduction_number(bad):
    with pytest.raises(ValueError, match="r0"):
        final_size_symbolic(bad)


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("1/(x-1)", ["1"]),
        ("1/(x**2-1)", ["-1", "1"]),
        ("x**2+3", []),
    ],
)
def test_singularities_are_exact_not_synthetic_samples(expr, expected):
    assert find_singularities(expr, "x") == expected


def test_symbolic_tool_dispatch_is_validated_before_execution():
    tool = SymPyTool()
    assert tool.execute({"expression": "x+x"})["result"] == "2*x"
    assert tool.execute({"expression": "x**2", "action": "differentiate", "variable": "x"})["result"] == "2*x"
    assert tool.execute({"expression": "x+x", "action": "equivalence", "other": "2*x"})["result"] is True


@pytest.mark.parametrize(
    ("payload", "pattern"),
    [
        ({}, "needs an 'expression'"),
        ({"expression": ""}, "non-empty"),
        ({"expression": "x", "action": "equivalence"}, "non-empty"),
        ({"expression": "x", "action": "bad"}, "unknown action"),
    ],
)
def test_symbolic_tool_rejects_unknown_requests(payload, pattern):
    with pytest.raises(ValueError, match=pattern):
        SymPyTool().execute(payload)
