"""Regression for real-arithmetic denominator semantics in Z3 constraints."""

from axiomize.tools.logic.z3_tool import check_constraints


def test_division_by_zero_is_not_satisfied_by_z3_totalization() -> None:
    result = check_constraints(["1 / x > 0", "x == 0"], {"x": (0.0, 0.0)})
    assert result["sat"] is False
    assert result["status"].value == "FAIL"


def test_nonzero_denominator_still_solves_normally() -> None:
    result = check_constraints(["1 / x > 0", "x >= 1"], {"x": (1.0, 2.0)})
    assert result["sat"] is True
    assert result["status"].value == "PASS"
