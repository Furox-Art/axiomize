"""Defense in depth at AST translation boundaries: no alternative Python evaluator."""

from __future__ import annotations

import ast

import pytest
import sympy as sp

from axiomize.safe_expression import (
    _fold_integer_constant,
    _to_sympy,
    sympy_expression,
    validate_expression,
)


def untrusted_ast(source):
    return ast.parse(source, mode="eval").body


def test_integer_constant_guard_rejects_power_before_large_result_allocation():
    with pytest.raises(ValueError, match="folded-constant limit"):
        _fold_integer_constant(untrusted_ast("256**600"))


def test_integer_constant_folding_never_interprets_arbitrary_unary_not_as_a_number():
    assert _fold_integer_constant(untrusted_ast("not 5")) is None


def test_ast_node_limit_is_checked_before_symbolic_computation():
    attack = "+".join(["x"] * 300)
    with pytest.raises(ValueError, match="AST-node limit"):
        validate_expression(attack, allowed_names={"x"})


def test_nested_expression_limit_is_checked_before_evaluation():
    deep = "x"
    for _ in range(45):
        deep = f"(x+{deep})"
    with pytest.raises(ValueError, match="nesting limit"):
        validate_expression(deep, allowed_names={"x"})


def test_sympy_translator_refuses_non_numeric_constant_even_if_called_directly():
    with pytest.raises(ValueError, match="unsupported constant"):
        _to_sympy(ast.Constant(value="hidden string"), {}, {})


def test_sympy_translator_refuses_unbound_symbol_even_if_caller_skips_validation():
    with pytest.raises(ValueError, match="unknown symbol"):
        _to_sympy(ast.Name(id="unknown", ctx=ast.Load()), {}, {})


def test_sympy_translator_supports_positive_and_negative_unary_without_eval():
    assert _to_sympy(untrusted_ast("+2"), {}, {}) == 2
    assert _to_sympy(untrusted_ast("-2"), {}, {}) == -2


def test_sympy_translator_refuses_unsupported_unary_operator_without_python_execution():
    with pytest.raises(ValueError, match="unsupported unary operator"):
        _to_sympy(untrusted_ast("not 2"), {}, {})


def test_sympy_translator_refuses_python_floor_division_operator():
    with pytest.raises(ValueError, match="unsupported binary operator"):
        _to_sympy(untrusted_ast("4//2"), {}, {})


def test_sympy_translator_refuses_python_identity_comparison_as_math_relation():
    with pytest.raises(ValueError, match="unsupported comparison operator"):
        _to_sympy(untrusted_ast("2 is 2"), {}, {})


def test_sympy_translator_refuses_nonmath_boolean_operation():
    with pytest.raises(ValueError, match="unsupported boolean operator"):
        _to_sympy(ast.BoolOp(op=ast.BitOr(), values=[ast.Constant(value=True), ast.Constant(value=False)]), {}, {})


def test_supported_math_boolean_or_is_translated_to_a_symbolic_predicate():
    x = sp.Symbol("x", real=True)
    out = sympy_expression("(x<0) or (x>1)", {"x": x})
    assert out == sp.Or(sp.Lt(x, 0), sp.Gt(x, 1))


def test_supported_math_equality_uses_sympy_relation_not_python_identity():
    x = sp.Symbol("x", real=True)
    out = sympy_expression("x==0", {"x": x})
    assert isinstance(out, sp.Equality)


def test_future_integer_expansion_function_without_bounded_handler_is_never_folded(
    monkeypatch,
):
    from axiomize import safe_expression as guard

    # Simulate an allow-list extended in a later release without a corresponding
    # bounded implementation. No symbolic evaluation may be attempted.
    monkeypatch.setattr(
        guard,
        "_INTEGER_EXPANSIVE_FUNCTIONS",
        guard._INTEGER_EXPANSIVE_FUNCTIONS | {"future_expansion"},
    )
    assert guard._fold_integer_constant(untrusted_ast("future_expansion(5)")) is None
