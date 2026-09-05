"""Bounded end-to-end scientific stress matrix for the installed Axiomize wheel.

The matrix covers every ModelFamily with a real native execution and adds
adversarial/verification/export checks. It is deterministic, small enough for CI,
and carries explicit runtime budgets so it cannot become an open-ended workload.
"""
from __future__ import annotations

import math
import time
from typing import Any, Callable

import numpy as np

from axiomize.general_engine import export_model, numerical_refinement, simulate_model
from axiomize.model_ir import ModelFamily, ModelIR

_CASE_BUDGET_S = 30.0
_TOTAL_BUDGET_S = 120.0


def _m(payload: dict[str, Any]) -> ModelIR:
    metadata=dict(payload.get("metadata",{})); metadata.setdefault("numerical_verification",{"enabled":False})
    return ModelIR.from_dict({"schema_version":"1.0","domain":"general",**payload,"metadata":metadata})


def _models() -> dict[ModelFamily, ModelIR]:
    models:dict[ModelFamily,ModelIR]={}
    models[ModelFamily.ALGEBRAIC]=_m({"name":"alg","family":"algebraic","variables":[{"name":"x","initial":1.0}],"parameters":[],"equations":[{"target":"","expression":"x-2","kind":"residual"}]})
    models[ModelFamily.ODE]=_m({"name":"ode","family":"ode","variables":[{"name":"x","initial":1.0}],"parameters":[{"name":"k","value":1.0}],"equations":[{"target":"x","expression":"-k*x","kind":"derivative"}]})
    models[ModelFamily.STOCHASTIC]=_m({"name":"sde","family":"stochastic","variables":[{"name":"x","initial":1.0}],"parameters":[{"name":"k","value":.2}],"equations":[{"target":"x","expression":"-k*x","kind":"derivative"}],"metadata":{"diffusion":{"x":.05}}})
    models[ModelFamily.PDE]=_m({"name":"pde","family":"pde","variables":[{"name":"u","initial":1.0}],"parameters":[{"name":"k","value":.5}],"equations":[{"target":"u","expression":"-k*u","kind":"derivative"}],"metadata":{"pde":{"grid_points":10,"space_span":[0,1],"diffusion":{"u":.1},"boundary_conditions":{"u":{"left":{"type":"neumann","value":0},"right":{"type":"neumann","value":0}}}}}})
    models[ModelFamily.DAE]=_m({"name":"dae","family":"dae","variables":[{"name":"x","initial":1.0},{"name":"z","initial":1.0,"role":"latent"}],"parameters":[{"name":"k","value":1.0}],"equations":[{"target":"x","expression":"-z","kind":"derivative"},{"target":"","expression":"z-k*x","kind":"residual"}]})
    models[ModelFamily.OPTIMIZATION]=_m({"name":"opt","family":"optimization","variables":[{"name":"x","role":"decision","initial":0.0,"bounds":[-10,10]}],"parameters":[],"equations":[{"target":"","expression":"(x-3)**2","kind":"objective"}],"metadata":{"optimization":{"objective":"(x-3)**2","sense":"minimize"}}})
    models[ModelFamily.CONTROL]=_m({"name":"control","family":"control","variables":[{"name":"x","initial":1.0}],"parameters":[],"equations":[{"target":"x","expression":"0","kind":"state_space"}],"metadata":{"control":{"A":[[-1.0]],"B":[[0.0]],"C":[[1.0]],"D":[[0.0]],"input":0.0}}})
    models[ModelFamily.NETWORK]=_m({"name":"network","family":"network","variables":[{"name":"x","initial":.5}],"parameters":[{"name":"c","value":.5}],"equations":[{"target":"x","expression":"c*laplacian_x","kind":"derivative"}],"metadata":{"network":{"nodes":["a","b"],"edges":[["a","b"]],"initial":{"x":[1,0]}}}})
    models[ModelFamily.BAYESIAN]=_m({"name":"bayes","family":"bayesian","variables":[{"name":"y","role":"output","initial":0.0}],"parameters":[{"name":"a","value":1.5,"fit":True,"prior":{"dist":"normal","mu":0,"sigma":3}}],"equations":[{"target":"y","expression":"a*x","kind":"observation"}],"metadata":{"bayesian":{"data":{"x":[0,1,2,3]},"observations":[0,2,4,6],"mean_expression":"a*x","sigma":.2,"draws":120,"burn":50,"chains":2,"proposal_scale":{"a":.1}}}})
    models[ModelFamily.AGENT_BASED]=_m({"name":"agents","family":"agent_based","variables":[{"name":"x","initial":1.0}],"parameters":[{"name":"k","value":.5}],"equations":[{"target":"x","expression":"-k*x","kind":"derivative"}],"metadata":{"agents":{"count":4,"noise_std":0.0}}})
    models[ModelFamily.DISCRETE_EVENT]=_m({"name":"des","family":"discrete_event","variables":[{"name":"n","initial":0.0}],"parameters":[{"name":"lam","value":8.0}],"equations":[{"target":"n","expression":"0","kind":"event_state"}],"metadata":{"discrete_event":{"events":[{"name":"arrival","rate":"lam","delta":{"n":1.0}}]}}})
    models[ModelFamily.HYBRID]=_m({"name":"hybrid","family":"hybrid","variables":[{"name":"x","initial":1.0}],"parameters":[],"equations":[{"target":"x","expression":"-1","kind":"derivative"}],"metadata":{"hybrid":{"events":[{"name":"reset","expression":"x","direction":-1,"reset":{"x":"1"}}]}}})
    models[ModelFamily.CAUSAL]=_m({"name":"causal","family":"causal","variables":[{"name":"y","role":"output","initial":0.0}],"parameters":[],"equations":[{"target":"y","expression":"0","kind":"causal"}],"metadata":{"causal":{"treatment":"treat","outcome":"outcome","data":{"treat":[0,1,0,1,0,1,0,1],"outcome":[1,3,1,3,1,3,1,3]},"identification":{"randomized":True}}}})
    source=_m({"name":"source","family":"ode","variables":[{"name":"x","initial":2.0}],"parameters":[],"equations":[{"target":"x","expression":"0","kind":"derivative"}]}).to_dict()
    target=_m({"name":"target","family":"ode","variables":[{"name":"y","initial":1.0}],"parameters":[{"name":"k","value":1.0}],"equations":[{"target":"y","expression":"-k*y","kind":"derivative"}]}).to_dict()
    models[ModelFamily.MULTIPHYSICS]=_m({"name":"multi","family":"multiphysics","variables":[{"name":"q","initial":0.0}],"parameters":[],"equations":[{"target":"q","expression":"0","kind":"coupling"}],"metadata":{"multiphysics":{"components":{"source":source,"target":target},"couplings":[{"from_component":"source","from_state":"x","to_component":"target","to_parameter":"k","reduction":"final","scale":.5}],"tolerance":1e-8,"max_iterations":4}}})
    return models


def _execute_family(family:ModelFamily,model:ModelIR)->None:
    approve=family in {ModelFamily.BAYESIAN,ModelFamily.MULTIPHYSICS}
    out=simulate_model(model,t_span=(0,1.2 if family==ModelFamily.HYBRID else 1),points=20,seed=11,approve_heavy=approve)
    if out.get("status")!="PASS":raise AssertionError(f"{family.value} execution returned {out.get('status')}: {out}")
    if family==ModelFamily.ALGEBRAIC and abs(out["states"]["x"]-2)>1e-8:raise AssertionError("algebraic root incorrect")
    if family==ModelFamily.ODE and abs(out["states"]["x"][-1]-math.exp(-1))>1e-4:raise AssertionError("ODE reference mismatch")
    if family==ModelFamily.PDE and np.asarray(out["states"]["u"]).shape!=(20,10):raise AssertionError("PDE shape mismatch")
    if family==ModelFamily.BAYESIAN:
        if "posterior_predictive" not in out or "posterior" not in out["diagnostics"]:raise AssertionError("Bayesian diagnostics/PPC missing")
    if family==ModelFamily.CAUSAL and abs(out["causal_effect"]["estimate"]-2)>1e-8:raise AssertionError("causal randomized effect mismatch")


def _edge_contracts(models:dict[ModelFamily,ModelIR])->None:
    from axiomize.safe_expression import validate_expression
    try: validate_expression("__import__('os').system('x')",allowed_names=set())
    except ValueError: pass
    else: raise AssertionError("expression escape accepted")
    # Every family must expose an approval-gated verification plan before repeats.
    for family,model in models.items():
        out=numerical_refinement(model,t_span=(0,1),points=10,seed=3,approve_heavy=False)
        if out.get("status")!="APPROVAL_REQUIRED":raise AssertionError(f"{family.value} numerical verification not approval-gated: {out}")
    if export_model(models[ModelFamily.ODE],format="modelica-3.6").get("status")!="PASS":raise AssertionError("Modelica export failed")
    if export_model(models[ModelFamily.NETWORK],format="graphml").get("status")!="PASS":raise AssertionError("GraphML export failed")
    if export_model(models[ModelFamily.CAUSAL],format="causal-dot").get("status")!="PASS":raise AssertionError("causal DOT export failed")
    if export_model(models[ModelFamily.ODE],format="portable-bundle-v1").get("status")!="PASS":raise AssertionError("portable bundle failed")


def run_stress_matrix()->dict[str,Any]:
    models=_models(); missing=set(ModelFamily)-set(models)
    if missing:return {"status":"FAIL","detail":f"families missing from matrix: {sorted(x.value for x in missing)}"}
    results=[]; start_all=time.monotonic()
    for family in ModelFamily:
        start=time.monotonic()
        try:_execute_family(family,models[family])
        except Exception as exc:status="FAIL"; error=f"{type(exc).__name__}: {exc}"
        else:status="PASS"; error=""
        elapsed=time.monotonic()-start
        if elapsed>_CASE_BUDGET_S:status="FAIL"; error=f"runtime budget exceeded: {elapsed:.3f}s > {_CASE_BUDGET_S}s"
        results.append({"name":f"family:{family.value}","family":family.value,"status":status,"elapsed_s":round(elapsed,4),**({"error":error} if error else {})})
    start=time.monotonic()
    try:_edge_contracts(models)
    except Exception as exc:status="FAIL"; error=f"{type(exc).__name__}: {exc}"
    else:status="PASS"; error=""
    results.append({"name":"cross_cutting_contracts","status":status,"elapsed_s":round(time.monotonic()-start,4),**({"error":error} if error else {})})
    total=time.monotonic()-start_all
    if total>_TOTAL_BUDGET_S:results.append({"name":"total_runtime_budget","status":"FAIL","error":f"{total:.3f}s > {_TOTAL_BUDGET_S}s"})
    passed=sum(row["status"]=="PASS" for row in results)
    return {"status":"PASS" if passed==len(results) else "FAIL","passed":passed,"total":len(results),"families_covered":sorted(f.value for f in models),"elapsed_s":round(total,4),"results":results}
