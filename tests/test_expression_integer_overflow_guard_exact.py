"""Exercise actual bounded-integer folding used to prevent symbolic explosions."""

from __future__ import annotations

import ast

import pytest

from axiomize.safe_expression import (
    MAX_EXPRESSION_CHARS,
    _constant_number,
    _exponent_magnitude,
    _fold_integer_constant,
    auto_symbol_map,
    validate_expression,
)


def expr(source):
    return ast.parse(source, mode="eval").body


@pytest.mark.parametrize(
    ("source", "value"),
    [
        ("1", 1),
        ("-2", -2),
        ("+3", 3),
        ("1+2", 3),
        ("8-3", 5),
        ("7*6", 42),
        ("8//3", 2),
        ("8%3", 2),
        ("2**10", 1024),
        ("factorial(5)", 120),
        ("binomial(5,2)", 10),
        ("product(2,4)", 24),
    ],
)
def test_bounded_integer_arithmetic_matches_python_small_exact_results(source, value):
    assert _fold_integer_constant(expr(source)) == value


@pytest.mark.parametrize(
    "source",
    [
        "1.5",
        "True",
        "x",
        "x+1",
        "3/2",
        "2**-1",
        "sin(2)",
        "factorial(x)",
        "factorial(3, extra=4)",
    ],
)
def test_symbolic_or_noninteger_subtrees_are_not_forged_to_constant(source):
    assert _fold_integer_constant(expr(source)) is None


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("8//0", "division by zero"),
        ("8%0", "modulo by zero"),
        ("factorial(5,6)", "exactly one"),
        ("binomial(5)", "exactly two"),
        ("product(1)", "exactly two"),
        ("factorial(-1)", "must be an integer in"),
        ("binomial(-1,2)", "must be integers"),
        ("product(-1,3)", "product range"),
        ("2**1000000", "exponent magnitude"),
    ],
)
def test_arithmetic_expansion_guards_refuse_unsafe_tree_before_symbolic_eval(source, message):
    with pytest.raises(ValueError, match=message):
        _fold_integer_constant(expr(source))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("3", 3.0),
        ("-2", -2.0),
        ("+5", 5.0),
        ("1.25", 1.25),
    ],
)
def test_numeric_exponent_extraction_is_exact(source, expected):
    assert _constant_number(expr(source)) == pytest.approx(expected)
    assert _exponent_magnitude(expr(source)) == pytest.approx(expected)


@pytest.mark.parametrize("source", ["x", "True", "1+2", "'hello'"])
def test_nonliteral_exponent_is_not_assumed_numeric(source):
    assert _constant_number(expr(source)) is None


@pytest.mark.parametrize(
    ("source", "pattern"),
    [
        ("x+", "invalid mathematical expression"),
        ("x" * (MAX_EXPRESSION_CHARS + 1), "expression exceeds hard limit"),
        ("max", "unknown symbol"),
        ("factorial(9)", "only approved mathematical functions"),
        ("x.__class__", "unsupported expression syntax"),
        ("sin(x, y=2)", "keyword arguments"),
        ("Piecewise()", "requires at least one"),
        ("Piecewise(x)", "arguments must be"),
        ("1 if x else 0", "unsupported expression syntax"),
    ],
)
def test_math_parser_rejects_invalid_input_shapes_and_expansion(source, pattern):
    with pytest.raises(ValueError, match=pattern):
        validate_expression(source, allowed_names={"x"})


def test_function_argument_ceiling_refuses_hostile_multi_argument_expression():
    payload = "Max(" + ",".join(["x"] * 33) + ")"
    with pytest.raises(ValueError, match="too many arguments"):
        validate_expression(payload, allowed_names={"x"})


@pytest.mark.parametrize(
    ("expression", "pattern"),
    [
        (None, "must be a string"),
        (")", "invalid mathematical expression"),
        ("x" * (MAX_EXPRESSION_CHARS + 1), "exceeds hard limit"),
    ],
)
def test_automatic_symbol_map_still_enforces_parser_limits(expression, pattern):
    with pytest.raises(ValueError, match=pattern):
        auto_symbol_map(expression)
