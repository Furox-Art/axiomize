"""Package-native Bayesian convergence diagnostics and posterior predictive checks."""
from __future__ import annotations

import math
from typing import Any

import numpy as np


def _autocorrelation(x: np.ndarray, max_lag: int) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    x = x - np.mean(x)
    variance = float(np.dot(x, x))
    if variance <= 0 or not math.isfinite(variance):
        return np.zeros(max_lag + 1, dtype=float)
    result = np.empty(max_lag + 1, dtype=float); result[0] = 1.0
    for lag in range(1, max_lag + 1):
        result[lag] = float(np.dot(x[:-lag], x[lag:]) / variance)
    return result


def split_rhat(chains: np.ndarray) -> float:
    chains = np.asarray(chains, dtype=float)
    if chains.ndim != 2 or chains.shape[0] < 2 or chains.shape[1] < 4:
        return float("nan")
    half = chains.shape[1] // 2
    split = np.concatenate([chains[:, :half], chains[:, -half:]], axis=0)
    n = split.shape[1]
    means = np.mean(split, axis=1)
    within = float(np.mean(np.var(split, axis=1, ddof=1)))
    between = n * float(np.var(means, ddof=1))
    if within <= 0:
        return 1.0 if between <= 0 else float("inf")
    var_hat = (n - 1) / n * within + between / n
    return float(math.sqrt(max(var_hat / within, 0.0)))


def effective_sample_size(chains: np.ndarray) -> float:
    chains = np.asarray(chains, dtype=float)
    if chains.ndim != 2 or chains.shape[1] < 4:
        return float("nan")
    m, n = chains.shape
    max_lag = min(n - 1, 1000)
    rhos = np.mean(np.vstack([_autocorrelation(row, max_lag) for row in chains]), axis=0)
    total = 0.0
    # Geyer's initial-positive paired sequence.
    for lag in range(1, max_lag, 2):
        pair = float(rhos[lag] + (rhos[lag + 1] if lag + 1 <= max_lag else 0.0))
        if pair <= 0:
            break
        total += pair
    ess = m * n / max(1.0 + 2.0 * total, 1e-12)
    return float(min(max(1.0, ess), m * n))


def posterior_diagnostics(chains: np.ndarray, names: list[str]) -> dict[str, Any]:
    values = np.asarray(chains, dtype=float)
    if values.ndim != 3 or values.shape[2] != len(names):
        raise ValueError("Bayesian chains must have shape [chains, draws, parameters]")
    result: dict[str, Any] = {}
    overall = "PASS"
    for index, name in enumerate(names):
        x = values[:, :, index]
        flat = x.reshape(-1)
        rhat = split_rhat(x)
        ess = effective_sample_size(x)
        sd = float(np.std(flat, ddof=1)) if flat.size > 1 else 0.0
        mcse = sd / math.sqrt(max(ess, 1.0))
        status = "PASS"
        if not math.isfinite(rhat) or rhat > 1.05 or ess < max(50.0, 0.05 * flat.size):
            status = "WARNING"
            overall = "WARNING"
        result[name] = {
            "r_hat": rhat,
            "ess_bulk": ess,
            "mcse_mean": mcse,
            "mean": float(np.mean(flat)),
            "sd": sd,
            "hdi95": [float(np.quantile(flat, 0.025)), float(np.quantile(flat, 0.975))],
            "status": status,
        }
    return {"status": overall, "parameters": result}


def normal_posterior_predictive(*, observed: np.ndarray, means: np.ndarray, sigmas: np.ndarray,
                                seed: int, max_replications: int = 1000) -> dict[str, Any]:
    observed = np.asarray(observed, dtype=float)
    means = np.asarray(means, dtype=float)
    sigmas = np.asarray(sigmas, dtype=float)
    if means.ndim != 2 or means.shape[1] != observed.size:
        raise ValueError("PPC means must have shape [draws, observations]")
    if sigmas.ndim != 1 or sigmas.size != means.shape[0]:
        raise ValueError("PPC sigma vector must match posterior draws")
    count = min(max_replications, means.shape[0])
    if count < 10:
        raise ValueError("PPC requires at least 10 posterior draws")
    indices = np.linspace(0, means.shape[0] - 1, count, dtype=int)
    rng = np.random.default_rng(seed)
    replicated = rng.normal(means[indices], sigmas[indices, None])
    pred_mean = np.mean(replicated, axis=0)
    lo90, hi90 = np.quantile(replicated, [0.05, 0.95], axis=0)
    lo95, hi95 = np.quantile(replicated, [0.025, 0.975], axis=0)
    obs_mean, obs_sd = float(np.mean(observed)), float(np.std(observed, ddof=1))
    rep_means = np.mean(replicated, axis=1); rep_sds = np.std(replicated, axis=1, ddof=1)
    return {
        "status": "PASS",
        "replications": int(count),
        "seed": int(seed),
        "predictive_rmse": float(np.sqrt(np.mean((pred_mean - observed) ** 2))),
        "coverage90": float(np.mean((observed >= lo90) & (observed <= hi90))),
        "coverage95": float(np.mean((observed >= lo95) & (observed <= hi95))),
        "bayesian_p_values": {
            "mean": float(np.mean(rep_means >= obs_mean)),
            "std": float(np.mean(rep_sds >= obs_sd)),
        },
        "observed_summary": {"mean": obs_mean, "std": obs_sd},
        "replicated_summary": {
            "mean_of_means": float(np.mean(rep_means)),
            "mean_of_stds": float(np.mean(rep_sds)),
        },
    }
