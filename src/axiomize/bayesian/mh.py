"""Bayesian inference (PHASE 4).

A dependency-free Metropolis-Hastings sampler is the built-in backend
(seeded, reproducible). Every direct call enforces the same hard allocation
ceilings as the general Model IR engine.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np

from axiomize.limits import (
    MAX_ARRAY_ITEMS,
    MAX_BAYES_DRAWS,
    MAX_MODEL_PARAMETERS,
    bounded_int,
    enforce_result_cells,
)


def _finite_positive(value: Any, *, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return result


def metropolis_hastings(
    log_posterior: Callable[[np.ndarray], float],
    x0: np.ndarray,
    n_samples: int = 5000,
    burn: int = 1000,
    proposal_std: float = 0.5,
    seed: int = 0,
) -> dict[str, Any]:
    n_samples = bounded_int(n_samples, name="n_samples", minimum=2, maximum=MAX_BAYES_DRAWS)
    burn = bounded_int(burn, name="burn", minimum=0, maximum=n_samples - 1)
    proposal_std = _finite_positive(proposal_std, name="proposal_std")
    current = np.asarray(x0, dtype=float)
    if current.ndim != 1 or current.size == 0:
        raise ValueError("x0 must be a non-empty 1D numeric array")
    if current.size > MAX_MODEL_PARAMETERS:
        raise ValueError(f"x0 dimension exceeds hard limit {MAX_MODEL_PARAMETERS}")
    if not np.all(np.isfinite(current)):
        raise ValueError("x0 must contain only finite values")
    enforce_result_cells(n_samples, int(current.size), name="Metropolis-Hastings chain")

    rng = np.random.default_rng(seed)
    current_lp = float(log_posterior(current.copy()))
    if not math.isfinite(current_lp):
        raise ValueError("log_posterior(x0) must be finite")
    chain = np.empty((n_samples, current.size), dtype=float)
    accepted = 0
    for i in range(n_samples):
        proposal = current + rng.normal(0, proposal_std, size=current.shape)
        proposal_lp = float(log_posterior(proposal.copy()))
        # A non-finite proposed density is outside the supported posterior
        # domain and is rejected deterministically rather than poisoning the
        # chain with NaN arithmetic.
        if math.isfinite(proposal_lp) and np.log(rng.random()) < proposal_lp - current_lp:
            current, current_lp = proposal, proposal_lp
            accepted += 1
        chain[i] = current
    posterior = chain[burn:]
    return {
        "samples": posterior,
        "acceptance_rate": accepted / n_samples,
        "mean": posterior.mean(axis=0),
        "std": posterior.std(axis=0),
    }


def normal_mean_posterior(
    y: np.ndarray,
    sigma: float,
    prior_mean: float = 0.0,
    prior_std: float = 10.0,
    n_samples: int = 5000,
    burn: int = 1000,
    seed: int = 0,
) -> dict[str, Any]:
    y = np.asarray(y, dtype=float)
    if y.ndim != 1 or y.size == 0 or y.size > MAX_ARRAY_ITEMS:
        raise ValueError(f"y must be a non-empty 1D array with at most {MAX_ARRAY_ITEMS} values")
    if not np.all(np.isfinite(y)):
        raise ValueError("y must contain only finite values")
    sigma = _finite_positive(sigma, name="sigma")
    prior_std = _finite_positive(prior_std, name="prior_std")
    try:
        prior_mean = float(prior_mean)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("prior_mean must be numeric") from exc
    if not math.isfinite(prior_mean):
        raise ValueError("prior_mean must be finite")

    def log_posterior(theta: np.ndarray) -> float:
        mu = theta[0]
        ll = -0.5 * np.sum(((y - mu) / sigma) ** 2)
        lp = -0.5 * ((mu - prior_mean) / prior_std) ** 2
        return float(ll + lp)

    out = metropolis_hastings(
        log_posterior,
        np.array([np.mean(y)]),
        n_samples=n_samples,
        burn=burn,
        proposal_std=sigma / np.sqrt(len(y)),
        seed=seed,
    )
    draws = out["samples"][:, 0]
    return {
        "mean": float(out["mean"][0]),
        "std": float(out["std"][0]),
        "ci95": (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))),
        "acceptance_rate": out["acceptance_rate"],
    }
