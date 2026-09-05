from __future__ import annotations

from axiomize.application.general_services import model_export_service


MODEL = {
    "schema_version": "1.0",
    "name": "service-decay",
    "domain": "physics",
    "family": "ode",
    "independent_variable": "t",
    "independent_unit": "day",
    "variables": [{"name": "x", "unit": "dimensionless", "initial": 1.0}],
    "parameters": [{"name": "k", "unit": "1/day", "value": 0.2}],
    "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
}


def test_standard_export_contract_is_adapter_safe() -> None:
    sbml = model_export_service({"model_ir": MODEL, "format": "sbml-l3v2"})
    assert sbml["status"] == "PASS"
    assert sbml["validation"]["xml_well_formed"] is True

    cellml = model_export_service({"model_ir": MODEL, "format": "cellml-2.0"})
    assert cellml["status"] == "PASS"
    assert cellml["validation"]["xml_well_formed"] is True

    old_alias = model_export_service({"model_ir": MODEL, "format": "sbml"})
    assert old_alias["status"] == "ADAPTER_REQUIRED"
