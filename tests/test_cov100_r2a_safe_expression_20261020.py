"""Round-2 coverage hardening for the hardened expression parser.

The tests drive ``validate_expression``/``sympy_expression``/``auto_symbol_map``
and the bounded constant folder, asserting both the accepted symbolic result and
the typed refusals for unsupported syntax and oversized constants.
"""
from __future__ import annotations

import ast

import pytest
import sympy as sp

from axiomize import safe_expression
from axiomize.limits import (
    MAX_EXPRESSION_CHARS,
    MAX_EXPRESSION_DEPTH,
    MAX_EXPRESSION_NODES,
)
from axiomize.safe_expression import (
    _fold_integer_constant,
    _to_sympy,
    auto_symbol_map,
    sympy_expression,
    validate_expression,
)


def _body(expression: str) -> ast.AST:
    return ast.parse(expression, mode="eval").body


def test_validate_expression_requires_a_string_and_rejects_oversized_text() -> None:
    with pytest.raises(ValueError, match="expression must be a string"):
        validate_expression(123, allowed_names=set())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match=f"hard limit of {MAX_EXPRESSION_CHARS}"):
        validate_expression("1" * (MAX_EXPRESSION_CHARS + 1), allowed_names=set())


def test_validate_expression_wraps_syntax_errors() -> None:
    with pytest.raises(ValueError, match="invalid mathematical expression"):
        validate_expression("x +", allowed_names={"x"})


def test_validate_expression_bounds_ast_node_count() -> None:
    terms = 300
    expression = " + ".join(["1"] * terms)
    assert len(list(ast.walk(ast.parse(expression, mode="eval")))) > MAX_EXPRESSION_NODES
    with pytest.raises(ValueError, match=f"AST-node limit of {MAX_EXPRESSION_NODES}"):
        validate_expression(expression, allowed_names=set())


def test_validate_expression_bounds_nesting_depth() -> None:
    expression = "-" * (MAX_EXPRESSION_DEPTH + 1) + "x"
    with pytest.raises(ValueError, match=f"nesting limit of {MAX_EXPRESSION_DEPTH}"):
        validate_expression(expression, allowed_names={"x"})


def test_validate_expression_limits_function_arity() -> None:
    expression = "Max(" + ", ".join(["1"] * 33) + ")"
    with pytest.raises(ValueError, match="too many arguments"):
        validate_expression(expression, allowed_names=set())


def test_non_numeric_constant_inside_power_is_reported() -> None:
    with pytest.raises(ValueError, match="only real numeric or boolean constants"):
        validate_expression("2 ** 'a'", allowed_names=set())


def test_constant_power_beyond_fold_limit_is_refused() -> None:
    # 17**1000 is under the exponent ceiling but its integer expansion exceeds
    # the folded-constant bit ceiling and must be rejected before evaluation.
    with pytest.raises(ValueError, match="constant power exceeds"):
        validate_expression("17**1000", allowed_names=set())


def test_fold_integer_constant_ignores_non_folding_unary_operator() -> None:
    assert _fold_integer_constant(_body("~5")) is None
    assert _fold_integer_constant(_body("+5")) == 5
    assert _fold_integer_constant(_body("-5")) == -5


def test_fold_integer_constant_ignores_symbolic_arguments() -> None:
    assert _fold_integer_constant(_body("factorial(x)")) is None
    assert _fold_integer_constant(_body("factorial(5)")) == 120


def test_fold_integer_constant_ignores_unknown_expansive_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        safe_expression,
        "_INTEGER_EXPANSIVE_FUNCTIONS",
        frozenset({"factorial", "product", "binomial", "min"}),
    )
    assert _fold_integer_constant(_body("min(1, 2)")) is None


def test_float_constants_translate_to_sympy_float() -> None:
    result = sympy_expression("x + 1.5", {"x": sp.Symbol("x", real=True)})
    assert isinstance(result, sp.Add)
    floats = [arg for arg in result.args if isinstance(arg, sp.Float)]
    assert floats == [sp.Float(1.5)]


def test_translation_refuses_unsupported_constant_and_symbol() -> None:
    with pytest.raises(ValueError, match="unsupported constant"):
        _to_sympy(_body("'a'"), {}, {})
    with pytest.raises(ValueError, match="unknown symbol in expression: z"):
        _to_sympy(_body("z"), {}, {})


def test_unary_plus_is_accepted_and_invert_is_refused() -> None:
    symbol = sp.Symbol("x", real=True)
    assert sympy_expression("+x", {"x": symbol}) == symbol
    with pytest.raises(ValueError, match="unsupported unary operator"):
        _to_sympy(_body("~x"), {"x": symbol}, {})


def test_modulo_translates_and_floor_division_is_refused() -> None:
    symbol = sp.Symbol("x", real=True)
    result = sympy_expression("x % 2", {"x": symbol})
    assert isinstance(result, sp.Mod)
    assert result == sp.Mod(symbol, 2)
    with pytest.raises(ValueError, match="unsupported binary operator"):
        _to_sympy(_body("x // 2"), {"x": symbol}, {})


def test_equality_and_inequality_translate() -> None:
    x = sp.Symbol("x", real=True)
    y = sp.Symbol("y", real=True)
    assert sympy_expression("x == y", {"x": x, "y": y}) == sp.Eq(x, y)
    assert sympy_expression("x != y", {"x": x, "y": y}) == sp.Ne(x, y)
    membership = ast.Compare(left=ast.Name(id="x", ctx=ast.Load()),
                             ops=[ast.In()], comparators=[ast.Name(id="y", ctx=ast.Load())])
    with pytest.raises(ValueError, match="unsupported comparison operator"):
        _to_sympy(membership, {"x": x, "y": y}, {})


def test_boolean_operators_translate_and_unknown_boolop_is_refused() -> None:
    x = sp.Symbol("x", real=True)
    y = sp.Symbol("y", real=True)
    assert sympy_expression("x > 0 and y > 0", {"x": x, "y": y}) == sp.And(x > 0, y > 0)
    assert sympy_expression("x > 0 or y > 0", {"x": x, "y": y}) == sp.Or(x > 0, y > 0)
    unsupported = ast.BoolOp(op=ast.BitAnd(), values=[ast.Constant(value=True), ast.Constant(value=False)])
    with pytest.raises(ValueError, match="unsupported boolean operator"):
        _to_sympy(unsupported, {}, {})


def test_unsupported_node_types_are_refused_by_translation() -> None:
    with pytest.raises(ValueError, match="unsupported expression syntax: List"):
        _to_sympy(_body("[1]"), {}, {})


def test_auto_symbol_map_bounds_text_and_wraps_syntax_errors() -> None:
    with pytest.raises(ValueError, match=f"hard limit of {MAX_EXPRESSION_CHARS}"):
        auto_symbol_map("x" * (MAX_EXPRESSION_CHARS + 1))
    with pytest.raises(ValueError, match="invalid mathematical expression"):
        auto_symbol_map("x +")
    symbols = auto_symbol_map("a + b")
    assert sorted(symbols) == ["a", "b"]
