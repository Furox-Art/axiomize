"""Real SBML/CellML XML, notebook IR reconstruction and explicit adapter limits.

Schema acceptance by libSBML is asserted when available; XML parse success
alone is never reported as full semantic/schema validation.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from axiomize import standards_export
from axiomize.model_ir import ModelFamily, ModelIR
from axiomize.scientific_stress import _models
from axiomize.standards_export import (
    _cellml_unit_name,
    _sid,
    export_cellml_2,
    export_sbml_l3v2,
    export_versioned_standard,
)


def native_model(family=ModelFamily.ODE):
    return _models()[family]


@pytest.mark.parametrize("raw, sanitized", [
    ("one-model", "one_model"), ("1model", "_1model"),
    ("", "model"), ("α model", "__model"),
    ("Valid_name", "Valid_name"),
])
def test_standard_id_is_portable_xml_identifier(raw, sanitized):
    assert _sid(raw) == sanitized


def test_real_sbml_ode_contains_parameters_species_and_explicit_mathml():
    model = native_model()
    result = export_sbml_l3v2(model)
    assert result["status"] == "PASS"
    assert result["format"] == "sbml-l3v2"
    assert result["validation"]["xml_well_formed"] is True
    document = ET.fromstring(result["content"])
    ns = {"sbml": "http://www.sbml.org/sbml/level3/version2/core",
          "math": "http://www.w3.org/1998/Math/MathML"}
    assert document.attrib == {"level": "3", "version": "2"}
    assert document.find(".//sbml:species", ns).attrib["id"] == "x"
    assert document.find(".//sbml:parameter", ns).attrib["id"] == "k"
    assert document.find(".//sbml:rateRule", ns).attrib["variable"] == "x"
    assert document.find(".//math:math", ns) is not None
    assert "unit_policy" in result
    if result["validation"]["schema_validation"] == "PASS":
        assert result["validation"]["libsbml_errors"] == 0
    else:
        assert result["validation"]["schema_validation"] == "NOT_RUN"


def test_sbml_rejects_unsupported_family_without_fabricating_semantics():
    output = export_sbml_l3v2(native_model(ModelFamily.NETWORK))
    assert output["status"] == "ADAPTER_REQUIRED"
    assert output["portable_ir"]["family"] == "network"
    assert "content" not in output


def test_algebraic_sbml_emits_algebraic_rule_not_rate_rule():
    out = export_sbml_l3v2(native_model(ModelFamily.ALGEBRAIC))
    root = ET.fromstring(out["content"])
    names = [element.tag.split("}")[-1] for element in root.iter()]
    assert "algebraicRule" in names
    assert "rateRule" not in names


@pytest.mark.parametrize("input_unit, expected", [
    ("dimensionless", "dimensionless"), ("1", "dimensionless"),
    ("m", "metre"), ("s", "second"), ("DAY", "day"),
    ("1/day", "per_day"), ("hour", "hour"),
    ("1/hour", "per_hour"), ("invented-unit", None),
])
def test_cellml_units_mapping_preserves_declared_physical_units(input_unit, expected):
    assert _cellml_unit_name(input_unit) == expected


def test_real_cellml_ode_has_2_0_namespace_and_mathml_derivative():
    output = export_cellml_2(native_model())
    assert output["status"] == "PASS"
    root = ET.fromstring(output["content"])
    assert root.tag == "{http://www.cellml.org/cellml/2.0#}model"
    assert output["validation"]["xml_well_formed"] is True
    assert output["validation"]["schema_validation"] == "NOT_RUN"
    assert any(x.tag.endswith("}diff") for x in root.iter())
    assert any(x.tag.endswith("}variable") and x.attrib.get("name") == "x"
               for x in root.iter())


def test_cellml_algebraic_export_preserves_equation_structure():
    output = export_cellml_2(native_model(ModelFamily.ALGEBRAIC))
    assert output["status"] == "PASS"
    root = ET.fromstring(output["content"])
    assert any(x.tag.endswith("}eq") for x in root.iter())


def test_cellml_unsupported_family_keeps_ir():
    output = export_cellml_2(native_model(ModelFamily.BAYESIAN))
    assert output["status"] == "ADAPTER_REQUIRED"
    assert output["portable_ir"]["family"] == "bayesian"


def test_unknown_units_are_not_reinterpreted_as_dimensionless():
    payload = native_model().to_dict()
    payload["variables"][0]["unit"] = "unknown_biology_unit"
    out = export_cellml_2(ModelIR.from_dict(payload))
    assert out["status"] == "ADAPTER_REQUIRED"
    assert out["unsupported_units"] == ["unknown_biology_unit"]
    assert out["portable_ir"]["variables"][0]["unit"] == "unknown_biology_unit"


def test_real_notebook_reconstructs_the_same_versioned_model_ir():
    model = native_model()
    result = standards_export.export_notebook(model)
    assert result["status"] == "PASS"
    artifact = json.loads(result["content"])
    assert artifact["nbformat"] == 4
    assert artifact["nbformat_minor"] == 5
    assert artifact["metadata"]["axiomize"]["model_ir_schema_version"] == "1.0"
    source = "".join(artifact["cells"][1]["source"])
    assert "ModelIR.from_dict" in source
    assert "simulate_model" in source
    assert "eval(" not in source
    assert model.to_dict()["name"] == json.loads(result["content"])["cells"][0]["source"][0].split("# ")[1].strip()


@pytest.mark.parametrize("format_name, canonical", [
    ("sbml-l3v2", "sbml-l3v2"), ("SBML3V2", "sbml-l3v2"),
    ("sbml_l3_v2", "sbml-l3v2"),
    ("cellml2", "cellml-2.0"), ("cellml-2", "cellml-2.0"),
    ("JUPYTER", "notebook"), ("ipynb", "notebook"), ("nbformat4", "notebook"),
])
def test_format_router_normalizes_alias_without_inventing_format(format_name, canonical):
    out = export_versioned_standard(native_model(), format=format_name)
    assert out is not None
    assert out["format"] == canonical


def test_format_router_returns_none_for_unsupported_protocol():
    assert export_versioned_standard(native_model(), format="invented-scientific-standard") is None



def test_cellml_custom_units_have_explicit_dimensions_and_correct_conversion_factors():
    payload = native_model().to_dict()
    payload["independent_unit"] = "day"
    payload["variables"][0]["unit"] = "minute"
    payload["parameters"][0]["unit"] = "1/s"
    extra = dict(payload["parameters"][0])
    extra.update({"name": "second_rate", "unit": "1/day", "value": None})
    payload["parameters"].append(extra)
    artifact = export_cellml_2(ModelIR.from_dict(payload))
    assert artifact["status"] == "PASS"
    root = ET.fromstring(artifact["content"])
    units = {
        element.attrib["name"]: element.find("{http://www.cellml.org/cellml/2.0#}unit")
        for element in root.iter()
        if element.tag.endswith("}units")
    }
    assert float(units["day"].attrib["multiplier"]) == 86400.0
    assert float(units["minute"].attrib["multiplier"]) == 60.0
    assert float(units["per_day"].attrib["exponent"]) == -1.0
    assert float(units["per_second"].attrib["exponent"]) == -1.0
    assert "multiplier" not in units["per_second"].attrib
    assert "initial_value" not in next(
        element.attrib for element in root.iter()
        if element.tag.endswith("}variable") and element.attrib.get("name") == "second_rate"
    )


def test_absent_optional_sbml_validator_does_not_claim_schema_pass(monkeypatch):
    import builtins

    original_import = builtins.__import__

    def refuse_libsbml(name, *args, **kwargs):
        if name == "libsbml":
            raise ImportError("optional native SBML validator not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse_libsbml)
    output = export_sbml_l3v2(native_model())
    assert output["status"] == "PASS"
    assert output["validation"]["schema_validation"] == "NOT_RUN"
    assert output["validation"]["xml_well_formed"] is True


def test_reported_sbml_schema_failure_is_not_rewritten_as_pass(monkeypatch):
    import sys
    from types import SimpleNamespace

    class DeliberatelyFailingDocument:
        def getNumErrors(self):
            return 2

        def getError(self, index):
            return SimpleNamespace(getMessage=lambda: f"injected schema error {index}")

    failing_validator = SimpleNamespace(readSBMLFromString=lambda content: DeliberatelyFailingDocument())
    monkeypatch.setitem(sys.modules, "libsbml", failing_validator)
    output = export_sbml_l3v2(native_model())
    assert output["status"] == "FAIL"
    assert output["validation"]["schema_validation"] == "FAIL"
    assert output["validation"]["libsbml_errors"] == 2
    assert len(output["validation"]["messages"]) == 2
