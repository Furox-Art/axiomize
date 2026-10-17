"""Interoperability exporters emit declared standards or explicit adapter gaps."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET

import pytest

from axiomize.extended_export import (
    export_causal_dot,
    export_extended,
    export_graphml,
    export_modelica,
    export_portable_bundle,
)
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, ParameterSpec, VariableSpec


def model(family=ModelFamily.ODE, *, metadata=None, equations=None, parameters=None, name="physics"):
    return ModelIR(
        name=name,
        domain="physics",
        family=family,
        variables=[VariableSpec("x", initial=1.0)],
        parameters=parameters if parameters is not None else [ParameterSpec("rate", 0.3)],
        equations=equations if equations is not None else [EquationSpec("x", "-rate*x")],
        metadata=metadata or {},
    )


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("modelica", "modelica-3.6"),
        ("mo", "modelica-3.6"),
        ("graphml", "graphml"),
        ("DOT", "causal-dot"),
        ("dag_dot", "causal-dot"),
        ("bundle", "portable-bundle-v1"),
        ("portable-bundle", "portable-bundle-v1"),
    ],
)
def test_format_aliases_never_rename_unrelated_model_formats(alias, expected):
    family = (
        ModelFamily.NETWORK
        if expected == "graphml"
        else ModelFamily.CAUSAL
        if expected == "causal-dot"
        else ModelFamily.ODE
    )
    cfg = {"network": {"nodes": ["a", "b"], "edges": [["a", "b"]]}} if family == ModelFamily.NETWORK else {}
    out = export_extended(model(family, metadata=cfg), format=alias)
    assert out["format"] == expected


def test_unknown_format_is_not_labeled_as_successful_scientific_export():
    assert export_extended(model(), format="imaginary-standard") is None


def test_modelica_ode_matches_differential_equation_and_declared_values():
    out = export_modelica(model(name="3 bad-name"))
    assert out["status"] == "PASS"
    assert "model _3_bad_name" in out["content"]
    assert "der(x) = -rate*x;" in out["content"]
    assert "parameter Real rate = 0.3;" in out["content"]
    assert out["validation"]["compiler_validation"] == "NOT_RUN"


def test_modelica_power_operator_and_algebraic_relations_are_valid_text():
    equations = [EquationSpec("x", "x**2", "algebraic")]
    out = export_modelica(model(ModelFamily.ALGEBRAIC, equations=equations))
    assert out["status"] == "PASS"
    assert "x = x^2;" in out["content"]


@pytest.mark.parametrize(
    "variant",
    [
        model(ModelFamily.CAUSAL),
        model(ModelFamily.ODE, parameters=[ParameterSpec("rate", None)]),
        model(ModelFamily.ODE, equations=[EquationSpec("", "x**2", "objective")]),
    ],
)
def test_modelica_unsupported_semantics_are_flagged_as_adapter_required(variant):
    out = export_modelica(variant)
    assert out["status"] == "ADAPTER_REQUIRED"
    assert out["portable_ir"] == variant.to_dict()


@pytest.mark.parametrize(
    ("cfg", "pattern"),
    [
        ({"network": []}, "metadata.network"),
        ({"network": {"nodes": []}}, "non-empty network nodes"),
        ({"network": {"nodes": ["a"], "edges": [["a"]]}}, "source and target"),
        ({"network": {"nodes": ["a"], "edges": [["a", "b"]]}}, "unknown node"),
    ],
)
def test_graphml_rejects_dangling_or_underspecified_graph(cfg, pattern):
    with pytest.raises(ValueError, match=pattern):
        export_graphml(model(ModelFamily.NETWORK, metadata=cfg))


def test_graphml_roundtrip_is_wellformed_and_keeps_directed_adjacency():
    cfg = {"network": {"directed": True, "nodes": ["a", "b"], "edges": [{"source": "a", "target": "b"}]}}
    out = export_graphml(model(ModelFamily.NETWORK, metadata=cfg))
    assert out["status"] == "PASS"
    root = ET.fromstring(out["content"])
    ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
    graph = root.find("g:graph", ns)
    assert graph.attrib["edgedefault"] == "directed"
    assert len(graph.findall("g:node", ns)) == 2
    edges = graph.findall("g:edge", ns)
    assert len(edges) == 1
    assert edges[0].attrib["source"] == "a"
    assert edges[0].attrib["target"] == "b"


def test_graphml_derives_nodes_from_edges_only_when_explicit_nodes_absent():
    cfg = {"network": {"edges": [["a", "b"], ["b", "c"]]}}
    out = export_graphml(model(ModelFamily.NETWORK, metadata=cfg))
    assert out["status"] == "PASS"
    root = ET.fromstring(out["content"])
    assert len(root.findall(".//{http://graphml.graphdrawing.org/xmlns}node")) == 3


@pytest.mark.parametrize(
    ("cfg", "pattern"),
    [
        ({"causal": {"dag_edges": "not-array"}}, "edges must be an array"),
        ({"causal": {"dag_edges": [["a"]]}}, "requires source and target"),
    ],
)
def test_causal_graph_export_requires_actual_dag_edges(cfg, pattern):
    with pytest.raises(ValueError, match=pattern):
        export_causal_dot(model(ModelFamily.CAUSAL, metadata=cfg))


def test_causal_dot_reports_recorded_edges_not_inferred_causes():
    cfg = {"causal": {"identification": {"dag_edges": [{"source": "z", "target": "t"}, ["t", "y"]]}}}
    out = export_causal_dot(model(ModelFamily.CAUSAL, metadata=cfg))
    assert out["status"] == "PASS"
    assert '"z" -> "t";' in out["content"]
    assert '"t" -> "y";' in out["content"]


def test_portable_bundle_hash_is_reproducible_and_matches_bytes():
    m = model()
    out = export_portable_bundle(m)
    assert out["status"] == "PASS"
    payload = m.to_dict()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    assert out["bundle"]["sha256"] == hashlib.sha256(canonical).hexdigest()
    assert json.loads(out["content"]) == out["bundle"]
    assert export_portable_bundle(m)["bundle"] == out["bundle"]
