"""Extended portable exports for Axiomize 1.12.

These adapters are conservative: they either emit a real format for a supported
Model IR subset or return ADAPTER_REQUIRED. They never relabel arbitrary JSON as
a scientific standard.
"""
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from typing import Any

from axiomize.model_ir import ModelFamily, ModelIR


def _id(value:str)->str:
    out=re.sub(r"[^A-Za-z0-9_]","_",str(value)) or "model"
    return "_"+out if out[0].isdigit() else out


def _modelica_expr(expr:str)->str:
    # Model IR parser already restricts expression syntax. Modelica uses ^ for powers.
    return str(expr).replace("**","^")


def export_modelica(model:ModelIR)->dict[str,Any]:
    if model.family not in {ModelFamily.ODE,ModelFamily.ALGEBRAIC,ModelFamily.DAE}:
        return {"status":"ADAPTER_REQUIRED","format":"modelica-3.6","detail":"Modelica export currently supports ODE, DAE and algebraic Model IR","portable_ir":model.to_dict()}
    name=_id(model.name); lines=[f"model {name}","  // Generated from Axiomize Model IR"]
    for p in model.parameters:
        if p.value is None:return {"status":"ADAPTER_REQUIRED","format":"modelica-3.6","detail":f"parameter {p.name} has no concrete value","portable_ir":model.to_dict()}
        lines.append(f"  parameter Real {_id(p.name)} = {float(p.value)!r};")
    for v in model.variables:
        init=f"(start={float(v.initial)!r})" if v.initial is not None else ""
        lines.append(f"  Real {_id(v.name)}{init};")
    lines.append("equation")
    for e in model.equations:
        target=_id(e.target) if e.target else ""
        rhs=_modelica_expr(e.expression)
        if e.kind=="derivative": lines.append(f"  der({target}) = {rhs};")
        elif e.kind in {"algebraic","constraint","residual"}:
            lines.append(f"  {target + ' = ' if target else ''}{rhs}{';' if target else ' = 0;'}")
        else:return {"status":"ADAPTER_REQUIRED","format":"modelica-3.6","detail":f"equation kind {e.kind!r} has no conservative Modelica mapping","portable_ir":model.to_dict()}
    lines.extend([f"end {name};",""])
    return {"status":"PASS","format":"modelica-3.6","standard":"Modelica 3.6 textual model","content":"\n".join(lines),"validation":{"syntax_generation":"PASS","compiler_validation":"NOT_RUN"}}


def export_graphml(model:ModelIR)->dict[str,Any]:
    if model.family!=ModelFamily.NETWORK:return {"status":"ADAPTER_REQUIRED","format":"graphml","detail":"GraphML export requires network Model IR","portable_ir":model.to_dict()}
    cfg=model.metadata.get("network",{})
    if not isinstance(cfg,dict):raise ValueError("metadata.network must be an object")
    nodes=cfg.get("nodes"); edges=cfg.get("edges",[])
    if nodes is None:
        discovered=[]
        for edge in edges:
            vals=[edge.get("source"),edge.get("target")] if isinstance(edge,dict) else list(edge[:2])
            for node in vals:
                if node not in discovered:discovered.append(node)
        nodes=discovered
    if not isinstance(nodes,list) or not nodes:raise ValueError("GraphML export requires non-empty network nodes")
    graphml="http://graphml.graphdrawing.org/xmlns"; ET.register_namespace("",graphml)
    root=ET.Element(f"{{{graphml}}}graphml"); graph=ET.SubElement(root,f"{{{graphml}}}graph",{"id":_id(model.name),"edgedefault":"directed" if cfg.get("directed") else "undirected"})
    known={str(n) for n in nodes}
    for n in nodes:ET.SubElement(graph,f"{{{graphml}}}node",{"id":_id(str(n))})
    for i,edge in enumerate(edges):
        if isinstance(edge,dict):s,t=edge.get("source"),edge.get("target")
        else:
            values=list(edge)
            if len(values)<2:raise ValueError("network edge needs source and target")
            s,t=values[:2]
        if str(s) not in known or str(t) not in known:raise ValueError("network edge references unknown node")
        ET.SubElement(graph,f"{{{graphml}}}edge",{"id":f"e{i}","source":_id(str(s)),"target":_id(str(t))})
    content=ET.tostring(root,encoding="unicode"); ET.fromstring(content)
    return {"status":"PASS","format":"graphml","standard":"GraphML","content":content,"validation":{"xml_well_formed":True}}


def export_causal_dot(model:ModelIR)->dict[str,Any]:
    if model.family!=ModelFamily.CAUSAL:return {"status":"ADAPTER_REQUIRED","format":"causal-dot","detail":"causal DOT export requires causal Model IR","portable_ir":model.to_dict()}
    cfg=model.metadata.get("causal",{}); identification=cfg.get("identification",{}) if isinstance(cfg,dict) else {}
    edges=(identification.get("dag_edges") if isinstance(identification,dict) else None) or (cfg.get("dag_edges",cfg.get("dag",[])) if isinstance(cfg,dict) else [])
    if not isinstance(edges,list):raise ValueError("causal DAG edges must be an array")
    lines=[f"digraph {_id(model.name)} {{"]
    for raw in edges:
        if isinstance(raw,dict):a,b=raw.get("source"),raw.get("target")
        elif isinstance(raw,(list,tuple)) and len(raw)==2:a,b=raw
        else:raise ValueError("causal DAG edge requires source and target")
        lines.append(f'  "{str(a).replace(chr(34), chr(39))}" -> "{str(b).replace(chr(34), chr(39))}";')
    lines.append("}")
    return {"status":"PASS","format":"causal-dot","standard":"Graphviz DOT","content":"\n".join(lines)}


def export_portable_bundle(model:ModelIR)->dict[str,Any]:
    payload=model.to_dict(); canonical=json.dumps(payload,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    manifest={"format":"axiomize.portable-bundle.v1","model_ir_schema_version":model.schema_version,"sha256":hashlib.sha256(canonical).hexdigest(),
              "model_ir":payload,"assumptions":list(model.assumptions),"provenance":[{"action":e.action,"detail":e.detail} for e in model.provenance]}
    return {"status":"PASS","format":"portable-bundle-v1","content":json.dumps(manifest,indent=2,sort_keys=True),"bundle":manifest}


def export_extended(model:ModelIR,*,format:str)->dict[str,Any]|None:
    normalized=str(format).strip().lower().replace("_","-")
    if normalized in {"modelica","modelica-3.6","mo"}:return export_modelica(model)
    if normalized in {"graphml"}:return export_graphml(model)
    if normalized in {"causal-dot","dot","dag-dot"}:return export_causal_dot(model)
    if normalized in {"portable-bundle","portable-bundle-v1","bundle"}:return export_portable_bundle(model)
    return None
