"""Native bounded Bayesian engine with multi-chain diagnostics and PPC."""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from axiomize.bayesian.diagnostics import parameter_diagnostics, posterior_predictive_normal
from axiomize.limits import MAX_ARRAY_ITEMS, MAX_BAYES_DRAWS, bounded_int
from axiomize.model_ir import ModelIR
from axiomize.safe_expression import sympy_expression

_MAX_CHAINS = 8
_MAX_LIKELIHOOD_WORK = 50_000_000


def _finite_array(values: Any, *, name: str) -> np.ndarray:
    try:
        out = np.asarray(values, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if out.ndim != 1 or out.size < 2 or out.size > MAX_ARRAY_ITEMS:
        raise ValueError(f"{name} must be a 1D array with 2..{MAX_ARRAY_ITEMS} values")
    if not np.all(np.isfinite(out)):
        raise ValueError(f"{name} must contain only finite values")
    return out


def _log_prior(value: float, prior: dict[str, Any] | None, bounds: tuple[float | None, float | None] | None, center: float) -> float:
    if bounds is not None:
        low, high = bounds
        if low is not None and value < float(low): return -math.inf
        if high is not None and value > float(high): return -math.inf
    if not prior:
        scale = max(abs(center), 1.0) * 10.0
        return -0.5 * ((value - center) / scale) ** 2 - math.log(scale)
    kind = str(prior.get("dist", prior.get("distribution", "normal"))).lower()
    if kind == "normal":
        mu = float(prior.get("mu", prior.get("mean", center))); sigma = float(prior.get("sigma", prior.get("sd", 1.0)))
        if not math.isfinite(mu) or not math.isfinite(sigma) or sigma <= 0: raise ValueError("normal prior requires finite mu and sigma > 0")
        return -0.5 * ((value - mu) / sigma) ** 2 - math.log(sigma)
    if kind == "halfnormal":
        sigma = float(prior.get("sigma", prior.get("sd", 1.0)))
        if not math.isfinite(sigma) or sigma <= 0: raise ValueError("halfnormal prior sigma must be positive")
        return -math.inf if value < 0 else -0.5 * (value / sigma) ** 2 - math.log(sigma)
    if kind == "uniform":
        low = float(prior.get("low", prior.get("lower", -math.inf))); high = float(prior.get("high", prior.get("upper", math.inf)))
        if low > high: raise ValueError("uniform prior lower must be <= upper")
        return 0.0 if low <= value <= high else -math.inf
    if kind == "lognormal":
        if value <= 0: return -math.inf
        mu = float(prior.get("mu", 0.0)); sigma = float(prior.get("sigma", 1.0))
        if not math.isfinite(mu) or not math.isfinite(sigma) or sigma <= 0: raise ValueError("lognormal prior requires finite mu and sigma > 0")
        logv = math.log(value)
        return -0.5 * ((logv - mu) / sigma) ** 2 - math.log(value * sigma)
    raise ValueError(f"unsupported builtin prior distribution: {kind}")


def infer_bayesian(
    model: ModelIR,
    *,
    t_span: tuple[float, float] = (0.0, 1.0),
    points: int = 200,
    parameter_overrides: dict[str, float] | None = None,
    seed: int = 0,
) -> dict[str, Any]:
    del t_span
    from axiomize.general_engine_core import _parameter_values
    import sympy as sp

    parameters = _parameter_values(model, parameter_overrides)
    cfg = model.metadata.get("bayesian", {})
    if not isinstance(cfg, dict): raise ValueError("metadata.bayesian must be an object")
    data = cfg.get("data", {})
    if not isinstance(data, dict): raise ValueError("bayesian.data must be an object")
    observed_raw = cfg.get("observations", cfg.get("observed"))
    if observed_raw is None and isinstance(cfg.get("outcome"), str): observed_raw = data.get(str(cfg["outcome"]))
    if observed_raw is None: raise ValueError("bayesian inference requires observations")
    observed = _finite_array(observed_raw, name="bayesian observations")

    mean_expression = cfg.get("mean_expression")
    if mean_expression is None:
        equation = next((e for e in model.equations if e.kind in {"likelihood", "observation", "mean"}), None)
        if equation is None: raise ValueError("bayesian inference requires mean_expression or likelihood/observation equation")
        mean_expression = equation.expression
    sampled_parameters = [p for p in model.parameters if p.fit or p.prior is not None] or list(model.parameters)
    if not sampled_parameters: raise ValueError("bayesian inference requires at least one parameter")
    pnames = [p.name for p in model.parameters]
    predictor_names = sorted(k for k in data if k != cfg.get("outcome"))
    symbols = {name: sp.Symbol(name, real=True) for name in [*predictor_names, *pnames]}
    expr = sympy_expression(str(mean_expression), symbols)
    mean_fn = sp.lambdify([symbols[name] for name in [*predictor_names, *pnames]], expr, modules=["numpy", "math"])
    predictors: list[Any] = []
    for name in predictor_names:
        raw = np.asarray(data[name], dtype=float)
        if raw.ndim == 0 and math.isfinite(float(raw)): predictors.append(float(raw))
        elif raw.shape == observed.shape and np.all(np.isfinite(raw)): predictors.append(raw)
        else: raise ValueError(f"bayesian.data.{name} must be finite scalar or match observations")

    draws = bounded_int(cfg.get("draws", max(200, int(points))), name="bayesian.draws", minimum=50, maximum=MAX_BAYES_DRAWS)
    burn = bounded_int(cfg.get("burn", max(50, draws // 4)), name="bayesian.burn", minimum=0, maximum=MAX_BAYES_DRAWS)
    chains_n = bounded_int(cfg.get("chains", 4), name="bayesian.chains", minimum=2, maximum=_MAX_CHAINS)
    if chains_n * (draws + burn) * observed.size > _MAX_LIKELIHOOD_WORK:
        raise ValueError(f"Bayesian request exceeds hard likelihood-work limit {_MAX_LIKELIHOOD_WORK}")
    sigma_spec = cfg.get("sigma", 1.0)
    if isinstance(sigma_spec, str) and sigma_spec not in pnames: raise ValueError("bayesian sigma parameter name is unknown")
    if not isinstance(sigma_spec, str):
        sigma_value = float(sigma_spec)
        if not math.isfinite(sigma_value) or sigma_value <= 0: raise ValueError("bayesian sigma must be finite and positive")

    proposal_cfg = cfg.get("proposal_scale", {})
    scales = np.zeros(len(sampled_parameters), dtype=float)
    for i, parameter in enumerate(sampled_parameters):
        if isinstance(proposal_cfg, dict) and parameter.name in proposal_cfg: scale = float(proposal_cfg[parameter.name])
        elif isinstance(proposal_cfg, (int, float)): scale = float(proposal_cfg)
        elif parameter.prior and str(parameter.prior.get("dist", "normal")).lower() in {"normal", "halfnormal", "lognormal"}: scale = 0.15 * float(parameter.prior.get("sigma", parameter.prior.get("sd", 1.0)))
        elif parameter.bounds and parameter.bounds[0] is not None and parameter.bounds[1] is not None: scale = 0.05 * (float(parameter.bounds[1]) - float(parameter.bounds[0]))
        else: scale = 0.1 * max(abs(parameters[parameter.name]), 1.0)
        if not math.isfinite(scale) or scale <= 0: raise ValueError(f"proposal scale for {parameter.name} must be positive and finite")
        scales[i] = max(scale, 1e-8)
    sampled_index = {p.name: i for i, p in enumerate(sampled_parameters)}

    def evaluate_mean(env: dict[str, float]) -> np.ndarray:
        mean = np.asarray(mean_fn(*predictors, *[env[name] for name in pnames]), dtype=float)
        if mean.ndim == 0: mean = np.full(observed.shape, float(mean))
        if mean.shape != observed.shape or not np.all(np.isfinite(mean)): raise FloatingPointError("invalid likelihood mean")
        return mean

    def log_posterior(values: np.ndarray) -> float:
        env = dict(parameters)
        for p in sampled_parameters: env[p.name] = float(values[sampled_index[p.name]])
        lp = 0.0
        for p in sampled_parameters:
            current = _log_prior(env[p.name], p.prior, p.bounds, parameters[p.name])
            if not math.isfinite(current): return -math.inf
            lp += current
        try: mean = evaluate_mean(env)
        except FloatingPointError: return -math.inf
        sigma = env[sigma_spec] if isinstance(sigma_spec, str) else float(sigma_spec)
        if not math.isfinite(float(sigma)) or sigma <= 0: return -math.inf
        residual = observed - mean
        return lp - 0.5 * float(np.sum((residual / sigma) ** 2)) - observed.size * math.log(float(sigma))

    baseline = np.asarray([parameters[p.name] for p in sampled_parameters], dtype=float)
    chain = np.zeros((chains_n, draws, len(sampled_parameters)), dtype=float)
    acceptance: list[float] = []
    rng_master = np.random.SeedSequence(int(seed))
    for chain_i, sequence in enumerate(rng_master.spawn(chains_n)):
        rng = np.random.default_rng(sequence)
        current = baseline.copy()
        if chain_i:
            current += rng.normal(scale=scales * 0.25, size=current.shape)
        current_lp = log_posterior(current)
        if not math.isfinite(current_lp):
            current = baseline.copy(); current_lp = log_posterior(current)
        if not math.isfinite(current_lp): raise ValueError("initial Bayesian parameter values have zero/invalid posterior density")
        accepted = kept = 0
        for iteration in range(draws + burn):
            proposal = current + rng.normal(scale=scales, size=current.shape)
            proposed_lp = log_posterior(proposal)
            if math.isfinite(proposed_lp) and math.log(max(rng.random(), 1e-300)) < proposed_lp - current_lp:
                current, current_lp = proposal, proposed_lp; accepted += 1
            if iteration >= burn:
                chain[chain_i, kept] = current; kept += 1
        acceptance.append(accepted / float(draws + burn))
    if not np.all(np.isfinite(chain)): raise RuntimeError("Bayesian sampler produced non-finite chain values")

    posterior: dict[str, Any] = {}; diagnostics: dict[str, Any] = {}
    posterior_parameters = dict(parameters)
    for i, p in enumerate(sampled_parameters):
        values = chain[:, :, i]; flat = values.reshape(-1)
        stats = parameter_diagnostics(values)
        posterior_parameters[p.name] = float(np.mean(flat))
        posterior[p.name] = {
            "mean": float(np.mean(flat)), "sd": float(np.std(flat, ddof=1)),
            "q025": float(np.quantile(flat, .025)), "median": float(np.quantile(flat, .5)), "q975": float(np.quantile(flat, .975)),
            **stats,
        }
        diagnostics[p.name] = stats

    converged = all(v["r_hat"] <= 1.05 and v["ess_bulk"] >= max(100.0, chains_n * draws * 0.01) for v in diagnostics.values())
    # PPC on a deterministic thinning of all posterior draws.
    flat_chain = chain.reshape(-1, chain.shape[-1])
    ppc_count = min(2000, flat_chain.shape[0])
    indices = np.linspace(0, flat_chain.shape[0] - 1, ppc_count, dtype=int)
    mean_draws = np.zeros((ppc_count, observed.size), dtype=float); sigma_draws = np.zeros(ppc_count, dtype=float)
    for j, values in enumerate(flat_chain[indices]):
        env = dict(parameters)
        for p in sampled_parameters: env[p.name] = float(values[sampled_index[p.name]])
        mean_draws[j] = evaluate_mean(env)
        sigma_draws[j] = env[sigma_spec] if isinstance(sigma_spec, str) else float(sigma_spec)
    ppc = posterior_predictive_normal(mean_draws, sigma_draws=sigma_draws, observed=observed, seed=int(seed) + 991)

    result: dict[str, Any] = {
        "status": "PASS" if converged else "WARNING",
        "family": model.family.value,
        "states": {v.name: float(v.initial) for v in model.variables if v.initial is not None},
        "parameters": posterior_parameters,
        "posterior": posterior,
        "posterior_predictive": ppc,
        "solver": {"backend": "builtin", "method": "multi_chain_random_walk_metropolis", "seed": int(seed)},
        "diagnostics": {
            "chains": chains_n, "draws_per_chain": draws, "burn_per_chain": burn,
            "acceptance_rate_by_chain": acceptance, "converged": converged,
            "criteria": "split-Rhat <= 1.05 and ESS >= max(100, 1% total draws)",
            "parameters": diagnostics,
        },
    }
    if bool(cfg.get("return_samples", False)):
        result["samples"] = {p.name: chain[:, :, i].tolist() for i, p in enumerate(sampled_parameters)}
    return result
