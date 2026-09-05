"""Bayesian Engine 2.0: bounded multi-chain MH, convergence diagnostics and PPC."""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from axiomize.bayesian.diagnostics import normal_posterior_predictive, posterior_diagnostics
from axiomize.limits import MAX_ARRAY_ITEMS, MAX_BAYES_DRAWS, bounded_int, enforce_result_cells
from axiomize.model_ir import ModelIR
from axiomize.safe_expression import sympy_expression

_MAX_LIKELIHOOD_WORK = 50_000_000


def _parameters(model: ModelIR, overrides: dict[str, float] | None) -> dict[str, float]:
    overrides = dict(overrides or {}); known = {p.name for p in model.parameters}
    unknown = sorted(set(overrides) - known)
    if unknown: raise ValueError(f"unknown parameter overrides: {unknown}")
    out: dict[str, float] = {}
    for p in model.parameters:
        raw = overrides[p.name] if p.name in overrides else p.value
        if raw is None: raise ValueError(f"parameter {p.name!r} has no value")
        value = float(raw)
        if not math.isfinite(value): raise ValueError(f"parameter {p.name!r} must be finite")
        out[p.name] = value
    return out


def _compile(expression: str, names: list[str]):
    import sympy as sp
    symbols = {name: sp.Symbol(name, real=True) for name in names}
    expr = sympy_expression(expression, symbols)
    return sp.lambdify([symbols[name] for name in names], expr, modules=["numpy", "math"])


def _log_prior(value: float, prior: dict[str, Any] | None, bounds: tuple[float | None, float | None] | None, center: float) -> float:
    if bounds:
        lo, hi = bounds
        if lo is not None and value < lo: return -math.inf
        if hi is not None and value > hi: return -math.inf
    if not prior:
        scale = max(abs(center), 1.0) * 10.0
        return -0.5 * ((value-center)/scale)**2 - math.log(scale)
    dist = str(prior.get("dist", prior.get("distribution", "normal"))).lower()
    if dist == "normal":
        mu = float(prior.get("mu", prior.get("mean", center))); sigma = float(prior.get("sigma", prior.get("sd", 1.0)))
        if sigma <= 0 or not math.isfinite(sigma): raise ValueError("normal prior sigma must be finite and positive")
        return -0.5*((value-mu)/sigma)**2-math.log(sigma)
    if dist == "halfnormal":
        sigma = float(prior.get("sigma", prior.get("sd", 1.0)))
        if sigma <= 0 or not math.isfinite(sigma): raise ValueError("halfnormal prior sigma must be finite and positive")
        return -math.inf if value < 0 else -0.5*(value/sigma)**2-math.log(sigma)
    if dist == "uniform":
        lo = float(prior.get("low", prior.get("lower", -math.inf))); hi = float(prior.get("high", prior.get("upper", math.inf)))
        if lo >= hi: raise ValueError("uniform prior lower must be < upper")
        return 0.0 if lo <= value <= hi else -math.inf
    if dist == "lognormal":
        if value <= 0: return -math.inf
        mu = float(prior.get("mu", 0)); sigma = float(prior.get("sigma", 1))
        if sigma <= 0 or not math.isfinite(sigma): raise ValueError("lognormal prior sigma must be finite and positive")
        lv=math.log(value); return -0.5*((lv-mu)/sigma)**2-math.log(value*sigma)
    raise ValueError(f"unsupported builtin prior distribution: {dist}")


def infer_bayesian_model(model: ModelIR, *, t_span: tuple[float,float], points: int,
                         parameter_overrides: dict[str,float] | None, seed: int) -> dict[str,Any]:
    del t_span
    parameters = _parameters(model, parameter_overrides)
    cfg = model.metadata.get("bayesian", {})
    if not isinstance(cfg, dict): raise ValueError("metadata.bayesian must be an object")
    data = cfg.get("data", {})
    if not isinstance(data, dict): raise ValueError("bayesian.data must be an object")
    observed_raw = cfg.get("observations", cfg.get("observed"))
    if observed_raw is None and isinstance(cfg.get("outcome"), str): observed_raw = data.get(str(cfg["outcome"]))
    observed = np.asarray(observed_raw, dtype=float) if observed_raw is not None else np.asarray([])
    if observed.ndim != 1 or observed.size < 2 or observed.size > MAX_ARRAY_ITEMS or not np.all(np.isfinite(observed)):
        raise ValueError(f"bayesian observations must be finite 1D with 2..{MAX_ARRAY_ITEMS} values")
    mean_expression = cfg.get("mean_expression")
    if mean_expression is None:
        equation = next((e for e in model.equations if e.kind in {"likelihood","observation","mean"}), None)
        if equation is None: raise ValueError("bayesian inference requires mean_expression or likelihood/observation equation")
        mean_expression = equation.expression
    sampled = [p for p in model.parameters if p.fit or p.prior is not None] or list(model.parameters)
    if not sampled: raise ValueError("bayesian inference requires at least one parameter")
    pnames=[p.name for p in model.parameters]
    outcome=str(cfg.get("outcome", "")); predictors=sorted(k for k in data if k != outcome)
    fn=_compile(str(mean_expression), [*predictors,*pnames])
    predictor_values=[]
    for name in predictors:
        arr=np.asarray(data[name],dtype=float)
        if arr.ndim==0: predictor_values.append(float(arr))
        elif arr.shape==observed.shape and np.all(np.isfinite(arr)): predictor_values.append(arr)
        else: raise ValueError(f"bayesian.data.{name} must be finite scalar or match observations")
    sigma_spec=cfg.get("sigma",1.0)
    if isinstance(sigma_spec,str) and sigma_spec not in pnames: raise ValueError("bayesian sigma parameter name is unknown")
    draws=bounded_int(cfg.get("draws", max(200,int(points))),name="bayesian.draws",minimum=50,maximum=MAX_BAYES_DRAWS)
    burn=bounded_int(cfg.get("burn",max(50,draws//4)),name="bayesian.burn",minimum=0,maximum=MAX_BAYES_DRAWS)
    chains=bounded_int(cfg.get("chains",4),name="bayesian.chains",minimum=2,maximum=8)
    if (draws+burn)*chains*observed.size > _MAX_LIKELIHOOD_WORK: raise ValueError("Bayesian request exceeds hard likelihood-work limit")
    enforce_result_cells(chains, draws, len(sampled), name="Bayesian chains")
    centers=np.asarray([parameters[p.name] for p in sampled],dtype=float)
    proposal_cfg=cfg.get("proposal_scale",{})
    scales=np.empty(len(sampled),dtype=float)
    for i,p in enumerate(sampled):
        if isinstance(proposal_cfg,dict) and p.name in proposal_cfg: scales[i]=float(proposal_cfg[p.name])
        elif isinstance(proposal_cfg,(int,float)): scales[i]=float(proposal_cfg)
        elif p.prior and str(p.prior.get("dist","normal")).lower() in {"normal","halfnormal","lognormal"}: scales[i]=.15*float(p.prior.get("sigma",p.prior.get("sd",1)))
        elif p.bounds and p.bounds[0] is not None and p.bounds[1] is not None: scales[i]=.05*(float(p.bounds[1])-float(p.bounds[0]))
        else: scales[i]=.1*max(abs(parameters[p.name]),1.0)
        if not math.isfinite(scales[i]) or scales[i] <= 0: raise ValueError(f"proposal scale for {p.name} must be finite and positive")
    index={p.name:i for i,p in enumerate(sampled)}
    def posterior(v:np.ndarray)->float:
        env=dict(parameters)
        for p in sampled: env[p.name]=float(v[index[p.name]])
        lp=0.0
        for p in sampled:
            item=_log_prior(env[p.name],p.prior,p.bounds,parameters[p.name])
            if not math.isfinite(item): return -math.inf
            lp+=item
        mean=np.asarray(fn(*predictor_values,*[env[n] for n in pnames]),dtype=float)
        if mean.ndim==0: mean=np.full(observed.shape,float(mean))
        if mean.shape!=observed.shape or not np.all(np.isfinite(mean)): return -math.inf
        sigma=env[sigma_spec] if isinstance(sigma_spec,str) else float(sigma_spec)
        if not math.isfinite(float(sigma)) or sigma<=0:return -math.inf
        r=(observed-mean)/sigma
        return lp - .5*float(np.dot(r,r)) - observed.size*math.log(float(sigma))
    all_chains=np.zeros((chains,draws,len(sampled)),dtype=float); accept=[]
    for c in range(chains):
        rng=np.random.default_rng(int(seed)+104729*c)
        current=centers + rng.normal(scale=scales*0.05,size=centers.shape)
        current_lp=posterior(current)
        if not math.isfinite(current_lp): current=centers.copy(); current_lp=posterior(current)
        if not math.isfinite(current_lp): raise ValueError("initial Bayesian parameter values have zero/invalid posterior density")
        accepted=0; kept=0
        for iteration in range(draws+burn):
            proposal=current+rng.normal(scale=scales,size=current.shape); proposed=posterior(proposal)
            if math.isfinite(proposed) and math.log(max(rng.random(),1e-300)) < proposed-current_lp:
                current=proposal; current_lp=proposed; accepted+=1
            if iteration>=burn: all_chains[c,kept]=current; kept+=1
        accept.append(accepted/max(1,draws+burn))
    flat=all_chains.reshape(chains*draws,len(sampled)); summaries={}; posterior_params=dict(parameters)
    for i,p in enumerate(sampled):
        column=flat[:,i]; mean=float(np.mean(column)); posterior_params[p.name]=mean
        summaries[p.name]={"mean":mean,"sd":float(np.std(column,ddof=1)),"q025":float(np.quantile(column,.025)),"median":float(np.quantile(column,.5)),"q975":float(np.quantile(column,.975))}
    diag=posterior_diagnostics(all_chains,[p.name for p in sampled])
    # PPC uses a deterministic bounded subset of posterior draws.
    ppc_count=min(1000,flat.shape[0]); idx=np.linspace(0,flat.shape[0]-1,ppc_count,dtype=int); ppc_means=[]; ppc_sigmas=[]
    for row in flat[idx]:
        env=dict(parameters)
        for p in sampled: env[p.name]=float(row[index[p.name]])
        mean=np.asarray(fn(*predictor_values,*[env[n] for n in pnames]),dtype=float)
        if mean.ndim==0: mean=np.full(observed.shape,float(mean))
        sigma=env[sigma_spec] if isinstance(sigma_spec,str) else float(sigma_spec)
        ppc_means.append(mean); ppc_sigmas.append(sigma)
    ppc=normal_posterior_predictive(observed=observed,means=np.asarray(ppc_means),sigmas=np.asarray(ppc_sigmas),seed=int(seed)+99991,max_replications=ppc_count)
    result:dict[str,Any]={
        "status":"PASS","family":model.family.value,
        "states":{v.name:float(v.initial) for v in model.variables if v.initial is not None},
        "parameters":posterior_params,"posterior":summaries,
        "posterior_predictive":ppc,
        "solver":{"backend":"builtin","method":"multi_chain_random_walk_metropolis","seed":int(seed)},
        "diagnostics":{"draws":draws,"burn":burn,"chains":chains,"acceptance_rate_by_chain":accept,"posterior":diag,"finite":bool(np.all(np.isfinite(all_chains)))},
    }
    if bool(cfg.get("return_samples",False)):
        result["samples"]={p.name:flat[:,i].tolist() for i,p in enumerate(sampled)}
    return result
