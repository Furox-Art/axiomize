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
        import pymc  # type: ignore[import-untyped]

        return str(pymc.__version__)

    def validate_input(self, payload: dict[str, Any]) -> None:
        if "model" not in payload:
            raise ValueError("pymc: payload needs a 'model' description")

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_input(payload)
        meta = self.availability()
        if not meta.available:
            raise RuntimeError(
                "pymc is not installed; use axiomize.bayesian.mh instead")
        raise NotImplementedError("pymc model execution lands in a later phase")
