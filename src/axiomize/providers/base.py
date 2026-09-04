"""AI provider abstraction (PHASE 9).

Providers are clients of the scientific engine, never its core.
The engine runs deterministically without any provider at all.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar


class ModelProvider(ABC):
    """Contract every AI-provider adapter implements."""

    name: ClassVar[str] = "base"
    capabilities: ClassVar[list[str]] = []
    context_limit: int = 0
    supports_tools: bool = False
    supports_structured_output: bool = False

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Free-form completion."""

    @abstractmethod
    def generate_structured(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Completion conforming to a JSON schema."""

    @abstractmethod
    def health_check(self) -> bool:
        """True when the provider is reachable and usable."""

    def complete(self, prompt: str) -> dict[str, Any]:
        """Backward-compatible structured completion wrapper."""
        return {"text": self.generate(prompt), "provider": self.name}

    def healthcheck(self) -> bool:
        """Backward-compatible health-check alias."""
        return self.health_check()
