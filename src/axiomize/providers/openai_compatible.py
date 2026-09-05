"""OpenAI-compatible provider adapter (dependency-free, urllib).

Provider endpoints are explicit caller configuration, but the adapter still
prevents unsafe URL schemes, credential-bearing redirect hops and unbounded
response reads. Local/private HTTP endpoints remain supported intentionally for
self-hosted model servers.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, ClassVar

from axiomize.limits import MAX_JSON_BYTES, MAX_PROVIDER_RESPONSE_BYTES
from axiomize.providers.base import ModelProvider


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


_OPENER = urllib.request.build_opener(_NoRedirect())


def _validate_base_url(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("base_url must be a non-empty URL")
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("base_url scheme must be http or https")
    if not parsed.hostname:
        raise ValueError("base_url must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("base_url must not embed credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("base_url must not contain query or fragment components")
    normalized = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
    return normalized


def _read_json_response(resp: Any) -> dict[str, Any]:
    raw = resp.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
    if len(raw) > MAX_PROVIDER_RESPONSE_BYTES:
        raise ValueError(f"provider response exceeds hard limit of {MAX_PROVIDER_RESPONSE_BYTES} bytes")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"provider returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("provider response must be a JSON object")
    return payload


class OpenAICompatibleProvider(ModelProvider):
    name: ClassVar[str] = "openai_compatible"
    capabilities: ClassVar[list[str]] = ["generate", "structured"]
    context_limit = 128_000
    supports_tools = True
    supports_structured_output = True

    def __init__(self, base_url: str, model: str = "default", api_key: str = "",
                 timeout_s: float = 30.0) -> None:
        self.base_url = _validate_base_url(base_url)
        self.model = str(model)
        if not self.model or len(self.model) > 512:
            raise ValueError("model must be a non-empty string <= 512 characters")
        self.api_key = str(api_key)
        timeout = float(timeout_s)
        if not math.isfinite(timeout) or timeout <= 0 or timeout > 300:
            raise ValueError("timeout_s must be finite and in (0, 300]")
        self.timeout_s = timeout

    def _url(self, path: str) -> str:
        if not isinstance(path, str) or not path.startswith("/") or "?" in path or "#" in path:
            raise ValueError("provider path must be an absolute path without query/fragment")
        return self.base_url + path

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_JSON_BYTES:
            raise ValueError(f"provider request exceeds hard limit of {MAX_JSON_BYTES} bytes")
        req = urllib.request.Request(self._url(path), data=encoded, headers=self._headers(), method="POST")
        try:
            with _OPENER.open(req, timeout=self.timeout_s) as resp:
                if int(getattr(resp, "status", 200)) < 200 or int(getattr(resp, "status", 200)) >= 300:
                    raise ValueError(f"provider returned HTTP {getattr(resp, 'status', 'unknown')}")
                return _read_json_response(resp)
        except urllib.error.HTTPError as exc:
            # Redirects are intentionally rejected so Authorization can never be
            # forwarded to a different origin by urllib.
            if 300 <= exc.code < 400:
                raise ValueError(f"provider redirects are not allowed (HTTP {exc.code})") from exc
            raise ValueError(f"provider request failed with HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ValueError(f"provider connection failed: {exc.reason}") from exc

    def generate(self, prompt: str) -> str:
        if not isinstance(prompt, str):
            raise ValueError("prompt must be a string")
        body = self._post("/chat/completions", {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        })
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("provider response is missing choices[0].message.content") from exc
        return str(content)

    def generate_structured(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(prompt, str) or not isinstance(schema, dict):
            raise ValueError("prompt must be a string and schema must be an object")
        body = self._post("/chat/completions", {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "axiomize", "schema": schema}},
        })
        try:
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("provider did not return valid structured JSON content") from exc
        if not isinstance(parsed, dict):
            raise ValueError("structured provider output must be a JSON object")
        return parsed

    def health_check(self) -> bool:
        try:
            req = urllib.request.Request(self._url("/models"), headers=self._headers(), method="GET")
            with _OPENER.open(req, timeout=min(self.timeout_s, 5.0)) as resp:
                if int(getattr(resp, "status", 0)) != 200:
                    return False
                # Bound even health responses; no need to parse the whole body.
                raw = resp.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
                return len(raw) <= MAX_PROVIDER_RESPONSE_BYTES
        except Exception:  # noqa: BLE001 - unreachable/malformed means unhealthy
            return False
