from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from axiomize.application.general_services import model_export_service
from axiomize.general_engine import export_model
from axiomize.model_ir import ModelIR


def _decay() -> ModelIR:
    return ModelIR.from_dict({
        "schema_version": "1.0",
        "name": "decay",
        "domain": "physics",
        "family": "ode",
        "independent_variable": "t",
        "independent_unit": "day",
        "variables": [
            {"name": "x", "unit": "dimensionless", "initial": 1.0},
        ],
        "parameters": [
            {"name": "k", "unit": "1/day", "value": 0.5},
        ],
        "equations": [
            {"target": "x", "expression": "-k*x", "kind": "derivative"},
        ],
        "assumptions": ["first-order decay"],
    })


def test_explicit_sbml_l3v2_export_is_well_formed_and_versioned() -> None:
    out = export_model(_decay(), format="sbml-l3v2")
    assert out["status"] == "PASS"
    assert out["standard"] == "SBML Level 3 Version 2 Core"
    root = ET.fromstring(out["content"].split("\n", 1)[1])
    assert root.tag.endswith("}sbml")
    assert root.attrib["level"] == "3"
    assert root.attrib["version"] == "2"
    assert out["validation"]["xml_well_formed"] is True


def test_explicit_cellml_2_export_preserves_supported_units() -> None:
    out = export_model(_decay(), format="cellml-2.0")
    assert out["status"] == "PASS"
    assert out["standard"] == "CellML 2.0"
    root = ET.fromstring(out["content"].split("\n", 1)[1])
    assert root.tag.endswith("}model")
    assert "per_day" in out["content"]
    assert "day" in out["content"]


def test_cellml_refuses_to_guess_unknown_units() -> None:
    model = _decay()
    model.variables[0] = type(model.variables[0])(
        name="x", unit="mystery_unit", role="state", initial=1.0,
        bounds=None, description="",
    )
    out = export_model(model, format="cellml-2.0")
    assert out["status"] == "ADAPTER_REQUIRED"
    assert out["unsupported_units"] == ["mystery_unit"]


def test_notebook_export_is_valid_nbformat_4_json() -> None:
    out = export_model(_decay(), format="ipynb")
    assert out["status"] == "PASS"
    notebook = json.loads(out["content"])
    assert notebook["nbformat"] == 4
    assert notebook["metadata"]["axiomize"]["schema_version"] == "1.0"
    assert any(cell["cell_type"] == "code" for cell in notebook["cells"])


def test_unversioned_standard_alias_remains_conservative() -> None:
    out = export_model(_decay(), format="sbml")
    assert out["status"] == "ADAPTER_REQUIRED"


def test_export_service_exposes_versioned_standard_adapter() -> None:
    out = model_export_service({
        "model_ir": _decay().to_dict(),
        "format": "sbml-l3v2",
    })
    assert out["status"] == "PASS"
    assert out["format"] == "sbml-l3v2"
