"""Adversarial AST, SymPy translation and bounded constant folding contracts."""

from __future__ import annotations

import ast

import pytest
import sympy as sp

from axiomize import safe_expression as safe


def integer_tree(text):
    return ast.parse(text, mode="eval").body


@pytest.mark.parametrize("text, expected", [
    ("3", 3), ("-4", -4), ("+4", 4),
    ("3+4", 7), ("9-10", -1), ("2*5", 10),
    ("9//2", 4), ("9%2", 1), ("2**8", 256),
    ("2**-2", None), ("x+1", None),
    ("1.2", None), ("True", None),
    ("3==3", None), ("sin(1)", None),
])
def test_constant_folder_only_folds_actual_bounded_integers(text, expected):
    assert safe._fold_integer_constant(integer_tree(text)) == expected


@pytest.mark.parametrize("text, pattern", [
    ("9//0", "integer division by zero"),
    ("9%0", "integer modulo by zero"),
    ("9**(10**9)", "exponent magnitude exceeds hard limit"),
    ("2**100000", "exponent magnitude exceeds hard limit"),
    ("factorial(-1)", "factorial argument"),
    ("factorial(1,2)", "factorial takes exactly one"),
    ("binomial(1)", "binomial takes exactly two"),
    ("binomial(-1,2)", "binomial arguments"),
    ("product(1)", "product takes exactly two"),
])
def test_bounded_integer_folder_rejects_expansive_arithmetic(text, pattern):
    with pytest.raises(ValueError, match=pattern):
        safe._fold_integer_constant(integer_tree(text))


@pytest.mark.parametrize("text, expected", [
    ("factorial(5)", 120),
    ("binomial(5,2)", 10),
    ("product(2,4)", 24),
    ("product(4,2)", 24),
])
def test_bounded_integer_combinatorics_are_exact(text, expected):
    assert safe._fold_integer_constant(integer_tree(text)) == expected


@pytest.mark.parametrize("name, pattern", [
    ("_internal", "ASCII letter"),
    ("x__y", "reserved implementation-style"),
    ("sin", "reserved mathematical"),
    ("None", "reserved mathematical"),
    ("name with spaces", "ASCII letter"),
    ("a.b", "ASCII letter"),
])
def test_symbol_namespace_has_no_implementation_shadowing(name, pattern):
    with pytest.raises(ValueError, match=pattern):
        safe.validate_identifier(name)


@pytest.mark.parametrize("expression, pattern", [
    ("", "non-empty"),
    ("x.__class__", "unsupported expression syntax"),
    ("__import__(\"os\")", "reserved implementation-style|approved"),
    ("x[0]", "unsupported expression syntax"),
    ("(lambda x: x)(3)", "only approved mathematical"),
    ("x if x>0 else 0", "unsupported expression syntax"),
    ("x < 1 < 2", "chained comparisons"),
    ("sin(x=3)", "keyword arguments"),
    ("Piecewise()", "requires at least one"),
    ("Piecewise(x)", "arguments must be"),
    ("unknown+1", "unknown symbol"),
    ("eval(x)", "only approved mathematical"),
    ("1+2j", "only real numeric"),
])
def test_mathematical_input_refuses_host_language_execution(expression, pattern):
    with pytest.raises(ValueError, match=pattern):
        safe.validate_expression(expression, allowed_names={"x"})


def test_expression_evaluation_does_not_execute_python_builtins():
    x = sp.Symbol("x", real=True)
    e = safe.sympy_expression("x**2 + 2*x + 1", {"x": x})
    assert sp.simplify(e - (x + 1)**2) == 0
    with pytest.raises(ValueError):
        safe.sympy_expression("__import__(\"os\").system(\"true\")", {})


def test_piecewise_and_boolean_relations_translate_with_correct_domains():
    x = sp.Symbol("x", real=True)
    converted = safe.sympy_expression("Piecewise((x,x>=0),(-x,True))", {"x": x})
    assert converted.subs(x, -2) == 2
    assert converted.subs(x, 3) == 3
    assert safe.sympy_expression("x < 2", {"x": x}) == sp.Lt(x, 2)


def test_unknown_and_invalid_symbol_maps_do_not_invent_parameters():
    symbols = safe.auto_symbol_map("sin(x) + y**2")
    assert sorted(symbols) == ["x", "y"]
    with pytest.raises(ValueError, match="unapproved mathematical functions"):
        safe.auto_symbol_map("exec(x)")
    with pytest.raises(ValueError, match="expression must be a string"):
        safe.auto_symbol_map(None)


def test_top_level_tuple_is_not_equation():
    with pytest.raises(ValueError, match="top-level.*tuple"):
        safe.sympy_expression("(1,2)", {})


def test_non_numeric_constants_are_not_allowed():
    with pytest.raises(ValueError, match="real numeric"):
        safe.validate_expression("\"hello\"", allowed_names=set())
    with pytest.raises(ValueError, match="finite"):
        safe._check_constant(float("inf"))


def test_exponent_magnitude_folds_nested_integer_terms():
    assert safe._exponent_magnitude(integer_tree("2+3")) == 5
    assert safe._exponent_magnitude(integer_tree("x+3")) is None
    assert safe._exponent_magnitude(integer_tree("-4")) == -4


def test_unsupported_function_namespace_cannot_be_enabled_by_caller():
    with pytest.raises(ValueError, match="unapproved mathematical functions"):
        safe.validate_expression("dangerous(x)", allowed_names={"x"}, allowed_functions={"dangerous"})
