"""PyMC preferred-backend probe (PHASE 4).

If PyMC is installed the router may select it; otherwise availability() reports
False and the built-in Metropolis-Hastings sampler is the honest fallback.
Direct tool calls enforce hard draw/data ceilings independently of approval.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar

from axiomize.limits import MAX_ARRAY_ITEMS, MAX_BAYES_DRAWS, bounded_int
from axiomize.tools.base import ScientificTool

_MAX_LIKELIHOOD_WORK = 50_000_000


def _finite(value: Any, *, name: str, positive: bool = False) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"pymc: {name} must be numeric") from exc
    if not math.isfinite(out) or (positive and out <= 0):
        requirement = "finite and positive" if positive else "finite"
        raise ValueError(f"pymc: {name} must be {requirement}")
    return out


class PyMCTool(ScientificTool):
    name: ClassVar[str] = "pymc"
    capabilities: ClassVar[list[str]] = ["bayesian_inference", "mcmc", "credible_intervals"]

    @classmethod
    def _probe_version(cls) -> str:
        import importlib
        pymc = importlib.import_module("pymc")
        return str(getattr(pymc, "__version__", "unknown"))

    def validate_input(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict) or "model" not in payload:
            raise ValueError("pymc: payload needs a 'model' description")
        if payload.get("model") == "normal-mean" and "y" not in payload:
            raise ValueError("pymc: normal-mean needs observed data under 'y'")

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_input(payload)
        meta = self.availability()
        if not meta.available:
            reason = meta.reason or "No module named 'pymc'"
            raise RuntimeError(
                f"TOOL_UNAVAILABLE: pymc is not installed ({reason}); use axiomize.bayesian.mh instead"
            )
        model = payload.get("model")
        if model == "normal-mean":
            result = self._run_normal_mean(payload)
            self.validate_output(result)
            return result
        raise NotImplementedError(f"pymc model {model!r} is not implemented yet; available: 'normal-mean'")

    @staticmethod
    def _run_normal_mean(payload: dict[str, Any]) -> dict[str, Any]:
        import numpy as np
        import pymc as pm

        try:
            y = np.asarray(payload["y"], dtype=float)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("pymc: 'y' must be a numeric 1D observation array") from exc
        if y.ndim != 1:
            raise ValueError("pymc: 'y' must be one-dimensional; multidimensional data are not silently flattened")
        if y.size == 0 or y.size > MAX_ARRAY_ITEMS:
            raise ValueError(f"pymc: 'y' must contain 1..{MAX_ARRAY_ITEMS} observations")
        if not np.all(np.isfinite(y)):
            raise ValueError("pymc: 'y' must contain only finite values")
        sigma = _finite(payload.get("sigma", 1.0), name="sigma", positive=True)
        prior_mu = _finite(payload.get("prior_mu", 0.0), name="prior_mu")
        prior_sigma = _finite(payload.get("prior_sigma", 10.0), name="prior_sigma", positive=True)
        draws = bounded_int(payload.get("draws", 500), name="pymc.draws", minimum=1, maximum=MAX_BAYES_DRAWS)
        tune = bounded_int(payload.get("tune", 500), name="pymc.tune", minimum=1, maximum=MAX_BAYES_DRAWS)
        if (draws + tune) * int(y.size) > _MAX_LIKELIHOOD_WORK:
            raise ValueError(f"pymc: request exceeds hard likelihood work limit {_MAX_LIKELIHOOD_WORK}")
        seed = bounded_int(payload.get("seed", 0), name="pymc.seed", minimum=0, maximum=2**32 - 1)

        with pm.Model():
            mu = pm.Normal("mu", mu=prior_mu, sigma=prior_sigma)
            pm.Normal("obs", mu=mu, sigma=sigma, observed=y)
            trace = pm.sample(
                draws=draws,
                tune=tune,
                chains=2,
                cores=1,
                progressbar=False,
                random_seed=seed,
            )

        mu_samples = np.asarray(trace.posterior["mu"].to_numpy(), dtype=float).ravel()
        expected_samples = 2 * draws
        if mu_samples.size != expected_samples or not np.all(np.isfinite(mu_samples)):
            raise RuntimeError(
                f"pymc returned malformed/non-finite posterior samples: expected {expected_samples}, got {mu_samples.size}"
            )
        r_hat: Any = ""
        ess_bulk: Any = ""
        diag_note = ""
        try:
            import arviz as az  # type: ignore[import-untyped]
            r_hat = float(az.rhat(trace.posterior["mu"]).to_numpy().max())
            ess_bulk = float(az.ess(trace.posterior["mu"]).to_numpy().min())
        except Exception as exc:  # diagnostic add-on must not invalidate a valid posterior
            diag_note = f"diagnostics unavailable: {type(exc).__name__}: {exc}"
        status = "PASS"
        if isinstance(r_hat, float) and (not math.isfinite(r_hat) or r_hat > 1.05):
            status = "WARNING"
        return {
            "status": status,
            "model": "normal-mean",
            "backend": f"pymc-{getattr(pm, '__version__', 'unknown')}",
            "n_obs": int(y.size),
            "draws": draws,
            "tune": tune,
            "chains": 2,
            "seed": seed,
            "posterior_mean": float(np.mean(mu_samples)),
            "posterior_sd": float(np.std(mu_samples)),
            "ci95": [float(np.quantile(mu_samples, 0.025)), float(np.quantile(mu_samples, 0.975))],
            "r_hat": r_hat,
            "ess_bulk": ess_bulk,
            "diagnostics_note": diag_note,
        }
