"""Scientific XML/notebook exports preserve exact version, units and equation semantics."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, ParameterSpec, VariableSpec
from axiomize.standards_export import (
    _cellml_unit_name,
    _sid,
    export_cellml_2,
    export_notebook,
    export_sbml_l3v2,
    export_versioned_standard,
)


def model(*, family=ModelFamily.ODE, unit="dimensionless", kind="derivative", initial=1.0, parameters=None):
    return ModelIR(
        name="clinical model",
        domain="biology",
        family=family,
        independent_unit="second",
        variables=[VariableSpec("state_x", unit=unit, initial=initial)],
        parameters=parameters if parameters is not None else [ParameterSpec("rate", 0.3, unit="1/s")],
        equations=[EquationSpec("state_x", "-rate*state_x", kind=kind)],
        assumptions=["no hidden external sources"],
    )


@pytest.mark.parametrize(
    ("input_value", "expected"),
    [
        ("valid_name", "valid_name"),
        ("3model", "_3model"),
        ("bad name", "bad_name"),
        ("", "model"),
        ("m-a", "m_a"),
    ],
)
def test_standard_entity_ids_are_safe_and_deterministic(input_value, expected):
    assert _sid(input_value) == expected


@pytest.mark.parametrize(
    ("unit", "expected"),
    [
        ("second", "second"),
        ("s", "second"),
        ("minute", "minute"),
        ("min", "minute"),
        ("hour", "hour"),
        ("1/s", "per_second"),
        ("1/min", "per_minute"),
        ("1/day", "per_day"),
        ("dimensionless", "dimensionless"),
        ("not-a-unit", None),
    ],
)
def test_cellml_supported_units_do_not_invent_undeclared_dimensions(unit, expected):
    assert _cellml_unit_name(unit) == expected


def test_sbml_xml_is_wellformed_and_carries_equation_and_source_unit_annotation():
    out = export_sbml_l3v2(model())
    assert out["format"] == "sbml-l3v2"
    assert out["validation"]["xml_well_formed"] is True
    assert out["validation"]["schema_validation"] in {"NOT_RUN", "PASS", "FAIL"}
    root = ET.fromstring(out["content"].split("\n", 1)[1])
    ns = {"s": "http://www.sbml.org/sbml/level3/version2/core"}
    assert root.attrib == {"level": "3", "version": "2"}
    assert len(root.findall(".//s:rateRule", ns)) == 1
    assert len(root.findall(".//s:species", ns)) == 1
    assert "no hidden external sources" in out["content"]


def test_sbml_algebraic_model_contains_algebraic_not_fake_rate_rule():
    m = model(family=ModelFamily.ALGEBRAIC, kind="residual")
    out = export_sbml_l3v2(m)
    assert "algebraicRule" in out["content"]
    assert "rateRule" not in out["content"]


def test_sbml_unsupported_family_returns_adapter_required_not_pseudostandard():
    out = export_sbml_l3v2(model(family=ModelFamily.CAUSAL))
    assert out["status"] == "ADAPTER_REQUIRED"
    assert out["portable_ir"]["family"] == "causal"


def test_cellml_model_preserves_declared_custom_second_inverse_unit():
    out = export_cellml_2(model())
    assert out["status"] == "PASS", out
    assert out["validation"]["xml_well_formed"] is True
    root = ET.fromstring(out["content"].split("\n", 1)[1])
    ns = {"c": "http://www.cellml.org/cellml/2.0#"}
    declared = root.findall("c:units", ns)
    assert any(row.attrib["name"] == "per_second" for row in declared)
    assert "diff" in out["content"]
    assert "state_x" in out["content"]


def test_cellml_unknown_unit_rejected_and_original_ir_retained():
    m = model(unit="fictitious-beans-per-day")
    out = export_cellml_2(m)
    assert out["status"] == "ADAPTER_REQUIRED"
    assert "fictitious-beans-per-day" in out["unsupported_units"]
    assert out["portable_ir"] == m.to_dict()


def test_cellml_algebraic_relation_remains_algebraic():
    out = export_cellml_2(model(family=ModelFamily.ALGEBRAIC, kind="algebraic"))
    assert out["status"] == "PASS"
    assert "state_x" in out["content"]


@pytest.mark.parametrize("family", [ModelFamily.NETWORK, ModelFamily.HYBRID, ModelFamily.CAUSAL])
def test_cellml_unsupported_families_cannot_be_relabelled_as_valid(family):
    out = export_cellml_2(model(family=family))
    assert out["status"] == "ADAPTER_REQUIRED"


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("sbml3v2", "sbml-l3v2"),
        ("sbml-l3-v2", "sbml-l3v2"),
        ("cellml2", "cellml-2.0"),
        ("CellML-2", "cellml-2.0"),
        ("jupyter", "notebook"),
        ("ipynb", "notebook"),
        ("nbformat4", "notebook"),
    ],
)
def test_scientific_format_aliases_have_canonical_identity(alias, expected):
    out = export_versioned_standard(model(), format=alias)
    assert out["format"] == expected


def test_unknown_standard_is_not_claimed_as_successful_conversion():
    assert export_versioned_standard(model(), format="random-standard") is None


def test_rerunnable_notebook_preserves_complete_versioned_ir_not_synthetic_model():
    m = model()
    out = export_notebook(m)
    assert out["status"] == "PASS"
    nb = json.loads(out["content"])
    assert nb["nbformat"] == 4
    assert len(nb["cells"]) == 2
    assert nb["metadata"]["axiomize"]["model_ir_schema_version"] == "1.0"
    source = "".join(nb["cells"][1]["source"])
    assert "ModelIR.from_dict" in source
    assert "simulate_model(model)" in source
    assert "clinical model" in source
