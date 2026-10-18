"""Direct scientific safety-limit, dimension algebra and symbolic solver contracts.

This is a regression suite against executable production code. It does not
patch coverage counters, omit production source or lower acceptance thresholds.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize import dimensional_engine as dimension
from axiomize import limits
from axiomize.tools.symbolic.sympy_tool import (
    SymPyTool, check_equivalence, differentiate, final_size_symbolic,
    find_singularities, jacobian_matrix, simplify_expr,
)

DIMS = {"x": {"length": 1.0}, "y": {"length": 1.0},
        "t": {"time": 1.0}, "k": {}, "z": {}}


@pytest.mark.parametrize("expression, expected", [
    ("x", {"length": 1.0}),
    ("+x", {"length": 1.0}),
    ("-x", {"length": 1.0}),
    ("x+y", {"length": 1.0}),
    ("x-y", {"length": 1.0}),
    ("x%y", {"length": 1.0}),
    ("x*t", {"length": 1.0, "time": 1.0}),
    ("x/t", {"length": 1.0, "time": -1.0}),
    ("x/x", {}),
    ("x**2", {"length": 2.0}),
    ("sqrt(x)", {"length": 0.5}),
    ("Abs(x)", {"length": 1.0}),
    ("Min(x,y)", {"length": 1.0}),
    ("Max(x,y)", {"length": 1.0}),
    ("sin(k)", {}),
    ("exp(k)", {}),
    ("log(1)", {}),
    ("2", {}),
])
def test_dimension_parser_matches_exact_physical_exponents(expression, expected):
    assert dimension._parse_dimension(expression, DIMS) == expected


@pytest.mark.parametrize("expression, fragment", [
    ("x+t", "additive dimension mismatch"),
    ("x%t", "additive dimension mismatch"),
    ("x**t", "dimensional exponent"),
    ("x**(1+1)", "exponent must be a numeric constant"),
    ("sin(x)", "requires dimensionless"),
    ("Min(x,t)", "arguments must have equal dimensions"),
    ("Max(x,t)", "arguments must have equal dimensions"),
    ("y+unknown", "unknown"),
])
def test_dimension_parser_rejects_invalid_math_instead_of_guessing(expression, fragment):
    with pytest.raises(ValueError, match=fragment):
        dimension._parse_dimension(expression, DIMS)


def test_dimension_combination_exactly_cancels_matching_exponents():
    assert dimension._combine({"length": 1.0}, {"length": 1.0}, sign=-1.0) == {}
    assert dimension._combine({"length": 1.0}, {"time": -2.0}) == {
        "length": 1.0, "time": -2.0,
    }


def test_tolerance_does_not_fabricate_dimension_mismatch():
    assert dimension._same({"length": 1.0}, {"length": 1.0 + 1e-13})
    assert not dimension._same({"length": 1.0}, {"length": 1.01})
    assert dimension._same({"length": 0.0}, {})


@pytest.mark.parametrize("input_value, expected", [
    (0, 0), (7, 7), (7.0, 7), (" 007 ", 7), ("+7", 7), ("-0", 0),
    (np.int64(7), 7),
])
def test_bounded_integer_accepts_exact_integer_representations(input_value, expected):
    assert limits.bounded_int(input_value, name="samples", minimum=0, maximum=8) == expected


@pytest.mark.parametrize("bad, fragment", [
    (True, "boolean"),
    (False, "boolean"),
    (1.2, "exact finite"),
    (float("nan"), "exact finite"),
    (float("inf"), "exact finite"),
    ("1.2", "must be an integer"),
    ("0x10", "must be an integer"),
    ("8" * (limits.MAX_INTEGER_DIGITS + 1), "exceeds"),
    (9, "between"),
    (-1, "between"),
    (None, "must be an integer"),
])
def test_bounded_integer_refuses_truncation_and_unbounded_requests(bad, fragment):
    with pytest.raises(ValueError, match=fragment):
        limits.bounded_int(bad, name="samples", minimum=0, maximum=8)


@pytest.mark.parametrize("value, fragment", [
    (True, "boolean"),
    (False, "boolean"),
    (None, "numeric"),
    ("garbled", "numeric"),
    (float("nan"), "finite"),
    (float("inf"), "finite"),
    (-0.1, ">= 0"),
    (2.1, "<= 2"),
])
def test_bounded_float_rejects_non_numeric_nonfinite_and_out_of_range(value, fragment):
    with pytest.raises(ValueError, match=fragment):
        limits.bounded_float(value, name="rate", minimum=0, maximum=2)


def test_strict_lower_float_boundary_is_not_silently_inclusive():
    with pytest.raises(ValueError, match="> 0"):
        limits.bounded_float(0.0, name="rate", minimum=0, minimum_inclusive=False)
    assert limits.bounded_float(0.1, name="rate", minimum=0, maximum=1,
                                minimum_inclusive=False) == 0.1


@pytest.mark.parametrize("value", [[1], (1, 2), []])
def test_bounded_sequence_preserves_input_order_and_type_contract(value):
    assert limits.bounded_sequence(value, name="observations") == list(value)


@pytest.mark.parametrize("value, minimum, maximum", [
    (None, 0, 5),
    ("values", 0, 5),
    ([1], 2, 5),
    ([1, 2, 3], 0, 2),
])
def test_bounded_sequence_fails_closed_on_shape_or_length(value, minimum, maximum):
    with pytest.raises(ValueError, match="array|length"):
        limits.bounded_sequence(value, name="observations", minimum=minimum, maximum=maximum)


def test_result_cell_allocation_limit_enforced_before_large_allocation():
    limits.enforce_result_cells(10, 20, name="trajectory")
    limits.enforce_result_cells(0, 100, name="trajectory")
    with pytest.raises(ValueError, match="hard safety limit"):
        limits.enforce_result_cells(100_000, 100_000, name="trajectory")


@pytest.mark.parametrize("value, fragment", [
    (True, "boolean"),
    ("missing", "numeric"),
    (None, "numeric"),
    (float("nan"), "finite"),
    (float("inf"), "finite"),
])
def test_nonfinite_evidence_is_rejected_before_numerical_aggregation(value, fragment):
    with pytest.raises(ValueError, match=fragment):
        limits.enforce_finite_values([1.0, value], name="measurements")


def test_valid_finite_evidence_is_explicitly_accepted():
    assert limits.enforce_finite_values([0, 1.5, "2.25"], name="measurements") is None


def test_sympy_adapter_reports_real_symbolic_derivative_and_equivalence():
    tool = SymPyTool()
    assert tool.execute({"expression": "x+x"})["result"] == "2*x"
    assert tool.execute({"action": "differentiate", "expression": "x**2",
                         "variable": "x"})["result"] == "2*x"
    assert tool.execute({"action": "equivalence", "expression": "(x+1)**2",
                         "other": "x**2+2*x+1"})["result"] is True


def test_sympy_equivalence_is_false_for_distinct_functions():
    assert check_equivalence("x**2", "x**3") is False
    assert simplify_expr("x+x") == "2*x"
    assert differentiate("x**2", "x") == "2*x"


@pytest.mark.parametrize("bad", [None, {}, {"expression": ""}, {"expression": 7}])
def test_sympy_payload_requires_explicit_valid_expression(bad):
    with pytest.raises(ValueError, match="expression|payload"):
        SymPyTool().validate_input(bad)


def test_sympy_equivalence_requires_two_real_expressions():
    with pytest.raises(ValueError, match="non-empty"):
        SymPyTool().execute({"action": "equivalence", "expression": "x", "other": " "})
    with pytest.raises(ValueError, match="unknown action"):
        SymPyTool().execute({"action": "unsupported", "expression": "x"})


def test_jacobian_exact_derivatives_have_stable_shape():
    assert jacobian_matrix(["x**2+y", "x*y"], ["x", "y"]) == [
        ["2*x", "1"], ["y", "x"],
    ]


@pytest.mark.parametrize("expressions, variables, fragment", [
    ([], ["x"], "expressions must contain"),
    (["x"], [], "variables must contain"),
    ([""], ["x"], "non-empty"),
    (["x"], ["x", "x"], "unique"),
])
def test_symbolic_jacobian_refuses_missing_or_duplicated_model_spec(
    expressions, variables, fragment,
):
    with pytest.raises(ValueError, match=fragment):
        jacobian_matrix(expressions, variables)


def test_symbolic_singularity_detection_distinguishes_regular_from_pole():
    assert find_singularities("x+1", "x") == []
    assert find_singularities("1/(x-2)", "x") == ["2"]


@pytest.mark.parametrize("bad, fragment", [
    (None, "numeric"),
    (float("nan"), "finite"),
    (-0.1, "non-negative"),
])
def test_symbolic_final_size_enforces_physical_domain(bad, fragment):
    with pytest.raises(ValueError, match=fragment):
        final_size_symbolic(bad)


def test_symbolic_final_size_has_correct_subcritical_zero_solution():
    assert final_size_symbolic(0.0) == 0.0
    assert final_size_symbolic(1.0) == 0.0
