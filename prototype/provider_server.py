from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass, asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


HOST = os.getenv("AXIOMIZE_PROVIDER_HOST", "127.0.0.1")
PORT = int(os.getenv("AXIOMIZE_PROVIDER_PORT", "8787"))


@dataclass(frozen=True)
class SkillDescriptor:
    id: str
    name: str
    version: str
    entrypoint: str
    description: str


SKILLS: dict[str, SkillDescriptor] = {
    "axiomize": SkillDescriptor(
        id="axiomize",
        name="Axiomize",
        version="git:prototype/hosted-scientific-provider",
        entrypoint="skills/axiomize/SKILL.md",
        description="Rigorous mathematical modeling, fitting, validation, and falsification workflow.",
    )
}

# Prototype only. Sessions intentionally disappear when the process restarts.
SESSIONS: dict[str, dict[str, Any]] = {}


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _read_skill_text(skill: SkillDescriptor) -> str:
    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / skill.entrypoint
    return path.read_text(encoding="utf-8")


def _build_openai_compatible_request(
    *, base_url: str, model: str, api_key: str, skill_text: str, user_prompt: str
) -> tuple[str, dict[str, str], bytes]:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": skill_text,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
    }
    return endpoint, headers, _json_bytes(body)


def _call_openai_compatible(
    *, base_url: str, model: str, api_key: str, skill_text: str, user_prompt: str
) -> dict[str, Any]:
    # Standard library only so the prototype does not add a new runtime dependency.
    import urllib.error
    import urllib.request

    endpoint, headers, data = _build_openai_compatible_request(
        base_url=base_url,
        model=model,
        api_key=api_key,
        skill_text=skill_text,
        user_prompt=user_prompt,
    )
    request = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Provider returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Provider connection failed: {exc.reason}") from exc

    payload = json.loads(raw.decode("utf-8"))
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("Provider response did not contain any choices")
    message = choices[0].get("message") or {}
    return {
        "output": message.get("content", ""),
        "provider_response_id": payload.get("id"),
        "usage": payload.get("usage"),
    }


class ProviderHandler(BaseHTTPRequestHandler):
    server_version = "AxiomizeHostedPrototype/0.1"

    def _send(self, status: int, payload: Any) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def log_message(self, fmt: str, *args: Any) -> None:
        # Avoid accidentally logging request headers (especially X-Provider-Key).
        print(f"{self.address_string()} - {fmt % args}")

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(HTTPStatus.OK, {"status": "ok", "service": "axiomize-hosted-prototype"})
            return
        if self.path == "/v1/skills":
            self._send(HTTPStatus.OK, {"skills": [asdict(skill) for skill in SKILLS.values()]})
            return
        self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = self._read_json()
        except (ValueError, json.JSONDecodeError) as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid_json", "detail": str(exc)})
            return

        if self.path == "/v1/session":
            provider = str(body.get("provider", "openai-compatible")).strip()
            model = str(body.get("model", "")).strip()
            base_url = str(body.get("base_url", "")).strip()
            if provider != "openai-compatible":
                self._send(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "unsupported_provider", "supported": ["openai-compatible"]},
                )
                return
            if not model or not base_url:
                self._send(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "missing_fields", "required": ["model", "base_url"]},
                )
                return

            session_id = uuid.uuid4().hex
            SESSIONS[session_id] = {
                "provider": provider,
                "model": model,
                "base_url": base_url,
            }
            self._send(
                HTTPStatus.CREATED,
                {
                    "session_id": session_id,
                    "provider": provider,
                    "model": model,
                    "base_url": base_url,
                    "api_key_stored": False,
                },
            )
            return

        if self.path == "/v1/run":
            session_id = str(body.get("session_id", "")).strip()
            skill_id = str(body.get("skill", "axiomize")).strip()
            prompt = str(body.get("prompt", "")).strip()
            api_key = self.headers.get("X-Provider-Key", "").strip()

            session = SESSIONS.get(session_id)
            skill = SKILLS.get(skill_id)
            if session is None:
                self._send(HTTPStatus.UNAUTHORIZED, {"error": "invalid_session"})
                return
            if skill is None:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "unknown_skill"})
                return
            if not prompt:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "missing_prompt"})
                return
            if not api_key:
                self._send(
                    HTTPStatus.UNAUTHORIZED,
                    {"error": "missing_provider_key", "header": "X-Provider-Key"},
                )
                return

            try:
                skill_text = _read_skill_text(skill)
                # The temporary directory is the first isolation boundary in the prototype.
                # Production should replace this with a real disposable container/sandbox.
                with tempfile.TemporaryDirectory(prefix="axiomize-run-"):
                    result = _call_openai_compatible(
                        base_url=session["base_url"],
                        model=session["model"],
                        api_key=api_key,
                        skill_text=skill_text,
                        user_prompt=prompt,
                    )
            except Exception as exc:  # prototype API boundary
                self._send(
                    HTTPStatus.BAD_GATEWAY,
                    {"error": "execution_failed", "detail": str(exc)},
                )
                return

            self._send(
                HTTPStatus.OK,
                {
                    "skill": skill.id,
                    "skill_version": skill.version,
                    "model": session["model"],
                    "retained_user_data": False,
                    **result,
                },
            )
            return

        self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), ProviderHandler)
    print(f"Axiomize hosted prototype listening on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
