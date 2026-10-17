"""Transport credentials, trusted-origin, and structured data boundaries."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

import axiomize.providers.openai_compatible as module
from axiomize.providers.openai_compatible import OpenAICompatibleProvider, _read_json_response


class Response:
    def __init__(self, body, *, status=200):
        self.stream = io.BytesIO(body)
        self.status = status
        self.read_limit = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit=-1):
        self.read_limit = limit
        return self.stream.read(limit)


class Opener:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def install(monkeypatch, payload, *, status=200):
    opener = Opener(Response(json.dumps(payload).encode(), status=status))
    monkeypatch.setattr(module, "_OPENER", opener)
    return opener


@pytest.mark.parametrize(
    ("base", "pattern"),
    [
        ("", "non-empty URL"),
        ("ftp://example.com", "scheme"),
        ("http://", "hostname"),
        ("https://username:pw@example.com", "credentials"),
        ("https://example.com/?key=x", "query or fragment"),
        ("https://example.com/#fragment", "query or fragment"),
    ],
)
def test_provider_url_cannot_embed_credentials_or_unapproved_protocol(base, pattern):
    with pytest.raises(ValueError, match=pattern):
        OpenAICompatibleProvider(base)


@pytest.mark.parametrize(
    ("timeout", "pattern"),
    [
        (0, "timeout_s"),
        (-1, "timeout_s"),
        (float("nan"), "timeout_s"),
        (float("inf"), "timeout_s"),
        (301, "timeout_s"),
    ],
)
def test_provider_timeout_is_finite_bounded(timeout, pattern):
    with pytest.raises(ValueError, match=pattern):
        OpenAICompatibleProvider("https://example.com", timeout_s=timeout)


@pytest.mark.parametrize("model", ["", "x" * 513])
def test_provider_model_identifier_requires_bounded_nonempty_string(model):
    with pytest.raises(ValueError, match="model must be"):
        OpenAICompatibleProvider("https://example.com", model=model)


@pytest.mark.parametrize(
    ("relative", "pattern"),
    [
        ("https://other.example", "absolute path"),
        ("relative/path", "absolute path"),
        ("/path?query=secret", "without query"),
        ("/path#fragment", "without query"),
    ],
)
def test_provider_service_path_cannot_change_trusted_origin(relative, pattern):
    with pytest.raises(ValueError, match=pattern):
        OpenAICompatibleProvider("https://example.com")._url(relative)


def test_authorized_model_call_never_sends_key_in_url(monkeypatch):
    opener = install(monkeypatch, {"choices": [{"message": {"content": "answer"}}]})
    provider = OpenAICompatibleProvider("https://example.com/v1/", model="scientific", api_key="sensitive-token")
    assert provider.generate("actual question") == "answer"
    assert len(opener.requests) == 1
    req, timeout = opener.requests[0]
    assert req.full_url == "https://example.com/v1/chat/completions"
    assert "sensitive-token" not in req.full_url
    assert req.get_header("Authorization") == "Bearer sensitive-token"
    assert req.get_method() == "POST"
    assert json.loads(req.data) == {
        "model": "scientific",
        "messages": [{"role": "user", "content": "actual question"}],
    }
    assert timeout == 30.0


def test_structured_output_requires_real_json_object(monkeypatch):
    opener = install(monkeypatch, {"choices": [{"message": {"content": '{"slope":2.0}'}}]})
    provider = OpenAICompatibleProvider("https://example.com")
    actual = provider.generate_structured("solve", {"type": "object"})
    assert actual == {"slope": 2.0}
    request = json.loads(opener.requests[0][0].data)
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["schema"] == {"type": "object"}


@pytest.mark.parametrize(
    ("body", "pattern"),
    [
        ({}, "missing choices"),
        ({"choices": []}, "missing choices"),
        ({"choices": [{}]}, "missing choices"),
        ({"choices": [{"message": {}}]}, "missing choices"),
    ],
)
def test_provider_missing_content_fails_closed(monkeypatch, body, pattern):
    install(monkeypatch, body)
    with pytest.raises(ValueError, match=pattern):
        OpenAICompatibleProvider("https://example.com").generate("question")


@pytest.mark.parametrize(
    ("content", "pattern"),
    [
        ("unstructured response", "valid structured JSON"),
        ("[1,2]", "must be a JSON object"),
        ('{"uncertainty":NaN}', "valid structured JSON"),
    ],
)
def test_structured_provider_cannot_forge_evidence(monkeypatch, content, pattern):
    install(monkeypatch, {"choices": [{"message": {"content": content}}]})
    with pytest.raises(ValueError, match=pattern):
        OpenAICompatibleProvider("https://example.com").generate_structured("question", {"type": "object"})


@pytest.mark.parametrize("body", [b"invalid", b'{"v":', b"\xff"])
def test_json_response_decoding_refuses_invalid_utf8_or_data(body):
    with pytest.raises(ValueError, match="invalid JSON"):
        _read_json_response(Response(body))


@pytest.mark.parametrize("body", [b"[]", b"null", b"1"])
def test_http_model_response_requires_object(body):
    with pytest.raises(ValueError, match="JSON object"):
        _read_json_response(Response(body))


def test_response_reader_enforces_explicit_byte_ceiling(monkeypatch):
    monkeypatch.setattr(module, "MAX_PROVIDER_RESPONSE_BYTES", 16)
    response = Response(b"x" * 17)
    with pytest.raises(ValueError, match="hard limit"):
        _read_json_response(response)
    assert response.read_limit == 17


@pytest.mark.parametrize(
    ("status", "pattern"),
    [
        (199, "HTTP 199"),
        (301, "HTTP 301"),
        (500, "HTTP 500"),
    ],
)
def test_provider_non_success_http_status_is_never_trusted(monkeypatch, status, pattern):
    install(monkeypatch, {"choices": [{"message": {"content": "fake success"}}]}, status=status)
    with pytest.raises(ValueError, match=pattern):
        OpenAICompatibleProvider("https://example.com").generate("question")


@pytest.mark.parametrize(
    ("status", "pattern"),
    [
        (301, "redirects are not allowed"),
        (401, "HTTP 401"),
    ],
)
def test_http_error_response_refuses_credential_redirect(monkeypatch, status, pattern):
    error = urllib.error.HTTPError("https://example.com", status, "error", {}, None)
    monkeypatch.setattr(module, "_OPENER", Opener(error))
    with pytest.raises(ValueError, match=pattern):
        OpenAICompatibleProvider("https://example.com", api_key="secret").generate("question")


def test_offline_provider_cannot_claim_success(monkeypatch):
    monkeypatch.setattr(module, "_OPENER", Opener(urllib.error.URLError("offline")))
    with pytest.raises(ValueError, match="connection failed"):
        OpenAICompatibleProvider("https://example.com").generate("question")


def test_provider_health_probe_obeys_short_timeout_and_requires_http_200(monkeypatch):
    opener = install(monkeypatch, {"models": []})
    provider = OpenAICompatibleProvider("http://localhost:8000", timeout_s=20)
    assert provider.health_check() is True
    request, timeout = opener.requests[0]
    assert request.full_url == "http://localhost:8000/models"
    assert request.get_method() == "GET"
    assert timeout == 5.0
    opener.response = Response(b"bad", status=503)
    assert provider.health_check() is False
    opener.response = urllib.error.URLError("offline")
    assert provider.health_check() is False


def test_provider_health_response_still_has_hard_size_ceiling(monkeypatch):
    monkeypatch.setattr(module, "MAX_PROVIDER_RESPONSE_BYTES", 16)
    opener = Opener(Response(b"x" * 17))
    monkeypatch.setattr(module, "_OPENER", opener)
    assert OpenAICompatibleProvider("https://example.com").health_check() is False
    assert opener.response.read_limit == 17


@pytest.mark.parametrize(
    "body",
    [
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":-Infinity}',
        b'{"x":1e999}',
        b'{"data":[{"value":NaN}]}',
    ],
)
def test_http_json_envelope_refuses_nonfinite_scientific_data(body):
    with pytest.raises(ValueError, match="invalid JSON"):
        _read_json_response(Response(body))


@pytest.mark.parametrize(
    "content",
    [
        '{"value":Infinity}',
        '{"value":-Infinity}',
        '{"value":1e999}',
        '{"values":[0.0,NaN]}',
    ],
)
def test_structured_scientific_response_refuses_nonfinite_claims(monkeypatch, content):
    install(monkeypatch, {"choices": [{"message": {"content": content}}]})
    with pytest.raises(ValueError, match="valid structured JSON"):
        OpenAICompatibleProvider("https://example.com").generate_structured("question", {"type": "object"})
