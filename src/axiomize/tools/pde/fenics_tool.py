"""FEniCS adapter slot (PHASE 6).

The native Axiomize PDE engine is the supported executor. Merely detecting a
FEniCS import is not enough to advertise a runnable backend: this adapter does
not yet implement safe weak-form execution, so availability is honestly false.
"""

from __future__ import annotations

from typing import Any, ClassVar

from axiomize.tools.base import ScientificTool, ToolMetadata


class FEniCSAdapter(ScientificTool):
    name: ClassVar[str] = "fenics"
    capabilities: ClassVar[list[str]] = ["fem", "pde_weak_form"]

    @classmethod
    def _probe_version(cls) -> str:
        import fenics  # type: ignore[import-untyped]
        return str(getattr(fenics, "__version__", "unknown"))

    @classmethod
    def availability(cls) -> ToolMetadata:
        try:
            version = cls._probe_version()
            detail = f"FEniCS {version} detected, but Axiomize weak-form execution is not implemented"
        except Exception as exc:
            detail = f"FEniCS execution unavailable: {exc}"
        return ToolMetadata(
            name=cls.name,
            capabilities=list(cls.capabilities),
            available=False,
            reason=detail + "; use the native bounded PDE executor",
        )

    def validate_input(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict) or "weak_form" not in payload:
            raise ValueError("fenics: payload needs a 'weak_form' description")

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_input(payload)
        raise RuntimeError(
            "TOOL_UNAVAILABLE: Axiomize does not yet implement FEniCS weak-form execution; "
            "use the native bounded PDE executor"
        )
