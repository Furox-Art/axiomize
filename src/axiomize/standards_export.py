"""Versioned portable export adapters for Model IR.

The generic JSON/Python/YAML exporters live in ``general_engine_core``. This
module adds explicit-version scientific exchange formats rather than emitting
ambiguous pseudo-standard XML. The adapters intentionally support a conservative
subset and report validation limitations in-band.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Any

import sympy as sp

from axiomize.model_ir import ModelFamily, ModelIR
from axiomize.safe_expression import sympy_expression as _sympy_expression

_MATHML_NS = "http://www.w3.org/1998/Math/MathML"
_SBML_NS = "http://www.sbml.org/sbml/level3/version2/core"
_CELLML_NS = "http://www.cellml.org/cellml/2.0#"
_AXIOMIZE_NS = "https://github.com/Furox-Art/axiomize/model-ir"


def _sid(value: str) -> str:
    out = re.sub(r"[^A-Za-z0-9_]", "_", str(value))
    if not out:
        out = "model"
    if out[0].isdigit():
        out = f"_{out}"
    return out


def _symbols(model: ModelIR) -> dict[str, Any]:
    names = [v.name for v in model.variables]
    names.extend(p.name for p in model.parameters)
    names.append(model.independent_variable)
    return {name: sp.Symbol(name, real=True) for name in names}


def _math_element(expression: str, symbols: dict[str, Any]) -> ET.Element:
    expr = _sympy_expression(expression, symbols)
    body = sp.printing.mathml(expr, printer="content")
    return ET.fromstring(f'<math xmlns="{_MATHML_NS}">{body}</math>')


def _xml_text(root: ET.Element) -> str:
    try:
        ET.indent(root, space="  ")
    except AttributeError:  # pragma: no cover - Python >=3.10 in supported CI
        pass
    text = ET.tostring(root, encoding="unicode", xml_declaration=False)
    ET.fromstring(text)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + text


def _annotation(parent: ET.Element, model: ModelIR) -> None:
    annotation = ET.SubElement(parent, f"{{{_SBML_NS}}}annotation")
    payload = ET.SubElement(annotation, f"{{{_AXIOMIZE_NS}}}modelIR")
    payload.set("schemaVersion", model.schema_version)
    payload.text = json.dumps(
        {
            "domain": model.domain,
            "independent_variable": model.independent_variable,
            "independent_unit": model.independent_unit,
            "variable_units": {v.name: v.unit for v in model.variables},
            "parameter_units": {p.name: p.unit for p in model.parameters},
            "assumptions": list(model.assumptions),
        },
        sort_keys=True,
    )


def export_sbml_l3v2(model: ModelIR) -> dict[str, Any]:
    """Export the supported ODE/algebraic Model IR subset as SBML L3V2 Core."""
    if model.family not in {ModelFamily.ODE, ModelFamily.ALGEBRAIC}:
        return {
            "status": "ADAPTER_REQUIRED",
            "format": "sbml-l3v2",
            "detail": "native SBML L3V2 export currently supports ODE and algebraic Model IR families",
            "portable_ir": model.to_dict(),
        }

    ET.register_namespace("", _SBML_NS)
    ET.register_namespace("axiomize", _AXIOMIZE_NS)
    root = ET.Element(f"{{{_SBML_NS}}}sbml", {"level": "3", "version": "2"})
    sbml_model = ET.SubElement(root, f"{{{_SBML_NS}}}model", {"id": _sid(model.name), "name": model.name})
    _annotation(sbml_model, model)

    compartments = ET.SubElement(sbml_model, f"{{{_SBML_NS}}}listOfCompartments")
    ET.SubElement(compartments, f"{{{_SBML_NS}}}compartment",
                  {"id": "default_compartment", "constant": "true", "size": "1"})

    variable_ids = {v.name: _sid(v.name) for v in model.variables}
    parameter_ids = {p.name: _sid(p.name) for p in model.parameters}

    species_list = ET.SubElement(sbml_model, f"{{{_SBML_NS}}}listOfSpecies")
    for variable in model.variables:
        attrs = {
            "id": variable_ids[variable.name], "name": variable.name,
            "compartment": "default_compartment", "hasOnlySubstanceUnits": "false",
            "boundaryCondition": "false", "constant": "false",
        }
        if variable.initial is not None:
            attrs["initialConcentration"] = repr(float(variable.initial))
        ET.SubElement(species_list, f"{{{_SBML_NS}}}species", attrs)

    if model.parameters:
        parameter_list = ET.SubElement(sbml_model, f"{{{_SBML_NS}}}listOfParameters")
        for parameter in model.parameters:
            attrs = {"id": parameter_ids[parameter.name], "name": parameter.name, "constant": "true"}
            if parameter.value is not None:
                attrs["value"] = repr(float(parameter.value))
            ET.SubElement(parameter_list, f"{{{_SBML_NS}}}parameter", attrs)

    rules = ET.SubElement(sbml_model, f"{{{_SBML_NS}}}listOfRules")
    symbols = _symbols(model)
    for equation in model.equations:
        if model.family == ModelFamily.ODE and equation.kind == "derivative":
            rule = ET.SubElement(rules, f"{{{_SBML_NS}}}rateRule",
                                 {"variable": variable_ids.get(equation.target, _sid(equation.target))})
            rule.append(_math_element(equation.expression, symbols))
        else:
            residual = equation.expression if equation.kind == "residual" else f"({equation.target})-({equation.expression})"
            rule = ET.SubElement(rules, f"{{{_SBML_NS}}}algebraicRule")
            rule.append(_math_element(residual, symbols))

    content = _xml_text(root)
    validation: dict[str, Any] = {
        "xml_well_formed": True,
        "schema_validation": "NOT_RUN",
        "detail": "XML structure was validated locally; install python-libsbml to perform full SBML semantic/schema validation",
    }
    try:
        import libsbml  # type: ignore

        document = libsbml.readSBMLFromString(content)
        errors = int(document.getNumErrors())
        validation = {"xml_well_formed": True, "schema_validation": "PASS" if errors == 0 else "FAIL",
                      "libsbml_errors": errors}
        if errors:
            validation["messages"] = [str(document.getError(i).getMessage()) for i in range(min(errors, 20))]
    except ImportError:
        pass

    return {
        "status": "PASS" if validation.get("schema_validation") != "FAIL" else "FAIL",
        "format": "sbml-l3v2", "standard": "SBML Level 3 Version 2 Core", "content": content,
        "validation": validation,
        "unit_policy": "original Model IR units are preserved in the axiomize annotation; unsupported free-form units are not fabricated as SBML unit definitions",
    }


_CELLML_BUILTIN = {
    "dimensionless": "dimensionless", "1": "dimensionless", "s": "second", "sec": "second",
    "second": "second", "seconds": "second", "m": "metre", "metre": "metre", "meter": "metre",
    "kg": "kilogram", "kilogram": "kilogram", "mol": "mole", "mole": "mole", "a": "ampere",
    "ampere": "ampere", "k": "kelvin", "kelvin": "kelvin",
}
_CELLML_CUSTOM = {
    "minute": ("minute", "second", 1.0, 60.0), "min": ("minute", "second", 1.0, 60.0),
    "hour": ("hour", "second", 1.0, 3600.0), "h": ("hour", "second", 1.0, 3600.0),
    "day": ("day", "second", 1.0, 86400.0), "1/s": ("per_second", "second", -1.0, 1.0),
    "1/second": ("per_second", "second", -1.0, 1.0),
    "1/min": ("per_minute", "second", -1.0, 1.0 / 60.0),
    "1/minute": ("per_minute", "second", -1.0, 1.0 / 60.0),
    "1/h": ("per_hour", "second", -1.0, 1.0 / 3600.0),
    "1/hour": ("per_hour", "second", -1.0, 1.0 / 3600.0),
    "1/day": ("per_day", "second", -1.0, 1.0 / 86400.0),
}


def _cellml_unit_name(unit: str) -> str | None:
    key = str(unit).strip().lower()
    if key in _CELLML_BUILTIN:
        return _CELLML_BUILTIN[key]
    if key in _CELLML_CUSTOM:
        return _CELLML_CUSTOM[key][0]
    return None


def export_cellml_2(model: ModelIR) -> dict[str, Any]:
    """Export the supported ODE/algebraic subset as explicit CellML 2.0 XML."""
    if model.family not in {ModelFamily.ODE, ModelFamily.ALGEBRAIC}:
        return {"status": "ADAPTER_REQUIRED", "format": "cellml-2.0",
                "detail": "native CellML 2.0 export currently supports ODE and algebraic Model IR families",
                "portable_ir": model.to_dict()}

    units = [model.independent_unit]
    units.extend(v.unit for v in model.variables)
    units.extend(p.unit for p in model.parameters)
    unsupported = sorted({u for u in units if _cellml_unit_name(u) is None})
    if unsupported:
        return {"status": "ADAPTER_REQUIRED", "format": "cellml-2.0",
                "detail": "CellML export will not silently reinterpret unknown units",
                "unsupported_units": unsupported, "portable_ir": model.to_dict()}

    ET.register_namespace("", _CELLML_NS)
    ET.register_namespace("m", _MATHML_NS)
    root = ET.Element(f"{{{_CELLML_NS}}}model", {"name": _sid(model.name)})

    needed_custom = {str(u).strip().lower() for u in units if str(u).strip().lower() in _CELLML_CUSTOM}
    emitted: set[str] = set()
    for key in sorted(needed_custom):
        name, base, exponent, multiplier = _CELLML_CUSTOM[key]
        if name in emitted:
            continue
        emitted.add(name)
        units_node = ET.SubElement(root, f"{{{_CELLML_NS}}}units", {"name": name})
        attrs = {"units": base}
        if exponent != 1.0:
            attrs["exponent"] = repr(float(exponent))
        if multiplier != 1.0:
            attrs["multiplier"] = repr(float(multiplier))
        ET.SubElement(units_node, f"{{{_CELLML_NS}}}unit", attrs)

    component = ET.SubElement(root, f"{{{_CELLML_NS}}}component", {"name": "model"})
    independent = _sid(model.independent_variable)
    ET.SubElement(component, f"{{{_CELLML_NS}}}variable",
                  {"name": independent, "units": str(_cellml_unit_name(model.independent_unit))})

    for variable in model.variables:
        attrs = {"name": _sid(variable.name), "units": str(_cellml_unit_name(variable.unit))}
        if variable.initial is not None:
            attrs["initial_value"] = repr(float(variable.initial))
        ET.SubElement(component, f"{{{_CELLML_NS}}}variable", attrs)
    for parameter in model.parameters:
        attrs = {"name": _sid(parameter.name), "units": str(_cellml_unit_name(parameter.unit))}
        if parameter.value is not None:
            attrs["initial_value"] = repr(float(parameter.value))
        ET.SubElement(component, f"{{{_CELLML_NS}}}variable", attrs)

    math = ET.SubElement(component, f"{{{_MATHML_NS}}}math")
    symbols = _symbols(model)
    for equation in model.equations:
        apply_eq = ET.SubElement(math, f"{{{_MATHML_NS}}}apply")
        ET.SubElement(apply_eq, f"{{{_MATHML_NS}}}eq")
        if model.family == ModelFamily.ODE and equation.kind == "derivative":
            diff_apply = ET.SubElement(apply_eq, f"{{{_MATHML_NS}}}apply")
            ET.SubElement(diff_apply, f"{{{_MATHML_NS}}}diff")
            bvar = ET.SubElement(diff_apply, f"{{{_MATHML_NS}}}bvar")
            ci_t = ET.SubElement(bvar, f"{{{_MATHML_NS}}}ci"); ci_t.text = independent
            ci_state = ET.SubElement(diff_apply, f"{{{_MATHML_NS}}}ci"); ci_state.text = _sid(equation.target)
            rhs = _math_element(equation.expression, symbols)
            for child in list(rhs):
                apply_eq.append(child)
        else:
            ci = ET.SubElement(apply_eq, f"{{{_MATHML_NS}}}ci"); ci.text = _sid(equation.target)
            rhs = _math_element(equation.expression, symbols)
            for child in list(rhs):
                apply_eq.append(child)

    content = _xml_text(root)
    return {"status": "PASS", "format": "cellml-2.0", "standard": "CellML 2.0", "content": content,
            "validation": {"xml_well_formed": True, "schema_validation": "NOT_RUN",
                           "detail": "export is restricted to a conservative CellML 2.0 ODE/algebraic subset; full libCellML validation is not bundled"}}


def export_notebook(model: ModelIR) -> dict[str, Any]:
    """Emit a rerunnable nbformat-4 notebook without requiring nbformat itself."""
    payload = model.to_dict()
    model_json = json.dumps(payload, sort_keys=True)
    source = [
        "import json\n",
        "from axiomize.model_ir import ModelIR\n",
        "from axiomize.general_engine import simulate_model\n",
        f"MODEL = json.loads({model_json!r})\n",
        "model = ModelIR.from_dict(MODEL)\n",
        "result = simulate_model(model)\n",
        "result\n",
    ]
    notebook = {
        "cells": [
            {"cell_type": "markdown", "metadata": {},
             "source": [f"# {model.name}\n", "Generated by Axiomize from a versioned Model IR.\n"]},
            {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source},
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                     "language_info": {"name": "python"},
                     "axiomize": {"model_ir_schema_version": model.schema_version}},
        "nbformat": 4, "nbformat_minor": 5,
    }
    return {"status": "PASS", "format": "notebook", "content": json.dumps(notebook, indent=2),
            "notebook": notebook, "detail": "rerunnable notebook reconstructs the exact versioned Model IR"}


def export_versioned_standard(model: ModelIR, *, format: str) -> dict[str, Any] | None:
    normalized = str(format).strip().lower().replace("_", "-")
    if normalized in {"sbml-l3v2", "sbml-l3-v2", "sbml3v2"}:
        return export_sbml_l3v2(model)
    if normalized in {"cellml-2.0", "cellml2", "cellml-2"}:
        return export_cellml_2(model)
    if normalized in {"notebook", "jupyter", "ipynb", "nbformat4"}:
        return export_notebook(model)
    return None
