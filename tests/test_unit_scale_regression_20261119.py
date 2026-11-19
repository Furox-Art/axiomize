"""Canonical unit-scale normalization is fail-closed (the 86400x blind spot).

Dimensional analysis ignored scale: a rate declared ``1/s`` integrated against
``t`` in ``day`` passed every check while the number was off by 86400x. The
engine now carries a canonical SI scale per unit, converts explicitly, and
emits a FAIL scale check (blocking execution) whenever an equation's actual
and expected scales disagree. Silent PASS + wrong number is never allowed.
"""

from __future__ import annotations

import math

import pytest

from axiomize import dimensional_engine as de
from axiomize.application.general_services import model_simulate_service
from axiomize.model_ir import ModelIR
from axiomize.validation.dimensions import (
    _UNIT_TABLE,
    DimensionalMismatch,
    convert_value,
    scale_of,
)


def _decay(independent_unit: str, k_unit: str) -> ModelIR:
    return ModelIR.from_dict({
        "schema_version": "1.0", "name": "scale-decay", "domain": "physics",
        "family": "ode", "independent_variable": "t", "independent_unit": independent_unit,
        "variables": [{"name": "x", "unit": "dimensionless", "initial": 1.0}],
        "parameters": [{"name": "k", "unit": k_unit, "value": 0.5}],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    })


def test_scale_of_known_units() -> None:
    assert scale_of("day") == 86400.0
    assert scale_of("s") == 1.0
    assert scale_of("1/day") == pytest.approx(1.0 / 86400.0)
    assert scale_of("cm") == 0.01
    assert scale_of("mol/L") == 1000.0
    assert scale_of("dimensionless") == 1.0


def test_scale_table_covers_every_dimension_unit() -> None:
    for unit in _UNIT_TABLE:
        value = scale_of(unit)
        assert math.isfinite(value) and value > 0, unit


@pytest.mark.parametrize("unit", ["", "bogus-unit"])
def test_scale_of_unknown_and_empty_fail_closed(unit: str) -> None:
    with pytest.raises(DimensionalMismatch):
        scale_of(unit)


def test_convert_value_day_to_seconds() -> None:
    assert convert_value(1.0, "day", "s") == 86400.0
    assert convert_value(2.0, "hour", "min") == pytest.approx(120.0)


def test_convert_value_rate_per_day_to_per_second() -> None:
    assert convert_value(0.3, "1/day", "1/s") == pytest.approx(0.3 / 86400.0)


def test_convert_value_dimension_mismatch_fail_closed() -> None:
    with pytest.raises(DimensionalMismatch, match="dimensions differ"):
        convert_value(1.0, "m", "s")


@pytest.mark.parametrize("value", ["x", None, float("nan"), float("inf")])
def test_convert_value_rejects_non_numeric_or_non_finite(value) -> None:
    with pytest.raises(ValueError):
        convert_value(value, "day", "s")


def test_86400_scale_mismatch_is_fail_closed_regression() -> None:
    # Dimensions agree (both T^-1) but the rate is 1/s while t is in day:
    # the number would be 86400x too large. This must NOT silently pass.
    model = _decay("day", "1/s")
    dim_checks = de.equation_dimension_checks(model)
    assert dim_checks[0]["status"] == "PASS"
    scale_checks = de.equation_unit_scale_checks(model)
    assert scale_checks[0]["status"] == "FAIL"
    assert "factor=86400" in scale_checks[0]["detail"]
    merged = de.merge_dimension_checks({"status": "PASS", "checks": []}, model)
    assert merged["status"] == "FAIL"
    assert merged["equation_unit_scale_checks"][0]["status"] == "FAIL"


def test_scale_mismatch_blocks_simulation() -> None:
    out = model_simulate_service({"model_ir": _decay("day", "1/s").to_dict(), "t_span": [0.0, 1.0]})
    assert out["status"] == "FAIL"
    assert out["stage"] == "pre_validation"


def test_consistent_units_scale_pass() -> None:
    model = _decay("day", "1/day")
    scale_checks = de.equation_unit_scale_checks(model)
    assert scale_checks[0]["status"] == "PASS"
    merged = de.merge_dimension_checks({"status": "PASS", "checks": []}, model)
    assert merged["status"] == "PASS"


def test_scale_check_skipped_for_residual_without_unit() -> None:
    model = ModelIR.from_dict({
        "schema_version": "1.0", "name": "res", "domain": "math", "family": "algebraic",
        "independent_variable": "t", "independent_unit": "day",
        "variables": [{"name": "x", "unit": "dimensionless"}],
        "parameters": [],
        "equations": [{"target": "", "expression": "x - x", "kind": "residual"}],
    })
    assert de.equation_unit_scale_checks(model) == []


def test_declared_equation_unit_scale_pass_and_fail() -> None:
    base = {
        "schema_version": "1.0", "name": "decl", "domain": "physics", "family": "algebraic",
        "independent_variable": "t", "independent_unit": "day",
        "variables": [{"name": "x", "unit": "dimensionless"}],
        "parameters": [{"name": "k", "unit": "1/day", "value": 0.5}],
    }
    ok = ModelIR.from_dict({**base, "equations": [
        {"target": "r", "expression": "k*x", "kind": "residual", "unit": "1/day"}]})
    assert de.equation_unit_scale_checks(ok)[0]["status"] == "PASS"
    bad = ModelIR.from_dict({**base, "equations": [
        {"target": "r", "expression": "k*x", "kind": "residual", "unit": "1/s"}]})
    assert de.equation_unit_scale_checks(bad)[0]["status"] == "FAIL"


def test_additive_scale_mismatch_fail_closed() -> None:
    model = ModelIR.from_dict({
        "schema_version": "1.0", "name": "add", "domain": "physics", "family": "algebraic",
        "independent_variable": "t", "independent_unit": "day",
        "variables": [{"name": "x", "unit": "cm"}, {"name": "y", "unit": "m"}],
        "parameters": [],
        "equations": [{"target": "", "expression": "x + y", "kind": "residual"}],
    })
    checks = de.equation_unit_scale_checks(model)
    assert checks[0]["status"] == "FAIL"
    assert "additive unit-scale mismatch" in checks[0]["detail"]


def test_min_max_scale_mismatch_fail_closed() -> None:
    model = ModelIR.from_dict({
        "schema_version": "1.0", "name": "mm", "domain": "physics", "family": "algebraic",
        "independent_variable": "t", "independent_unit": "day",
        "variables": [{"name": "x", "unit": "cm"}, {"name": "y", "unit": "m"}],
        "parameters": [],
        "equations": [{"target": "", "expression": "Max(x, y)", "kind": "residual"}],
    })
    checks = de.equation_unit_scale_checks(model)
    assert checks[0]["status"] == "FAIL"
    assert "equal unit scales" in checks[0]["detail"]


@pytest.mark.parametrize("target,kind,fragment", [
    ("ghost", "derivative", "unknown derivative target"),
    ("ghost", "algebraic", "unknown target"),
])
def test_scale_check_unknown_target_fail_closed(target: str, kind: str, fragment: str) -> None:
    from axiomize.model_ir import EquationSpec, ModelFamily, VariableSpec

    model = ModelIR(
        name="unk", domain="physics", family=ModelFamily.ALGEBRAIC,
        variables=[VariableSpec(name="x", unit="dimensionless")],
        parameters=[], equations=[EquationSpec(target=target, expression="1", kind=kind)],
        independent_variable="t", independent_unit="day",
    )
    checks = de.equation_unit_scale_checks(model)
    assert checks[0]["status"] == "FAIL"
    assert fragment in checks[0]["detail"]


def test_merge_scale_engine_crash_is_fail_closed() -> None:
    from types import SimpleNamespace

    broken = SimpleNamespace(
        variables=[SimpleNamespace(name="x", unit=object())],
        parameters=[], independent_variable="t", independent_unit="day",
        equations=[], family="algebraic", metadata={},
    )
    merged = de.merge_dimension_checks({"status": "PASS"}, broken)
    assert merged["status"] == "FAIL"
    assert merged["equation_unit_scale_checks"][0]["name"] == "equation_unit_scale_engine"


_DIMS = {"x": {"L": 1}, "t": {"T": 1}}
_SCALES = {"x": 0.01, "t": 60.0}


@pytest.mark.parametrize("expression,expected", [
    ("x", 0.01),
    ("-x", 0.01),
    ("2", 1.0),
    ("x/t", 0.01 / 60.0),
    ("x*t", 0.01 * 60.0),
    ("x**2", 0.01 ** 2),
    ("sqrt(x)", 0.1),
    ("Abs(x)", 0.01),
    ("Min(x, x)", 0.01),
    ("x - x", 0.01),
    ("sin(x/x)", 1.0),
])
def test_parse_scale_combines_canonical_scales(expression: str, expected: float) -> None:
    assert de._parse_scale(expression, _DIMS, _SCALES) == pytest.approx(expected)
