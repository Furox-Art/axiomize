"""Standard ScientificTool interface (PHASE 1 core).

Every scientific backend (symbolic, numerical, optimization, ...) speaks
through this contract so workflow code never embeds tool-specific logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass
class ToolMetadata:
    name: str
    capabilities: list[str] = field(default_factory=list)
    version: str = "unknown"
    available: bool = False
    reason: str = ""


class ScientificTool(ABC):
    """Common contract for all scientific backends."""

    name: ClassVar[str] = "base"
    capabilities: ClassVar[list[str]] = []

    @classmethod
    def availability(cls) -> ToolMetadata:
        """Probe whether the backend is really installed. Never guess."""
        try:
            version = cls._probe_version()
        except Exception as exc:  # noqa: BLE001 - any import/link failure means unavailable
            return ToolMetadata(name=cls.name, capabilities=list(cls.capabilities),
                                available=False, reason=str(exc))
        return ToolMetadata(name=cls.name, capabilities=list(cls.capabilities),
                            version=version, available=True)

    @classmethod
    def _probe_version(cls) -> str:
        raise NotImplementedError

    @abstractmethod
    def validate_input(self, payload: dict[str, Any]) -> None:
        """Raise ValueError on malformed input before any computation."""

    @abstractmethod
    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run the computation; return a JSON-serializable result dict."""

    def validate_output(self, result: dict[str, Any]) -> None:
        """Hook for output sanity checks; default accepts anything dict-like."""
        if not isinstance(result, dict):
            raise TypeError(f"{self.name}: result must be a dict")

    def metadata(self) -> ToolMetadata:
        meta = self.availability()
        meta.capabilities = list(self.capabilities)
        return meta
