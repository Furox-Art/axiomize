"""Bayesian inference (PHASE 4).

A dependency-free Metropolis-Hastings sampler is the built-in backend
(seeded, reproducible). PyMC is probed as the preferred backend when
installed; otherwise the router falls back here and says so.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np


def metropolis_hastings(log_posterior: Callable[[np.ndarray], float],
                        x0: np.ndarray, n_samples: int = 5000,
                        burn: int = 1000, proposal_std: float = 0.5,
                        seed: int = 0) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    current = np.asarray(x0, dtype=float)
    current_lp = float(log_posterior(current))
    chain = np.zeros((n_samples, current.size))
    accepted = 0
    for i in range(n_samples):
        proposal = current + rng.normal(0, proposal_std, size=current.shape)
        proposal_lp = float(log_posterior(proposal))
        if np.log(rng.random()) < proposal_lp - current_lp:
            current, current_lp = proposal, proposal_lp
            accepted += 1
        chain[i] = current
    posterior = chain[burn:]
    return {"samples": posterior, "acceptance_rate": accepted / n_samples,
            "mean": posterior.mean(axis=0), "std": posterior.std(axis=0)}


def normal_mean_posterior(y: np.ndarray, sigma: float,
                          prior_mean: float = 0.0, prior_std: float = 10.0,
                          n_samples: int = 5000, burn: int = 1000,
                          seed: int = 0) -> dict[str, Any]:
    y = np.asarray(y, dtype=float)

    def log_posterior(theta: np.ndarray) -> float:
        mu = theta[0]
        ll = -0.5 * np.sum(((y - mu) / sigma) ** 2)
        lp = -0.5 * ((mu - prior_mean) / prior_std) ** 2
        return float(ll + lp)

    out = metropolis_hastings(log_posterior, np.array([np.mean(y)]),
                              n_samples=n_samples, burn=burn,
                              proposal_std=sigma / np.sqrt(len(y)), seed=seed)
    draws = out["samples"][:, 0]
    return {"mean": float(out["mean"][0]), "std": float(out["std"][0]),
            "ci95": (float(np.percentile(draws, 2.5)),
                     float(np.percentile(draws, 97.5))),
            "acceptance_rate": out["acceptance_rate"]}
