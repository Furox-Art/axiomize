"""Deterministic echo provider for tests and offline use."""

from __future__ import annotations

from typing import Any, ClassVar

from axiomize.providers.base import ModelProvider


class EchoProvider(ModelProvider):
    name: ClassVar[str] = "echo"
    capabilities: ClassVar[list[str]] = ["generate", "structured"]
    context_limit = 1_000_000
    supports_tools = False
    supports_structured_output = True

    def generate(self, prompt: str) -> str:
        return f"echo: {prompt}"

    def generate_structured(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        _ = prompt
        out: dict[str, Any] = {}
        for key in schema.get("properties", {}):
            prop = schema["properties"][key]
            out[key] = 0.0 if prop.get("type") == "number" else None
        for key in schema.get("required", []):
            out.setdefault(key, None)
        return out

    def health_check(self) -> bool:
        return True
