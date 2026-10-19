"""Export real scientific formats, refuse unsupported mappings, preserve evidence."""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET

import pytest

from axiomize import extended_export as export
from axiomize import scientific_stress as stress
from axiomize.model_ir import ModelFamily, ModelIR


def reference(family):
    return stress._models()[family]


@pytest.mark.parametrize("identifier,expected", [
    ("9 model", "_9_model"),
    ("model with spaces", "model_with_spaces"),
    ("", "model"),
    ("valid_identifier", "valid_identifier"),
])
def test_ids_are_conservative_and_deterministic(identifier, expected):
    assert export._id(identifier) == expected


def test_modelica_emits_real_ode_derivatives_and_exact_python_floats():
    model = reference(ModelFamily.ODE)
    result = export.export_modelica(model)
    assert result["status"] == "PASS"
    assert "der(x) = -k*x;" in result["content"]
    assert "parameter Real k = 1.0" in result["content"]
    assert result["validation"]["compiler_validation"] == "NOT_RUN"


def test_modelica_algebraic_constraint_is_equal_to_zero_not_dummy_target():
    result = export.export_modelica(reference(ModelFamily.ALGEBRAIC))
    assert result["status"] == "PASS"
    assert "= 0;" in result["content"]


def test_modelica_keeps_real_dae_equations_not_fake_ode():
    result = export.export_modelica(reference(ModelFamily.DAE))
    assert result["status"] == "PASS"
    assert "der(x)" in result["content"]


def test_unsupported_family_cannot_claim_modelica_standard():
    result = export.export_modelica(reference(ModelFamily.CAUSAL))
    assert result["status"] == "ADAPTER_REQUIRED"
    assert "portable_ir" in result


def test_modelica_undefined_parameter_requires_adapter():
    payload = reference(ModelFamily.ODE).to_dict()
    payload["parameters"][0]["value"] = None
    result = export.export_modelica(ModelIR.from_dict(payload))
    assert result["status"] == "ADAPTER_REQUIRED"
    assert "no concrete value" in result["detail"]


def test_modelica_unmappable_equation_kind_does_not_claim_pass():
    payload = reference(ModelFamily.ODE).to_dict()
    payload["equations"].append(
        {"target": "", "kind": "objective", "expression": "k*x"},
    )
    result = export.export_modelica(ModelIR.from_dict(payload))
    assert result["status"] == "ADAPTER_REQUIRED"
    assert "no conservative Modelica mapping" in result["detail"]


def test_modelica_numeric_exponent_maps_to_modelica_power_syntax():
    assert export._modelica_expr("x**2 + y**0.5") == "x^2 + y^0.5"


def test_real_graphml_produces_well_formed_node_and_edge_xml():
    result = export.export_graphml(reference(ModelFamily.NETWORK))
    assert result["status"] == "PASS"
    xml = ET.fromstring(result["content"])
    ns = "{http://graphml.graphdrawing.org/xmlns}"
    assert len(xml.findall(f".//{ns}node")) == 2
    assert len(xml.findall(f".//{ns}edge")) == 1


def test_graphml_nonnetwork_ir_never_passes():
    result = export.export_graphml(reference(ModelFamily.ODE))
    assert result["status"] == "ADAPTER_REQUIRED"


@pytest.mark.parametrize("bad,pattern", [
    ([], "metadata.network must be an object"),
    ({"nodes": []}, "non-empty network nodes"),
    ({"nodes": ["a"], "edges": [["a", "b"]]}, "unknown node"),
    ({"nodes": ["a"], "edges": [["a"]]}, "needs source and target"),
])
def test_graphml_rejects_invalid_topology_before_emitting_graph(bad, pattern):
    ir = reference(ModelFamily.NETWORK)
    ir.metadata["network"] = bad
    with pytest.raises(ValueError, match=pattern):
        export.export_graphml(ir)


def test_graphml_can_discover_nodes_from_real_directed_edges():
    ir = reference(ModelFamily.NETWORK)
    ir.metadata["network"] = {
        "edges": [{"source": "A", "target": "B"}, ["B", "C"]],
        "directed": True,
    }
    output = export.export_graphml(ir)
    assert output["status"] == "PASS"
    document = ET.fromstring(output["content"])
    namespace = "{http://graphml.graphdrawing.org/xmlns}"
    graph = document.find(f"{namespace}graph")
    assert graph.get("edgedefault") == "directed"
    assert len(document.findall(f".//{namespace}node")) == 3
    assert len(document.findall(f".//{namespace}edge")) == 2


def test_causal_dot_output_uses_explicit_identification_edges():
    ir = reference(ModelFamily.CAUSAL)
    ir.metadata["causal"]["dag_edges"] = [["U", "V"]]
    ir.metadata["causal"]["identification"] = {
        "dag_edges": [{"source": "Treatment", "target": "Outcome"}],
    }
    result = export.export_causal_dot(ir)
    assert result["status"] == "PASS"
    assert "Treatment" in result["content"]
    assert "Outcome" in result["content"]
    assert "U" not in result["content"]


def test_causal_dot_noncausal_ir_never_passes():
    result = export.export_causal_dot(reference(ModelFamily.ODE))
    assert result["status"] == "ADAPTER_REQUIRED"


@pytest.mark.parametrize("edges,pattern", [
    ("not-an-array", "must be an array"),
    ([["Treatment"]], "requires source and target"),
    ([42], "requires source and target"),
])
def test_causal_dot_refuses_unverified_edges(edges, pattern):
    ir = reference(ModelFamily.CAUSAL)
    ir.metadata["causal"]["dag_edges"] = edges
    with pytest.raises(ValueError, match=pattern):
        export.export_causal_dot(ir)


def test_portable_bundle_sha_matches_actual_canonical_ir():
    model = reference(ModelFamily.ODE)
    result = export.export_portable_bundle(model)
    assert result["status"] == "PASS"
    bundle = json.loads(result["content"])
    canonical = json.dumps(
        bundle["model_ir"], sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()
    assert bundle["sha256"] == hashlib.sha256(canonical).hexdigest()
    assert bundle["format"] == "axiomize.portable-bundle.v1"


@pytest.mark.parametrize("format_name,expected", [
    ("mo", "modelica-3.6"),
    ("MODELica", "modelica-3.6"),
    ("graphml", "graphml"),
    ("portable_bundle", "portable-bundle-v1"),
])
def test_export_router_never_relables_formats(format_name, expected):
    family = ModelFamily.NETWORK if expected == "graphml" else ModelFamily.ODE
    assert export.export_extended(reference(family), format=format_name)["format"] == expected


def test_unknown_format_does_not_invent_scientific_export():
    assert export.export_extended(reference(ModelFamily.ODE), format="unsupported") is None
