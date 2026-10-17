"""Mathematical parsing boundaries must be checked before SymPy evaluation."""

from __future__ import annotations

import pytest
import sympy as sp

from axiomize.safe_expression import (
    auto_symbol_map,
    sympy_expression,
    validate_expression,
    validate_identifier,
)


@pytest.mark.parametrize(
    ("symbol", "message"),
    [
        ("9x", "start with"),
        ("__secret", "start with"),
        ("x__private", "reserved implementation"),
        ("sin", "reserved mathematical"),
        ("False", "reserved mathematical"),
        ("x-y", "start with"),
    ],
)
def test_namespace_is_bounded_to_simple_explicit_identifiers(symbol, message):
    with pytest.raises(ValueError, match=message):
        validate_identifier(symbol)


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("", "non-empty"),
        (None, "must be a string"),
        ("1.0e999", "must be finite"),
        ('"secret"', "only real numeric"),
        ("x.y", "unsupported expression syntax"),
        ("x[1]", "unsupported expression syntax"),
        ("x if x > 1 else 2", "unsupported expression syntax"),
        ("x < 1 < 2", "chained comparisons"),
        ("sin(x, y=1)", "keyword arguments"),
        ("Piecewise()", "at least one"),
        ("Piecewise(x)", "arguments must be"),
        ("x**10000000", "exponent magnitude"),
        ("9**(10**9)", "exponent"),
        ("x + missing", "unknown symbol"),
        ("eval(x)", "only approved mathematical functions"),
    ],
)
def test_rejected_math_payload_never_enters_symbolic_evaluator(expression, message):
    with pytest.raises(ValueError, match=message):
        validate_expression(expression, allowed_names={"x", "y"})


@pytest.mark.parametrize(
    "expression",
    [
        "x+y*2",
        "x<=y",
        "(x<y) and (y>0)",
        "Piecewise((x,x>0),(0,True))",
        "Min(x,y)+Max(x,y)",
        "sin(x)+cos(y)",
        "Abs(x)+sqrt(y**2)",
        "Heaviside(x)",
    ],
)
def test_allowed_symbols_produce_sympy_expression(expression):
    result = sympy_expression(expression, {"x": sp.Symbol("x", real=True), "y": sp.Symbol("y", real=True)})
    assert isinstance(result, (sp.Basic, bool))


def test_auto_symbol_map_cannot_silently_allow_unapproved_function():
    with pytest.raises(ValueError, match="unapproved"):
        auto_symbol_map("secret(x)")


def test_auto_symbol_map_only_creates_declared_non_function_symbols():
    result = auto_symbol_map("sin(x) + y")
    assert set(result) == {"x", "y"}
