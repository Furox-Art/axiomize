"""Numerical verification 2.0 covering every executable Model IR family.

ODE/DAE/PDE retain dedicated tolerance/mesh refinement. Other families use a
family-appropriate bounded replay or output-resolution study. Numerical error is
kept separate from stochastic/Monte-Carlo variability and scientific uncertainty.
"""
from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np

from axiomize.model_ir import ModelFamily, ModelIR
from axiomize.numerical_verification import numerical_refinement_study as _legacy

SimulateOnce = Callable[..., dict[str, Any]]
_STOCHASTIC = {ModelFamily.STOCHASTIC, ModelFamily.BAYESIAN, ModelFamily.AGENT_BASED, ModelFamily.DISCRETE_EVENT}
_TRAJECTORY = {ModelFamily.CONTROL, ModelFamily.NETWORK, ModelFamily.HYBRID, ModelFamily.MULTIPHYSICS}


def _approval(model: ModelIR, points: int, study: str, runs: int = 2) -> dict[str, Any]:
    return {
        "status":"APPROVAL_REQUIRED","study":study,"family":model.family.value,
        "cost":{"level":"low" if points*runs<50_000 else "medium","planned_refinement_runs":runs,
                "temporal_output_points":points,"estimated_work_units":points*runs*max(1,len(model.variables)),
                "requires_user_approval":True,"reason":"verification repeats the native model executor"},
        "uncertainty_separation":{"numerical":"pending verification","aleatoric":"separate","parameter":"separate","data":"separate","model_structural":"separate"},
    }


def _numeric_leaves(value: Any, prefix: str="") -> dict[str,float]:
    out:dict[str,float]={}
    if isinstance(value,bool) or value is None:return out
    if isinstance(value,(int,float,np.number)):
        x=float(value)
        if math.isfinite(x):out[prefix or "value"]=x
        return out
    if isinstance(value,dict):
        for k,v in value.items():
            if str(k) in {"time","seed","elapsed_s","runtime_s"}:continue
            out.update(_numeric_leaves(v,f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(value,(list,tuple)) and len(value)<=10000:
        arr=np.asarray(value)
        if np.issubdtype(arr.dtype,np.number) and arr.size:
            flat=np.asarray(arr,dtype=float).reshape(-1)
            if np.all(np.isfinite(flat)):
                out[prefix or "array.mean"]=float(np.mean(flat)); out[(prefix or "array")+".norm"]=float(np.linalg.norm(flat))
    return out


def _terminal_states(result:dict[str,Any])->np.ndarray:
    states=result.get("states",{})
    if not isinstance(states,dict) or not states:return np.asarray([])
    chunks=[]
    for name in sorted(states):
        arr=np.asarray(states[name],dtype=float)
        if arr.size==0:continue
        terminal=arr[-1] if arr.ndim>=1 else arr
        chunks.append(np.asarray(terminal,dtype=float).reshape(-1))
    return np.concatenate(chunks) if chunks else np.asarray([])


def _relative(a:np.ndarray,b:np.ndarray)->float:
    a=np.asarray(a,dtype=float).reshape(-1); b=np.asarray(b,dtype=float).reshape(-1)
    if a.shape!=b.shape or not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        raise ValueError("verification comparison arrays are incompatible/non-finite")
    return float(np.linalg.norm(a-b)/max(np.linalg.norm(b),np.finfo(float).eps))


def _run(simulate_once:SimulateOnce, model:ModelIR, *, t_span, points, parameter_overrides, seed)->dict[str,Any]:
    result=simulate_once(model,t_span=t_span,points=points,parameter_overrides=parameter_overrides,seed=seed,approve_heavy=True)
    if result.get("status")!="PASS":raise RuntimeError(f"verification replay failed: {result.get('status')}")
    return result


def _replay_study(model:ModelIR, *, simulate_once:SimulateOnce,t_span,points,parameter_overrides,seed,tolerance,approve_heavy)->dict[str,Any]:
    if not approve_heavy:return _approval(model,points,"same_seed_reproducibility",2)
    a=_run(simulate_once,model,t_span=t_span,points=points,parameter_overrides=parameter_overrides,seed=seed)
    b=_run(simulate_once,model,t_span=t_span,points=points,parameter_overrides=parameter_overrides,seed=seed)
    av=_numeric_leaves(a); bv=_numeric_leaves(b); keys=sorted(set(av)&set(bv))
    diffs=[abs(av[k]-bv[k])/max(abs(bv[k]),1e-15) for k in keys]
    error=max(diffs,default=0.0); converged=error<=tolerance
    return {"status":"PASS" if converged else "FAIL","study":"same_seed_reproducibility","family":model.family.value,
            "converged":converged,"tolerance":tolerance,"estimated_numerical_error":error,
            "error_metric":"maximum relative difference across deterministic numeric summaries under identical seed",
            "uncertainty_separation":{"numerical":error,"aleatoric":"not estimated by same-seed replay; vary seeds separately","parameter":"separate","data":"separate","model_structural":"separate"},
            "interpretation":"same-seed replay tests implementation/numerical reproducibility only; between-seed variation is stochastic uncertainty, not numerical error"}


def _resolution_study(model:ModelIR, *, simulate_once:SimulateOnce,t_span,points,parameter_overrides,seed,tolerance,approve_heavy)->dict[str,Any]:
    fine=min(max(points+1,points*2-1),200_000)
    if fine<=points:return _replay_study(model,simulate_once=simulate_once,t_span=t_span,points=points,parameter_overrides=parameter_overrides,seed=seed,tolerance=tolerance,approve_heavy=approve_heavy)
    if not approve_heavy:return _approval(model,points,"output_resolution_refinement",2)
    coarse=_run(simulate_once,model,t_span=t_span,points=points,parameter_overrides=parameter_overrides,seed=seed)
    refined=_run(simulate_once,model,t_span=t_span,points=fine,parameter_overrides=parameter_overrides,seed=seed)
    ca=_terminal_states(coarse); fa=_terminal_states(refined)
    if ca.size and fa.size: error=_relative(ca,fa); metric="terminal-state relative L2 difference"
    else:
        c=_numeric_leaves(coarse); f=_numeric_leaves(refined); keys=sorted(set(c)&set(f)); error=max([abs(c[k]-f[k])/max(abs(f[k]),1e-15) for k in keys],default=0.0); metric="numeric-summary relative difference"
    converged=error<=tolerance
    return {"status":"PASS" if converged else "FAIL","study":"output_resolution_refinement","family":model.family.value,"converged":converged,
            "tolerance":tolerance,"levels":[points,fine],"estimated_numerical_error":error,"error_metric":metric,
            "uncertainty_separation":{"numerical":error,"aleatoric":"separate","parameter":"separate","data":"separate","model_structural":"separate"}}


def _deterministic_replay(model:ModelIR, **kwargs:Any)->dict[str,Any]:
    return _replay_study(model,**kwargs)


def numerical_refinement_study_v2(model:ModelIR, *, simulate_once:SimulateOnce,t_span:tuple[float,float],points:int=200,
                                  parameter_overrides:dict[str,float]|None=None,seed:int=0,tolerance:float=1e-3,approve_heavy:bool=False)->dict[str,Any]:
    if not math.isfinite(float(tolerance)) or tolerance<=0:raise ValueError("numerical refinement tolerance must be finite and positive")
    if points<2:raise ValueError("points must be at least 2")
    if model.family in {ModelFamily.ODE,ModelFamily.DAE,ModelFamily.PDE}:
        return _legacy(model,simulate_once=simulate_once,t_span=t_span,points=points,parameter_overrides=parameter_overrides,seed=seed,tolerance=tolerance,approve_heavy=approve_heavy)
    kwargs=dict(simulate_once=simulate_once,t_span=t_span,points=points,parameter_overrides=parameter_overrides,seed=seed,tolerance=tolerance,approve_heavy=approve_heavy)
    if model.family in _STOCHASTIC:return _replay_study(model,**kwargs)
    if model.family in _TRAJECTORY:return _resolution_study(model,**kwargs)
    # algebraic, optimization and causal have no time-grid truncation in their native executors;
    # verify deterministic numerical repeatability instead of fabricating a mesh error.
    return _deterministic_replay(model,**kwargs)
