"""PyMC preferred-backend probe (PHASE 4).

If PyMC is installed the router may select it; otherwise availability()
reports False and the built-in Metropolis-Hastings sampler in
:mod:`axiomize.bayesian.mh` is the honest fallback.
"""

from __future__ import annotations

from typing import Any, ClassVar

from axiomize.tools.base import ScientificTool


class PyMCTool(ScientificTool):
    name: ClassVar[str] = "pymc"
    capabilities: ClassVar[list[str]] = ["bayesian_inference", "mcmc", "credible_intervals"]

    @classmethod
    def _probe_version(cls) -> str:
        import importlib

        pymc = importlib.import_module("pymc")

        return str(getattr(pymc, "__version__", "unknown"))

    def validate_input(self, payload: dict[str, Any]) -> None:
        if "model" not in payload:
            raise ValueError("pymc: payload needs a 'model' description")
        if payload.get("model") == "normal-mean" and "y" not in payload:
            raise ValueError("pymc: normal-mean needs observed data under 'y'")

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_input(payload)
        meta = self.availability()
        if not meta.available:
            reason = meta.reason or "No module named 'pymc'"
            raise RuntimeError(
                f"TOOL_UNAVAILABLE: pymc is not installed ({reason}); "
                "use axiomize.bayesian.mh instead")
        model = payload.get("model")
        if model == "normal-mean":
            result = self._run_normal_mean(payload)
            self.validate_output(result)
            return result
        raise NotImplementedError(
            f"pymc model {model!r} is not implemented yet; available: 'normal-mean'")

    @staticmethod
    def _run_normal_mean(payload: dict[str, Any]) -> dict[str, Any]:
        """Gercek NUTS orneklemesi: y ~ Normal(mu, sigma), mu bilinmiyor."""
        import numpy as np
        import pymc as pm

        y = np.asarray(payload["y"], dtype=float).ravel()
        if y.size == 0:
            raise ValueError("pymc: normal-mean needs non-empty 'y'")
        if not np.all(np.isfinite(y)):
            raise ValueError("pymc: 'y' must contain only finite values")
        sigma = float(payload.get("sigma", 1.0))
        if sigma <= 0:
            raise ValueError("pymc: 'sigma' must be positive")
        draws = int(payload.get("draws", 500))
        tune = int(payload.get("tune", 500))
        seed = int(payload.get("seed", 0))
        if draws <= 0 or tune <= 0:
            raise ValueError("pymc: 'draws' and 'tune' must be positive")

        with pm.Model():
            mu = pm.Normal("mu", mu=float(payload.get("prior_mu", 0.0)),
                           sigma=float(payload.get("prior_sigma", 10.0)))
            pm.Normal("obs", mu=mu, sigma=sigma, observed=y)
            trace = pm.sample(draws=draws, tune=tune, chains=2, cores=1,
                              progressbar=False, random_seed=seed)

        mu_samples = trace.posterior["mu"].to_numpy().ravel()
        r_hat: Any = ""
        ess_bulk: Any = ""
        diag_note = ""
        try:
            import arviz as az  # type: ignore[import-untyped]

            r_hat = float(az.rhat(trace.posterior["mu"]).to_numpy().max())
            ess_bulk = float(az.ess(trace.posterior["mu"]).to_numpy().min())
        except Exception as exc:  # noqa: BLE001 - teshis yoksa sonuc yine gecerli, nedeni kaydedilir
            diag_note = f"diagnostics unavailable: {exc}"
        status = "PASS"
        if isinstance(r_hat, float) and r_hat > 1.05:
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
            "ci95": [float(np.quantile(mu_samples, 0.025)),
                     float(np.quantile(mu_samples, 0.975))],
            "r_hat": r_hat,
            "ess_bulk": ess_bulk,
            "diagnostics_note": diag_note,
        }
