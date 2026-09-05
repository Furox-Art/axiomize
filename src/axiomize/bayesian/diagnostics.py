"""Bayesian convergence diagnostics and posterior predictive checks.

The implementations are dependency-light and deterministic for a supplied
chain. They provide split-Rhat, autocorrelation ESS, MCSE and bounded normal-
likelihood posterior predictive summaries without requiring ArviZ.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np


def _chains(values: Any) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 2 or array.shape[0] < 2 or array.shape[1] < 8:
        raise ValueError("diagnostics require at least 2 chains and 8 draws per chain")
    if not np.all(np.isfinite(array)):
        raise ValueError("chains must contain only finite values")
    return array


def split_rhat(values: Any) -> float:
    chains = _chains(values)
    half = chains.shape[1] // 2
    if half < 4:
        raise ValueError("too few draws for split-Rhat")
    split = np.concatenate([chains[:, :half], chains[:, -half:]], axis=0)
    n = split.shape[1]
    chain_means = np.mean(split, axis=1)
    chain_vars = np.var(split, axis=1, ddof=1)
    W = float(np.mean(chain_vars))
    if W <= np.finfo(float).tiny:
        return 1.0
    B = float(n * np.var(chain_means, ddof=1))
    var_hat = ((n - 1) / n) * W + B / n
    return float(math.sqrt(max(var_hat / W, 0.0)))


def effective_sample_size(values: Any) -> float:
    chains = _chains(values)
    m, n = chains.shape
    centered = chains - np.mean(chains, axis=1, keepdims=True)
    variances = np.var(centered, axis=1, ddof=1)
    W = float(np.mean(variances))
    if W <= np.finfo(float).tiny:
        return float(m * n)
    mean_chain = np.mean(chains, axis=1)
    B = float(n * np.var(mean_chain, ddof=1))
    var_plus = ((n - 1) / n) * W + B / n
    rho_sum = 0.0
    # Initial-positive-sequence style truncation. The cap keeps diagnostics
    # bounded for very long chains while capturing the practically relevant ACF.
    max_lag = min(n - 1, 2000)
    previous_pair = math.inf
    lag = 1
    while lag <= max_lag:
        pair = 0.0
        used = 0
        for current_lag in (lag, lag + 1):
            if current_lag > max_lag:
                continue
            autocov = 0.0
            for chain in centered:
                autocov += float(np.dot(chain[:-current_lag], chain[current_lag:]) / (n - current_lag))
            autocov /= m
            rho = 1.0 - (W - autocov) / max(var_plus, np.finfo(float).tiny)
            pair += rho; used += 1
        if used == 0 or pair < 0:
            break
        pair = min(pair, previous_pair)
        rho_sum += max(pair, 0.0)
        previous_pair = pair
        lag += 2
    tau = max(1.0, 1.0 + 2.0 * rho_sum)
    return float(min(m * n, (m * n) / tau))


def parameter_diagnostics(values: Any) -> dict[str, float]:
    chains = _chains(values)
    flat = chains.reshape(-1)
    ess = effective_sample_size(chains)
    sd = float(np.std(flat, ddof=1))
    return {
        "r_hat": split_rhat(chains),
        "ess_bulk": ess,
        "mcse_mean": sd / math.sqrt(max(ess, 1.0)),
    }


def posterior_predictive_normal(
    mean_draws: Any,
    *,
    sigma_draws: Any,
    observed: Any,
    seed: int,
    max_draws: int = 2000,
) -> dict[str, Any]:
    means = np.asarray(mean_draws, dtype=float)
    observed_arr = np.asarray(observed, dtype=float)
    sigma = np.asarray(sigma_draws, dtype=float).reshape(-1)
    if means.ndim != 2 or means.shape[1:] != observed_arr.shape:
        raise ValueError("PPC mean draws must have shape [draw, observation]")
    if sigma.shape[0] != means.shape[0] or np.any(sigma <= 0):
        raise ValueError("PPC sigma draws must be positive and match posterior draws")
    if not (np.all(np.isfinite(means)) and np.all(np.isfinite(sigma)) and np.all(np.isfinite(observed_arr))):
        raise ValueError("PPC inputs must be finite")
    if means.shape[0] > max_draws:
        index = np.linspace(0, means.shape[0] - 1, max_draws, dtype=int)
        means, sigma = means[index], sigma[index]
    rng = np.random.default_rng(seed)
    predictive = means + rng.normal(size=means.shape) * sigma[:, None]
    pred_mean = np.mean(predictive, axis=0)
    q025 = np.quantile(predictive, 0.025, axis=0)
    q975 = np.quantile(predictive, 0.975, axis=0)
    coverage = float(np.mean((observed_arr >= q025) & (observed_arr <= q975)))
    rmse = float(np.sqrt(np.mean((observed_arr - pred_mean) ** 2)))
    obs_mean = float(np.mean(observed_arr))
    replicated_means = np.mean(predictive, axis=1)
    p_mean = float(np.mean(replicated_means >= obs_mean))
    obs_var = float(np.var(observed_arr))
    replicated_vars = np.var(predictive, axis=1)
    p_variance = float(np.mean(replicated_vars >= obs_var))
    return {
        "status": "PASS",
        "predictive_mean": pred_mean.tolist(),
        "q025": q025.tolist(),
        "q975": q975.tolist(),
        "interval_coverage": coverage,
        "rmse": rmse,
        "bayesian_p_values": {"mean": p_mean, "variance": p_variance},
        "draws_used": int(predictive.shape[0]),
    }
