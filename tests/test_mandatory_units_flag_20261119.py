"""Mandatory units: explicit status / opt-in fail-closed enforcement.

The README promises mandatory units, but an omitted unit silently defaulted to
``dimensionless``. ``unit_declaration_audit`` now surfaces the omission as an
explicit WARNING, and ``ModelIR.from_dict(require_units=True)`` refuses it.
The default stays backward compatible.
"""

from __future__ import annotations

import pytest

from axiomize.model_ir import ModelIR, unit_declaration_audit


def _payload(**overrides) -> dict:
    base = {
        "schema_version": "1.0", "name": "units", "domain": "physics", "family": "ode",
        "independent_variable": "t", "independent_unit": "day",
        "variables": [{"name": "x", "unit": "dimensionless", "initial": 1.0}],
        "parameters": [{"name": "k", "unit": "1/day", "value": 0.5}],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    }
    base.update(overrides)
    return base


def test_require_units_passes_when_all_units_explicit() -> None:
    model = ModelIR.from_dict(_payload(), require_units=True)
    assert model.variables[0].unit == "dimensionless"


def test_require_units_rejects_omitted_variable_unit() -> None:
    payload = _payload(variables=[{"name": "x", "initial": 1.0}])
    with pytest.raises(ValueError, match="variable:x"):
        ModelIR.from_dict(payload, require_units=True)


def test_require_units_rejects_omitted_parameter_unit() -> None:
    payload = _payload(parameters=[{"name": "k", "value": 0.5}])
    with pytest.raises(ValueError, match="parameter:k"):
        ModelIR.from_dict(payload, require_units=True)


def test_require_units_rejects_omitted_independent_unit() -> None:
    payload = _payload()
    del payload["independent_unit"]
    with pytest.raises(ValueError, match="independent_unit"):
        ModelIR.from_dict(payload, require_units=True)


def test_default_remains_backward_compatible() -> None:
    payload = _payload(variables=[{"name": "x", "initial": 1.0}])
    model = ModelIR.from_dict(payload)
    assert model.variables[0].unit == "dimensionless"


def test_audit_reports_warning_with_omitted_symbols() -> None:
    payload = _payload(variables=[{"name": "x", "initial": 1.0}], parameters=[{"name": "k", "value": 0.5}])
    del payload["independent_unit"]
    audit = unit_declaration_audit(payload)
    assert audit["status"] == "WARNING"
    assert audit["omitted"] == ["variable:x", "parameter:k", "independent_unit"]
    assert audit["defaulted_to"] == "dimensionless"


def test_audit_pass_when_complete() -> None:
    audit = unit_declaration_audit(_payload())
    assert audit["status"] == "PASS"
    assert audit["omitted"] == []


def test_audit_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="must be an object"):
        unit_declaration_audit(["not", "a", "model"])


def test_audit_tolerates_non_list_sections() -> None:
    audit = unit_declaration_audit({"variables": None, "parameters": "bad", "independent_unit": "day"})
    assert audit["omitted"] == []
