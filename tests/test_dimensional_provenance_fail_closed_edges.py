"""Equation dimensions are measured against declared units and never guessed."""

from __future__ import annotations

import pytest

from axiomize.dimensional_engine import (
    _parse_dimension,
    _register_advanced_symbols,
    equation_dimension_checks,
    merge_dimension_checks,
)
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, VariableSpec


def make_model(*, equation, family=ModelFamily.ODE, metadata=None, unit="metre"):
    return ModelIR(
        name="observed system",
        domain="physics",
        family=family,
        variables=[VariableSpec("x", unit=unit, initial=1.0)],
        parameters=[],
        equations=[equation],
        independent_unit="second",
        metadata=metadata or {},
    )


def test_declared_expression_unit_takes_precedence_over_implied_target_unit():
    m = make_model(equation=EquationSpec("x", "x", kind="algebraic", unit="metre"))
    rows = equation_dimension_checks(m)
    assert rows[0]["status"] == "PASS"
    assert "declared unit metre" in rows[0]["detail"]


def test_explicit_incorrect_equation_unit_is_not_silently_repaired():
    m = make_model(equation=EquationSpec("x", "x", kind="algebraic", unit="second"))
    rows = equation_dimension_checks(m)
    assert rows[0]["status"] == "FAIL"
    assert "expected=" in rows[0]["detail"]


def test_unknown_derivative_target_is_a_failed_equation_not_unknown_result():
    m = make_model(equation=EquationSpec("undocumented", "x", kind="derivative"))
    result = equation_dimension_checks(m)
    assert result[0]["status"] == "FAIL"
    assert "unknown derivative target" in result[0]["detail"]


def test_unknown_algebraic_target_is_a_failed_equation():
    m = make_model(equation=EquationSpec("undocumented", "x", kind="algebraic"))
    result = equation_dimension_checks(m)
    assert result[0]["status"] == "FAIL"
    assert "unknown target" in result[0]["detail"]


def test_unanchored_objective_is_unverified_not_automatically_pass():
    m = make_model(equation=EquationSpec("", "x", kind="objective"))
    result = equation_dimension_checks(m)
    assert result[0]["status"] == "UNVERIFIED"
    assert "no declared unit" in result[0]["detail"]


def test_invalid_unknown_unit_is_a_recorded_failure_before_solver_execution():
    m = make_model(equation=EquationSpec("x", "x", kind="algebraic"), unit="no_such_unit_2026")
    report = merge_dimension_checks({"status": "PASS", "checks": []}, m)
    assert report["status"] == "FAIL"
    assert report["equation_dimension_checks"][0]["status"] == "FAIL"
    assert "equation_dimension_engine" in report["equation_dimension_checks"][0]["name"]


def test_explicit_advanced_symbol_unit_is_not_an_inferred_free_parameter():
    m = make_model(
        equation=EquationSpec("x", "observed", kind="algebraic"),
        metadata={"symbol_units": {"observed": "metre"}},
    )
    result = equation_dimension_checks(m)
    assert result[0]["status"] == "PASS", result


def test_bayesian_data_units_are_only_added_for_unobserved_named_data():
    m = make_model(
        equation=EquationSpec("x", "observed", kind="algebraic"),
        family=ModelFamily.BAYESIAN,
        metadata={"bayesian": {"data": {"observed": [1.0, 2.0]}, "data_units": {"observed": "metre"}}},
    )
    result = equation_dimension_checks(m)
    assert result[0]["status"] == "PASS", result


def test_recorded_bayesian_data_cannot_override_declared_state_units():
    m = make_model(
        equation=EquationSpec("x", "x", kind="algebraic"),
        family=ModelFamily.BAYESIAN,
        metadata={"bayesian": {"data": {"x": [1.0, 2.0]}, "data_units": {"x": "second"}}},
    )
    result = equation_dimension_checks(m)
    assert result[0]["status"] == "PASS", result


def test_true_boolean_ast_constant_cannot_be_interpreted_as_dimensionless_measurement():
    with pytest.raises(ValueError, match="only numeric constants"):
        _parse_dimension("True", {})


def test_dimensional_exponent_cannot_erase_units():
    with pytest.raises(ValueError, match="dimensional exponent"):
        _parse_dimension("x**t", {"x": {"L": 1.0}, "t": {"T": 1.0}})


def test_custom_observables_under_metadata_are_registered_with_provenance():
    m = make_model(equation=EquationSpec("x", "x"))
    dims = {"x": {"length": 1.0}}
    units = {"x": "metre"}
    m.metadata = {"symbol_units": {"measured": "metre"}}
    _register_advanced_symbols(m, dims, units)
    assert "measured" in dims
    assert units["measured"] == "metre"
