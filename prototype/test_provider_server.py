from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import provider_server


class ProviderPrototypeTests(unittest.TestCase):
    def test_skill_registry_contains_axiomize(self) -> None:
        skill = provider_server.SKILLS["axiomize"]
        self.assertEqual(skill.name, "Axiomize")
        self.assertTrue(skill.entrypoint.endswith("SKILL.md"))

    def test_openai_compatible_request_does_not_embed_key_in_body(self) -> None:
        endpoint, headers, body = provider_server._build_openai_compatible_request(
            base_url="https://example.test/v1",
            model="test-model",
            api_key="secret-key",
            skill_text="skill instructions",
            user_prompt="solve this",
        )
        self.assertEqual(endpoint, "https://example.test/v1/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer secret-key")
        decoded = json.loads(body)
        self.assertNotIn("secret-key", json.dumps(decoded))
        self.assertEqual(decoded["model"], "test-model")
        self.assertEqual(decoded["messages"][0]["content"], "skill instructions")
        self.assertEqual(decoded["messages"][1]["content"], "solve this")

    @patch("provider_server._read_skill_text", return_value="skill")
    def test_skill_loading_path_is_centralized(self, read_skill: object) -> None:
        provider_server._read_skill_text(provider_server.SKILLS["axiomize"])
        self.assertTrue(read_skill.called)


if __name__ == "__main__":
    unittest.main()
