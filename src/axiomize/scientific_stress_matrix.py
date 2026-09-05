"""Bounded end-to-end scientific benchmark/stress matrix.

The matrix exercises every Model IR family plus adversarial, export and
verification contracts. Cases use fixed seeds and objective tolerances. It is
safe for CI: each case and the total suite have wall-clock budgets, and no paid
or external model calls are made.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import numpy as np

from axiomize.general_engine import export_model, numerical_refinement, simulate_model
from axiomize.model_ir import ModelIR, UnsupportedSchemaVersion
from axiomize.safe_expression import validate_expression

CASE_BUDGET_S = 20.0
SUITE_BUDGET_S = 120.0


def _model(payload: dict[str, Any]) -> ModelIR:
    payload = {"schema_version": "1.0", "domain": "general", **payload}
    metadata = dict(payload.get("metadata", {})); metadata.setdefault("numerical_verification", {"enabled": False}); payload["metadata"] = metadata
    return ModelIR.from_dict(payload)


def _ode() -> None:
    m = _model({"name":"decay","family":"ode","variables":[{"name":"x","initial":1.0}],"parameters":[{"name":"k","value":0.5}],"equations":[{"target":"x","kind":"derivative","expression":"-k*x"}]})
    out = simulate_model(m, t_span=(0,1), points=41); assert out["status"] == "PASS" and abs(out["states"]["x"][-1]-np.exp(-.5)) < 1e-5


def _algebraic() -> None:
    m = _model({"name":"root","family":"algebraic","variables":[{"name":"x","initial":1.0}],"parameters":[],"equations":[{"target":"","kind":"residual","expression":"x**2-4"}]})
    out=simulate_model(m); assert out["status"]=="PASS" and abs(abs(out["states"]["x"])-2)<1e-8


def _stochastic() -> None:
    m=_model({"name":"sde","family":"stochastic","variables":[{"name":"x","initial":1.0}],"parameters":[{"name":"k","value":.2}],"equations":[{"target":"x","kind":"derivative","expression":"-k*x"}],"metadata":{"diffusion":{"x":.05}}})
    a=simulate_model(m,t_span=(0,1),points=100,seed=7); b=simulate_model(m,t_span=(0,1),points=100,seed=7); assert a["status"]=="PASS" and a["states"]==b["states"]


def _pde() -> None:
    m=_model({"name":"rd","family":"pde","variables":[{"name":"u","initial":1.0}],"parameters":[{"name":"k","value":.5}],"equations":[{"target":"u","kind":"derivative","expression":"-k*u"}],"metadata":{"pde":{"grid_points":12,"space_span":[0,1],"diffusion":{"u":.1},"boundary_conditions":{"u":{"left":{"type":"neumann","value":0},"right":{"type":"neumann","value":0}}}}}})
    out=simulate_model(m,t_span=(0,1),points=25); assert out["status"]=="PASS" and abs(float(np.mean(out["states"]["u"][-1]))-np.exp(-.5))<5e-4


def _dae() -> None:
    m=_model({"name":"dae","family":"dae","variables":[{"name":"x","initial":1.0},{"name":"z","initial":1.0,"role":"latent"}],"parameters":[{"name":"k","value":1.0}],"equations":[{"target":"x","kind":"derivative","expression":"-z"},{"target":"","kind":"residual","expression":"z-k*x"}]})
    out=simulate_model(m,t_span=(0,1),points=25); assert out["status"]=="PASS" and abs(out["states"]["x"][-1]-np.exp(-1))<5e-3


def _optimization() -> None:
    m=_model({"name":"opt","family":"optimization","variables":[{"name":"x","role":"decision","initial":0.0,"bounds":[-10,10]}],"parameters":[],"equations":[{"target":"","kind":"objective","expression":"(x-3)**2"}],"metadata":{"optimization":{"objective":"(x-3)**2","sense":"minimize"}}})
    out=simulate_model(m); assert out["status"]=="PASS" and abs(out["states"]["x"]-3)<5e-4


def _control() -> None:
    m=_model({"name":"control","family":"control","variables":[{"name":"x","initial":1.0}],"parameters":[],"equations":[{"target":"x","kind":"state_space","expression":"0"}],"metadata":{"control":{"A":[[-1.0]],"B":[[0.0]],"C":[[1.0]],"D":[[0.0]],"input":0.0}}})
    out=simulate_model(m,t_span=(0,1),points=30); assert out["status"]=="PASS" and out["diagnostics"]["stability"]=="stable"


def _network() -> None:
    m=_model({"name":"network","family":"network","variables":[{"name":"x","initial":.5}],"parameters":[{"name":"c","value":.5}],"equations":[{"target":"x","kind":"derivative","expression":"c*laplacian_x"}],"metadata":{"network":{"nodes":["a","b"],"edges":[["a","b"]],"initial":{"x":[1.0,0.0]}}}})
    out=simulate_model(m,t_span=(0,2),points=25); vals=np.asarray(out["states"]["x"]); assert out["status"]=="PASS" and abs(float(np.mean(vals[-1]))-.5)<1e-8


def _bayesian() -> None:
    m=_model({"name":"bayes","family":"bayesian","variables":[{"name":"y","role":"output","initial":0.0}],"parameters":[{"name":"a","value":1.5,"fit":True,"prior":{"dist":"normal","mu":0,"sigma":3}}],"equations":[{"target":"y","kind":"observation","expression":"a*x"}],"metadata":{"bayesian":{"data":{"x":[0.,1.,2.,3.,4.,5.]},"observations":[0.,2.,4.,6.,8.,10.],"mean_expression":"a*x","sigma":.2,"draws":350,"burn":100,"chains":2,"proposal_scale":{"a":.07}}}})
    out=simulate_model(m,seed=42,approve_heavy=True); assert out["status"] in {"PASS","WARNING"}; assert abs(out["posterior"]["a"]["mean"]-2)<.2; assert "posterior_predictive" in out


def _agent() -> None:
    m=_model({"name":"agents","family":"agent_based","variables":[{"name":"x","initial":1.0,"bounds":[0,None]}],"parameters":[{"name":"k","value":.5}],"equations":[{"target":"x","kind":"derivative","expression":"-k*x"}],"metadata":{"agents":{"count":4,"noise_std":0.0}}})
    out=simulate_model(m,t_span=(0,1),points=31,seed=1); assert out["status"]=="PASS" and np.asarray(out["states"]["x"]).shape==(31,4)


def _des() -> None:
    m=_model({"name":"des","family":"discrete_event","variables":[{"name":"n","initial":0.0}],"parameters":[{"name":"lam","value":5.0}],"equations":[{"target":"n","kind":"event_state","expression":"0"}],"metadata":{"discrete_event":{"events":[{"name":"arrival","rate":"lam","delta":{"n":1.0}}],"max_events":10000}}})
    out=simulate_model(m,t_span=(0,2),points=20,seed=3); assert out["status"]=="PASS" and out["diagnostics"]["total_events"]>0


def _hybrid() -> None:
    m=_model({"name":"hybrid","family":"hybrid","variables":[{"name":"x","initial":1.0}],"parameters":[],"equations":[{"target":"x","kind":"derivative","expression":"-1"}],"metadata":{"hybrid":{"events":[{"name":"reset","expression":"x","direction":-1,"reset":{"x":"1"}}]}}})
    out=simulate_model(m,t_span=(0,2.2),points=45); assert out["status"]=="PASS" and out["diagnostics"]["event_count"]>=2


def _causal() -> None:
    z=[0.,0.,0.,1.,1.,1.,0.,1.,0.,1.]; t=[0.,0.,1.,0.,1.,1.,0.,1.,1.,1.]; y=[3*zv+2*tv+1 for zv,tv in zip(z,t)]
    m=_model({"name":"causal","family":"causal","variables":[{"name":"y","role":"output","initial":0.0}],"parameters":[],"equations":[{"target":"y","kind":"causal","expression":"0"}],"metadata":{"causal":{"treatment":"t","outcome":"y","data":{"z":z,"t":t,"y":y},"estimator":"robust_ols","identification":{"dag":[["z","t"],["z","y"],["t","y"]],"auto_adjustment":True}}}})
    out=simulate_model(m); assert out["status"]=="PASS" and out["identification"]["adjustment_set"]==["z"] and abs(out["causal_effect"]["estimate"]-2)<1e-9


def _multiphysics() -> None:
    source=_model({"name":"source","family":"ode","variables":[{"name":"x","initial":2.0}],"parameters":[],"equations":[{"target":"x","kind":"derivative","expression":"0"}]}).to_dict()
    target=_model({"name":"target","family":"ode","variables":[{"name":"y","initial":1.0}],"parameters":[{"name":"k","value":1.0}],"equations":[{"target":"y","kind":"derivative","expression":"-k*y"}]}).to_dict()
    m=_model({"name":"multi","family":"multiphysics","variables":[{"name":"q","initial":0.0}],"parameters":[],"equations":[{"target":"q","kind":"coupling","expression":"0"}],"metadata":{"multiphysics":{"components":{"source":source,"target":target},"couplings":[{"from_component":"source","from_state":"x","to_component":"target","to_parameter":"k","reduction":"final","scale":.5}],"tolerance":1e-9,"max_iterations":4}}})
    out=simulate_model(m,t_span=(0,1),points=20,approve_heavy=True); assert out["status"]=="PASS" and out["diagnostics"]["converged"]


def _expression_attack_rejected() -> None:
    try: validate_expression("__import__('os').system('x')", allowed_names={"x"})
    except ValueError: return
    raise AssertionError("unsafe expression accepted")


def _future_schema_rejected() -> None:
    try: ModelIR.from_dict({"schema_version":"99","name":"x","domain":"g","family":"ode","variables":[],"parameters":[],"equations":[]}, allow_migration=True)
    except UnsupportedSchemaVersion: return
    raise AssertionError("future schema silently accepted")


def _causal_unidentified_rejected() -> None:
    m=_model({"name":"assoc","family":"causal","variables":[{"name":"y","role":"output","initial":0}],"parameters":[],"equations":[{"target":"y","kind":"causal","expression":"0"}],"metadata":{"causal":{"treatment":"t","outcome":"y","data":{"t":[0,1,0,1],"y":[0,1,0,1]}}}})
    assert simulate_model(m)["status"]=="INSUFFICIENT_CAUSAL_EVIDENCE"


def _exports() -> None:
    m=_model({"name":"export-decay","family":"ode","variables":[{"name":"x","initial":1}],"parameters":[{"name":"k","value":.2}],"equations":[{"target":"x","kind":"derivative","expression":"-k*x"}]})
    for fmt in ("json","python","ipynb","latex","mathml","dot","markdown","julia"):
        out=export_model(m,format=fmt); assert out.get("status","PASS") == "PASS" and out.get("content")


def _verification_contract() -> None:
    m=_model({"name":"verify-root","family":"algebraic","variables":[{"name":"x","initial":1}],"parameters":[],"equations":[{"target":"","kind":"residual","expression":"x-2"}]})
    blocked=numerical_refinement(m,approve_heavy=False); assert blocked["status"]=="APPROVAL_REQUIRED"
    checked=numerical_refinement(m,approve_heavy=True); assert checked["status"]=="PASS"


_CASES: list[tuple[str,str,Callable[[],None]]] = [
    ("ode","family",_ode),("algebraic","family",_algebraic),("stochastic","family",_stochastic),("pde","family",_pde),
    ("dae","family",_dae),("optimization","family",_optimization),("control","family",_control),("network","family",_network),
    ("bayesian","family",_bayesian),("agent_based","family",_agent),("discrete_event","family",_des),("hybrid","family",_hybrid),
    ("causal","family",_causal),("multiphysics","family",_multiphysics),("expression_attack","adversarial",_expression_attack_rejected),
    ("future_schema","adversarial",_future_schema_rejected),("causal_identification_guard","adversarial",_causal_unidentified_rejected),
    ("expanded_exports","portability",_exports),("all_family_verification_contract","verification",_verification_contract),
]


def run_matrix(*, case_budget_s: float = CASE_BUDGET_S, suite_budget_s: float = SUITE_BUDGET_S) -> dict[str,Any]:
    started=time.monotonic(); results=[]
    for name,category,fn in _CASES:
        case_start=time.monotonic(); error=None
        try: fn()
        except Exception as exc: error=f"{type(exc).__name__}: {exc}"
        elapsed=time.monotonic()-case_start
        status="PASS" if error is None and elapsed<=case_budget_s else "FAIL"
        if error is None and elapsed>case_budget_s: error=f"case runtime {elapsed:.3f}s exceeded budget {case_budget_s:.3f}s"
        results.append({"name":name,"category":category,"status":status,"elapsed_s":round(elapsed,4),**({"error":error} if error else {})})
        if time.monotonic()-started>suite_budget_s:
            results.append({"name":"suite_budget","category":"stress","status":"FAIL","elapsed_s":round(time.monotonic()-started,4),"error":f"suite exceeded {suite_budget_s}s"}); break
    elapsed=time.monotonic()-started; passed=sum(r["status"]=="PASS" for r in results)
    family_passed=sum(r["status"]=="PASS" and r["category"]=="family" for r in results)
    return {"status":"PASS" if passed==len(results) and family_passed==14 else "FAIL","passed":passed,"total":len(results),
            "family_coverage":{"passed":family_passed,"total":14},"elapsed_s":round(elapsed,4),"case_budget_s":case_budget_s,"suite_budget_s":suite_budget_s,"results":results}
