"""FEniCS adapter slot (PHASE 6).

FEniCS is not pip-installable on all platforms (notably Windows), so
this adapter honestly reports TOOL_UNAVAILABLE until a real backend is
present. The FTCS solver in :mod:`axiomize.pde.diffusion` is the
built-in fallback for 1D parabolic problems.
"""

from __future__ import annotations

from typing import Any, ClassVar

from axiomize.tools.base import ScientificTool


class FEniCSAdapter(ScientificTool):
    name: ClassVar[str] = "fenics"
    capabilities: ClassVar[list[str]] = ["fem", "pde_weak_form"]

    @classmethod
    def _probe_version(cls) -> str:
        import fenics  # type: ignore[import-untyped]

        return str(getattr(fenics, "__version__", "unknown"))

    def validate_input(self, payload: dict[str, Any]) -> None:
        if "weak_form" not in payload:
            raise ValueError("fenics: payload needs a 'weak_form' description")

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_input(payload)
        raise RuntimeError("fenics backend is not installed in this environment")
