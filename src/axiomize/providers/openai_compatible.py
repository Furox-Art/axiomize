"""OpenAI-compatible provider adapter (dependency-free, urllib)."""

from __future__ import annotations

import json
import urllib.request
from typing import Any, ClassVar

from axiomize.providers.base import ModelProvider


class OpenAICompatibleProvider(ModelProvider):
    name: ClassVar[str] = "openai_compatible"
    capabilities: ClassVar[list[str]] = ["generate", "structured"]
    context_limit = 128_000
    supports_tools = True
    supports_structured_output = True

    def __init__(self, base_url: str, model: str = "default", api_key: str = "",
                 timeout_s: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_s = timeout_s

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            self.base_url + path, data=json.dumps(payload).encode(),
            headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            return json.loads(resp.read().decode())

    def generate(self, prompt: str) -> str:
        body = self._post("/chat/completions", {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}]})
        return str(body["choices"][0]["message"]["content"])

    def generate_structured(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        body = self._post("/chat/completions", {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "axiomize",
                                                "schema": schema}}})
        return json.loads(body["choices"][0]["message"]["content"])

    def health_check(self) -> bool:
        try:
            req = urllib.request.Request(self.base_url + "/models", method="GET")
            if self.api_key:
                req.add_header("Authorization", f"Bearer {self.api_key}")
            with urllib.request.urlopen(req, timeout=min(self.timeout_s, 5.0)) as resp:
                return resp.status == 200
        except Exception:  # noqa: BLE001 - unreachable means unhealthy
            return False
