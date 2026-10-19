"""Test provider HTTP trust boundaries with an isolated deterministic transport.

The transport is fake, not an external LLM: assertions concern HTTP framing,
credential confidentiality, finite JSON and explicit response validation.
"""
from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock

import pytest

from axiomize.providers import openai_compatible as provider


class Reply:
    def __init__(self, data, *, status=200):
        self.data = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
        self.status = status

    def read(self, size):
        return self.data[:size]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def transport(monkeypatch, data, *, status=200):
    opener = MagicMock()
    opener.open.return_value = Reply(data, status=status)
    monkeypatch.setattr(provider, "_OPENER", opener)
    return opener


@pytest.mark.parametrize("url, expected", [
    ("http://127.0.0.1:8080/v1/", "http://127.0.0.1:8080/v1"),
    ("https://models.example.org/v1", "https://models.example.org/v1"),
    ("https://models.example.org/", "https://models.example.org"),
])
def test_base_url_normalizes_only_trailing_separator(url, expected):
    assert provider._validate_base_url(url) == expected


@pytest.mark.parametrize("bad, reason", [
    ("", "non-empty"), (None, "non-empty"), ("ftp://server/v1", "scheme"),
    ("file:///tmp/a", "scheme"), ("http://", "hostname"),
    ("https://alice:secret@models.example.org", "credentials"),
    ("https://models.example.org/?x=1", "query or fragment"),
    ("https://models.example.org/#hash", "query or fragment"),
])
def test_endpoint_denies_credential_leaks_and_unsafe_schemes(bad, reason):
    with pytest.raises(ValueError, match=reason):
        provider._validate_base_url(bad)


@pytest.mark.parametrize("bad", ["relative", "path/a", "/x?secret=1", "/x#anchor", None])
def test_post_paths_must_be_absolute_without_url_components(bad):
    model = provider.OpenAICompatibleProvider("http://127.0.0.1:8080")
    with pytest.raises(ValueError, match="provider path"):
        model._url(bad)


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf"), 301])
def test_timeouts_must_be_finite_and_bounded(bad):
    with pytest.raises(ValueError, match="timeout_s"):
        provider.OpenAICompatibleProvider("http://127.0.0.1:8080", timeout_s=bad)


def test_model_ids_must_be_nonempty_and_bounded():
    for value in ("", "a" * 513):
        with pytest.raises(ValueError, match="model must"):
            provider.OpenAICompatibleProvider("https://models.example.org", model=value)


def test_auth_header_not_forwarded_by_redirect_handler():
    opener = provider._NoRedirect()
    assert opener.redirect_request(None, None, 302, "redirect", {}, "https://other.example.org") is None


def test_valid_post_serializes_payload_with_explicit_model_and_optional_key(monkeypatch):
    opener = transport(monkeypatch, {"choices": [{"message": {"content": "grounded reply"}}]})
    m = provider.OpenAICompatibleProvider("https://models.example.org/v1", model="audited", api_key="private-key")
    assert m.generate("A known test prompt") == "grounded reply"
    req = opener.open.call_args.args[0]
    assert req.full_url == "https://models.example.org/v1/chat/completions"
    assert req.get_header("Authorization") == "Bearer private-key"
    assert json.loads(req.data.decode("utf-8")) == {
        "model": "audited", "messages": [{"role": "user", "content": "A known test prompt"}],
    }


def test_missing_key_has_no_auth_header(monkeypatch):
    opener = transport(monkeypatch, {"choices": [{"message": {"content": 42}}]})
    m = provider.OpenAICompatibleProvider("http://127.0.0.1:8080")
    assert m.generate("p") == "42"
    assert opener.open.call_args.args[0].get_header("Authorization") is None


@pytest.mark.parametrize("payload", [
    {"choices": []}, {"choices": [{"message": {}}]}, {"choices": [{}]},
    {"choices": None}, {},
])
def test_missing_chat_message_content_is_not_invented(monkeypatch, payload):
    transport(monkeypatch, payload)
    with pytest.raises(ValueError, match="missing choices"):
        provider.OpenAICompatibleProvider("http://127.0.0.1:8080").generate("p")


@pytest.mark.parametrize("bad", [None, 3.5, ["a"]])
def test_generate_requires_actual_prompt_text(bad):
    model = provider.OpenAICompatibleProvider("http://127.0.0.1:8080")
    with pytest.raises(ValueError, match="prompt must"):
        model.generate(bad)


def test_structured_generation_checks_schema_and_decodes_real_json(monkeypatch):
    opener = transport(monkeypatch, {"choices": [{"message": {"content": json.dumps({"accepted": True})}}]})
    m = provider.OpenAICompatibleProvider("https://models.example.org")
    assert m.generate_structured("p", {"type": "object"}) == {"accepted": True}
    body = json.loads(opener.open.call_args.args[0].data.decode())
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == {"type": "object"}


@pytest.mark.parametrize("payload", [
    {"choices": [{"message": {"content": "[1,2]"}}]},
    {"choices": [{"message": {"content": "malformed"}}]},
    {"choices": [{}]}, {"choices": []},
])
def test_structured_generation_rejects_missing_invalid_and_nonobject_output(monkeypatch, payload):
    transport(monkeypatch, payload)
    with pytest.raises(ValueError, match="structured|valid structured"):
        provider.OpenAICompatibleProvider("https://models.example.org").generate_structured("p", {})


def test_structured_generation_refuses_nonschema_objects():
    with pytest.raises(ValueError, match="schema must be"):
        provider.OpenAICompatibleProvider("http://127.0.0.1").generate_structured("p", [])


@pytest.mark.parametrize("data, reason", [
    (b"no-json", "invalid JSON"),
    (b"[]", "JSON object"),
    (b"123", "JSON object"),
    (b"\\xff", "invalid JSON"),
])
def test_response_parser_does_not_accept_untrusted_nonobject_data(data, reason):
    with pytest.raises(ValueError, match=reason):
        provider._read_json_response(Reply(data))


def test_hard_response_budget_rejects_oversized_external_reply(monkeypatch):
    monkeypatch.setattr(provider, "MAX_PROVIDER_RESPONSE_BYTES", 8)
    with pytest.raises(ValueError, match="hard limit"):
        provider._read_json_response(Reply(bytes([123, 34, 109, 97, 110, 121, 34, 58, 34, 98, 121, 116, 101, 115, 34, 125])))


@pytest.mark.parametrize("status", [100, 301, 403, 500])
def test_non_2xx_http_responses_are_not_reported_as_success(monkeypatch, status):
    transport(monkeypatch, {}, status=status)
    with pytest.raises(ValueError, match="returned HTTP"):
        provider.OpenAICompatibleProvider("http://127.0.0.1").generate("p")


@pytest.mark.parametrize("http_status, message", [(302, "redirects are not allowed"), (401, "failed with HTTP 401")])
def test_transport_failures_do_not_forward_credentials(monkeypatch, http_status, message):
    opener = MagicMock()
    opener.open.side_effect = urllib.error.HTTPError(
        "https://models.example.org", http_status, "denied", {}, None,
    )
    monkeypatch.setattr(provider, "_OPENER", opener)
    with pytest.raises(ValueError, match=message):
        provider.OpenAICompatibleProvider("https://models.example.org", api_key="private-key").generate("p")


def test_url_error_retains_connection_failure_cause(monkeypatch):
    opener = MagicMock()
    opener.open.side_effect = urllib.error.URLError("network refused")
    monkeypatch.setattr(provider, "_OPENER", opener)
    with pytest.raises(ValueError, match="connection failed"):
        provider.OpenAICompatibleProvider("https://models.example.org").generate("p")


def test_invalid_outbound_nan_cannot_be_json_encoded(monkeypatch):
    transport(monkeypatch, {})
    with pytest.raises(ValueError, match="Out of range float"):
        provider.OpenAICompatibleProvider("http://127.0.0.1")._post("/chat/completions", {"metric": float("nan")})


def test_bounded_health_probe_is_not_a_generation_approval(monkeypatch):
    opener = transport(monkeypatch, {"models": []})
    m = provider.OpenAICompatibleProvider("http://127.0.0.1", timeout_s=30.0)
    assert m.health_check() is True
    assert opener.open.call_args.kwargs["timeout"] == 5.0
    assert opener.open.call_args.args[0].get_method() == "GET"


def test_health_probe_rejects_non_200_and_oversized_payloads(monkeypatch):
    transport(monkeypatch, {}, status=204)
    m = provider.OpenAICompatibleProvider("http://127.0.0.1")
    assert m.health_check() is False
    monkeypatch.setattr(provider, "MAX_PROVIDER_RESPONSE_BYTES", 8)
    transport(monkeypatch, bytes([120]) * 15)
    assert m.health_check() is False


def test_health_probe_transport_errors_are_not_mistaken_for_health(monkeypatch):
    opener = MagicMock()
    opener.open.side_effect = urllib.error.URLError("unreachable")
    monkeypatch.setattr(provider, "_OPENER", opener)
    assert provider.OpenAICompatibleProvider("http://127.0.0.1").health_check() is False


def test_oversized_outgoing_payload_refused_before_transport(monkeypatch):
    opener = transport(monkeypatch, {})
    monkeypatch.setattr(provider, "MAX_JSON_BYTES", 8)
    with pytest.raises(ValueError, match="request exceeds hard limit"):
        provider.OpenAICompatibleProvider("http://127.0.0.1")._post(
            "/chat/completions", {"content": "scientific evidence"}
        )
    opener.open.assert_not_called()
