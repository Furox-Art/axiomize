"""Direct core and facade symbolic parsers must enforce identical limits."""

from __future__ import annotations

import pytest
import sympy as sp

from axiomize import general_engine as facade
from axiomize import general_engine_core as core
from axiomize.safe_expression import validate_expression


@pytest.mark.parametrize(
    "expression",
    [
        "sin(x) + exp(x)",
        "sqrt(x**2)",
        "Piecewise((x, x > 0), (-x, True))",
    ],
)
def test_every_core_and_facade_symbolic_path_matches_same_approved_ast(expression):
    symbols = {"x": sp.Symbol("x", real=True)}
    ast_tree = validate_expression(expression, allowed_names={"x"})
    assert ast_tree is not None
    from_core = core._sympy_expression(expression, symbols)
    from_facade = facade._sympy_expression(expression, symbols)
    assert sp.simplify(from_core - from_facade) == 0


@pytest.mark.parametrize(
    "expression",
    [
        "9**(10**9)",
        "__import__('os').system('echo bad')",
        "unknown_symbol+x",
        "x.__class__",
        "factorial(100000000)",
    ],
)
def test_direct_core_parse_cannot_bypass_the_public_scientific_safety_boundary(expression):
    symbols = {"x": sp.Symbol("x", real=True)}
    with pytest.raises(ValueError):
        core._sympy_expression(expression, symbols)
    with pytest.raises(ValueError):
        facade._sympy_expression(expression, symbols)
    with pytest.raises(ValueError):
        core._validate_expression_syntax(expression, {"x"})


def test_direct_core_parser_rejects_unknown_names_before_symbolic_execution():
    with pytest.raises(ValueError, match="unknown symbol"):
        core._validate_expression_syntax("x+y", {"x"})
