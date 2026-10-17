"""Hardened SymPy input guard does not evaluate unauthorized Python expressions."""

from __future__ import annotations

import ast

import pytest
import sympy as sp

from axiomize.safe_expression import (
    _constant_number,
    _fold_bounded,
    _fold_integer_constant,
    _to_sympy,
    auto_symbol_map,
    sympy_expression,
    validate_expression,
    validate_identifier,
)


def fold(source: str):
    return _fold_integer_constant(ast.parse(source, mode="eval").body)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("5", 5),
        ("-5", -5),
        ("+5", 5),
        ("3+4", 7),
        ("3-4", -1),
        ("3*4", 12),
        ("2**5", 32),
        ("7//2", 3),
        ("7%2", 1),
        ("factorial(5)", 120),
        ("binomial(5,2)", 10),
        ("product(2,4)", 24),
    ],
)
def test_bounded_integer_subtree_folding_respects_exact_integer_semantics(source, expected):
    assert fold(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "True",
        "3.0",
        "x",
        "x+1",
        "sin(1)",
        "factorial(x)",
        "1/2",
        "2**-1",
    ],
)
def test_noninteger_or_symbolic_expression_is_not_treated_as_const_integer(source):
    assert fold(source) is None


@pytest.mark.parametrize(
    ("source", "pattern"),
    [
        ("7//0", "integer division by zero"),
        ("7%0", "integer modulo by zero"),
        ("factorial(1000000)", "factorial argument"),
        ("factorial(1,2)", "exactly one"),
        ("binomial(2)", "exactly two"),
        ("binomial(-1,2)", "binomial arguments"),
        ("product(1)", "exactly two"),
        ("product(-1,2)", "product range"),
        ("9**(10**9)", "exponent"),
    ],
)
def test_constant_expansion_bounds_deny_exponential_resource_exhaustion(source, pattern):
    with pytest.raises(ValueError, match=pattern):
        fold(source)


def test_precomputed_folding_limit_rejects_arbitrary_precision_bomb():
    with pytest.raises(ValueError, match="folded-constant limit"):
        _fold_bounded(1 << 1_000_000, what="test guard")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("3", 3.0),
        ("-3", -3.0),
        ("+3", 3.0),
        ("3.5", 3.5),
    ],
)
def test_simple_finite_real_literals_have_explicit_magnitude(source, expected):
    node = ast.parse(source, mode="eval").body
    assert _constant_number(node) == pytest.approx(expected)


def test_constant_magnitude_none_for_symbolic_and_boolean_expressions():
    for source in ("x", "True", "x+2", "sin(x)"):
        assert _constant_number(ast.parse(source, mode="eval").body) is None


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("x**2", sp.Symbol("x") ** 2),
        ("x%2", sp.Mod(sp.Symbol("x"), 2)),
        ("x!=1", sp.Ne(sp.Symbol("x"), 1)),
        ("x<=1", sp.Le(sp.Symbol("x"), 1)),
        ("x>=1", sp.Ge(sp.Symbol("x"), 1)),
    ],
)
def test_safe_sympy_translation_does_not_use_python_eval(source, expected):
    x = sp.Symbol("x")
    assert sympy_expression(source, {"x": x}) == expected


@pytest.mark.parametrize(
    ("value", "pattern"),
    [
        ([], "expression must be a string"),
        ("", "invalid mathematical expression"),
        ("not_a_mathematical_function(x)", "unapproved mathematical functions"),
        ("x.y", "unsupported expression syntax"),
        ("abs(x)", "unapproved mathematical functions"),
    ],
)
def test_auto_namespace_guards_refuse_unapproved_tokens(value, pattern):
    with pytest.raises(ValueError, match=pattern):
        auto_symbol_map(value)


def test_top_level_tuple_is_not_a_valid_scalar_mathematical_output():
    with pytest.raises(ValueError, match="top-level mathematical expression cannot be a tuple"):
        sympy_expression("(1,2)", {})


def test_reserved_namespace_rejects_implementation_dunder_identifier():
    with pytest.raises(ValueError, match="reserved implementation"):
        validate_identifier("x__internal")


def test_unapproved_explicit_function_allowlist_cannot_override_parser_policy():
    with pytest.raises(ValueError, match="unapproved mathematical functions"):
        validate_expression("myfunc(x)", allowed_names={"x"}, allowed_functions={"myfunc"})


def test_no_keywords_allowed_even_on_mathematically_supported_functions():
    with pytest.raises(ValueError, match="keyword arguments"):
        validate_expression("Min(x, y=2)", allowed_names={"x", "y"})


def test_untrusted_math_ast_call_cannot_reference_attributes():
    with pytest.raises(ValueError, match="only approved mathematical functions|unsupported"):
        validate_expression("sin.__class__(x)", allowed_names={"x"})


def test_private_translation_errors_for_unsupported_ast_nodes():
    with pytest.raises(ValueError, match="unsupported expression syntax"):
        _to_sympy(ast.List(elts=[], ctx=ast.Load()), {}, {})


def test_python_code_in_expression_does_not_execute_on_translation(monkeypatch):
    import os

    def forbidden(*_args, **_kwargs):
        raise AssertionError("security error: external interpreter reached")

    monkeypatch.setattr(os, "system", forbidden)
    with pytest.raises(ValueError):
        sympy_expression("__import__('os').system('x')", {})
