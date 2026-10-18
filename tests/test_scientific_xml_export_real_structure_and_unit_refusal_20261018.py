"""Portable scientific XML must be parseable and cannot invent undefined units."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, ParameterSpec, VariableSpec
from axiomize.standards_export import (
    _cellml_unit_name,
    _sid,
    export_cellml_2,
    export_sbml_l3v2,
)


def model(
    *,
    family=ModelFamily.ODE,
    state_init=None,
    parameter_value=None,
    state_unit="metre",
    parameter_unit="1/min",
    independent_unit="second",
):
    return ModelIR(
        name="observed kinetic system",
        domain="physics",
        family=family,
        variables=[VariableSpec("x", initial=state_init, unit=state_unit)],
        parameters=[ParameterSpec("k", value=parameter_value, unit=parameter_unit)],
        equations=[EquationSpec("x", "-k*x", kind="derivative")],
        independent_unit=independent_unit,
    )


def test_generated_sbml_is_wellformed_while_explicitly_disclosing_missing_full_schema_validation():
    out = export_sbml_l3v2(model())
    assert out["status"] == "PASS"
    root = ET.fromstring(out["content"].split("\n", 1)[1])
    assert root.tag.endswith("sbml")
    species = [elem for elem in root.iter() if elem.tag.endswith("species")]
    assert len(species) == 1
    assert "initialConcentration" not in species[0].attrib
    parameters = [elem for elem in root.iter() if elem.tag.endswith("parameter")]
    assert len(parameters) == 1
    assert "value" not in parameters[0].attrib
    assert out["validation"]["schema_validation"] == "NOT_RUN"
    assert "not fabricated" in out["unit_policy"]


def test_explicit_sbml_initial_values_survive_serialization_without_defaulting_to_zero():
    out = export_sbml_l3v2(model(state_init=4.0, parameter_value=2.0))
    assert out["status"] == "PASS"
    root = ET.fromstring(out["content"].split("\n", 1)[1])
    species = [elem for elem in root.iter() if elem.tag.endswith("species")]
    parameter = [elem for elem in root.iter() if elem.tag.endswith("parameter")]
    assert species[0].attrib["initialConcentration"] == "4.0"
    assert parameter[0].attrib["value"] == "2.0"


def test_cellml_unknown_physical_units_are_explicitly_refused_with_original_ir():
    out = export_cellml_2(model(state_unit="unrecognized_unit_2026"))
    assert out["status"] == "ADAPTER_REQUIRED"
    assert "unrecognized_unit_2026" in out["unsupported_units"]
    assert out["portable_ir"]["variables"][0]["unit"] == "unrecognized_unit_2026"


def test_cellml_derivative_equation_uses_mathml_without_fabricating_values():
    out = export_cellml_2(model(state_init=None, parameter_value=None))
    assert out["status"] == "PASS"
    assert out["validation"]["schema_validation"] == "NOT_RUN"
    root = ET.fromstring(out["content"].split("\n", 1)[1])
    variables = [elem for elem in root.iter() if elem.tag.endswith("variable")]
    variable = {v.attrib["name"]: v for v in variables}
    assert "initial_value" not in variable["x"].attrib
    assert "initial_value" not in variable["k"].attrib
    assert any(node.tag.endswith("diff") for node in root.iter())
    assert any(node.tag.endswith("math") for node in root.iter())


def test_cellml_actual_custom_time_unit_uses_correct_scale_not_a_dimensionless_substitute():
    out = export_cellml_2(model(parameter_unit="1/hour", state_unit="metre", state_init=2.0))
    assert out["status"] == "PASS"
    root = ET.fromstring(out["content"].split("\n", 1)[1])
    named = {e.attrib.get("name"): e for e in root.iter() if e.tag.endswith("units")}
    assert "per_hour" in named
    children = [c for c in named["per_hour"] if c.tag.endswith("unit")]
    assert len(children) == 1
    assert children[0].attrib["units"] == "second"
    assert float(children[0].attrib["exponent"]) == -1.0
    assert float(children[0].attrib["multiplier"]) == pytest.approx(1 / 3600)
    state = [e for e in root.iter() if e.tag.endswith("variable") and e.attrib.get("name") == "x"][0]
    assert float(state.attrib["initial_value"]) == 2.0


def test_cellml_aliases_of_same_custom_unit_are_only_emitted_once():
    mod = model(parameter_unit="minute", independent_unit="min")
    out = export_cellml_2(mod)
    assert out["status"] == "PASS"
    root = ET.fromstring(out["content"].split("\n", 1)[1])
    custom = [e for e in root.iter() if e.tag.endswith("units") and e.attrib.get("name") == "minute"]
    assert len(custom) == 1


def test_xml_export_respects_legal_identifiers_and_rejects_empty_arbitrary_names():
    assert _sid("") == "model"
    assert _sid("23-speed") == "_23_speed"
    assert _sid("normal_name") == "normal_name"


@pytest.mark.parametrize(
    ("unit", "expected"),
    [
        ("second", "second"),
        ("seconds", "second"),
        ("min", "minute"),
        ("1/hour", "per_hour"),
        ("unrecognized", None),
    ],
)
def test_cellml_physical_unit_mapping_is_explicit_not_guessed(unit, expected):
    assert _cellml_unit_name(unit) == expected


def test_nonported_advanced_family_has_honest_adapter_required_status():
    for exporter in (export_sbml_l3v2, export_cellml_2):
        out = exporter(model(family=ModelFamily.NETWORK))
        assert out["status"] == "ADAPTER_REQUIRED"
        assert out["portable_ir"]["family"] == "network"
