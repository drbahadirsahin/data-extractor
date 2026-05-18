import io
import os
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from llm_provider import (
    OllamaProvider,
    OpenAICompatibleProvider,
    ProviderHTTPError,
    build_ollama_options,
    build_openai_reasoning,
    create_provider,
    merge_llm_settings,
    post_json,
    resolve_api_key,
)
from secrets_store import SecretsStore
from settings_store import APP_HOME_ENV_VAR


class LlmProviderTests(unittest.TestCase):
    def test_merge_llm_settings_prefers_project_values(self) -> None:
        merged = merge_llm_settings(
            {"provider": "ollama", "base_url": "http://localhost:11434", "temperature": 0},
            {"provider": "openai_compatible", "temperature": 0.3},
        )
        self.assertEqual(merged["provider"], "openai_compatible")
        self.assertEqual(merged["base_url"], "http://localhost:11434")
        self.assertEqual(merged["temperature"], 0.3)

    def test_resolve_api_key_from_env(self) -> None:
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "secret-key"}, clear=False):
            self.assertEqual(
                resolve_api_key({"api_key_env": "OPENROUTER_API_KEY"}),
                "secret-key",
            )

    def test_resolve_api_key_from_default_secret_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {APP_HOME_ENV_VAR: temp_dir}, clear=False):
                SecretsStore(temp_dir).set("llm_api_key", "secret-key")

                self.assertEqual(
                    resolve_api_key({"provider": "openai_compatible"}),
                    "secret-key",
                )

    def test_create_provider_supports_openrouter_alias(self) -> None:
        provider = create_provider({"provider": "openrouter"})
        self.assertIsInstance(provider, OpenAICompatibleProvider)

    def test_build_ollama_options_merges_extra_options(self) -> None:
        options = build_ollama_options(
            {
                "temperature": 0,
                "max_tokens": 2048,
                "options": {
                    "num_ctx": 16384,
                    "repeat_penalty": 1.05,
                },
            }
        )
        self.assertEqual(options["num_predict"], 2048)
        self.assertEqual(options["num_ctx"], 16384)
        self.assertEqual(options["repeat_penalty"], 1.05)

    def test_ollama_provider_streams_by_default(self) -> None:
        provider = OllamaProvider()
        with patch(
            "llm_provider.post_json_stream",
            return_value={"message": {"content": '{"ok":true}', "thinking": None}},
        ) as mock_stream:
            response = provider.generate(
                messages=[{"role": "user", "content": "test"}],
                schema={"type": "object"},
                settings={"provider": "ollama", "base_url": "http://127.0.0.1:11434", "model": "qwen3.5:9b"},
            )

        self.assertEqual(response.content, '{"ok":true}')
        self.assertTrue(mock_stream.call_args.kwargs["payload"]["stream"])
        self.assertEqual(mock_stream.call_args.kwargs["timeout_seconds"], 600)

    def test_build_openai_reasoning_disables_reasoning_when_think_false(self) -> None:
        reasoning = build_openai_reasoning({"think": False})
        self.assertEqual(reasoning, {"effort": "none", "exclude": True})

    def test_build_openai_reasoning_uses_explicit_config(self) -> None:
        reasoning = build_openai_reasoning({"reasoning": {"effort": "low"}})
        self.assertEqual(reasoning, {"effort": "low"})

    def test_openai_compatible_retries_without_json_schema(self) -> None:
        provider = OpenAICompatibleProvider()
        first_error = ProviderHTTPError(
            "unsupported response_format",
            status_code=400,
            body='{"error":"response_format is unsupported"}',
        )
        success_response = {
            "choices": [
                {
                    "message": {
                        "content": '{"project_name":"Test","results":[]}',
                    }
                }
            ]
        }
        with patch("llm_provider.post_json", side_effect=[first_error, success_response]) as mock_post:
            response = provider.generate(
                messages=[{"role": "user", "content": "test"}],
                schema={"type": "object"},
                settings={
                    "provider": "openai_compatible",
                    "base_url": "https://openrouter.ai/api/v1",
                    "api_key": "secret",
                    "model": "openai/gpt-4o-mini",
                    "use_json_schema": True,
                },
            )

        self.assertEqual(response.content, '{"project_name":"Test","results":[]}')
        self.assertEqual(mock_post.call_count, 2)
        first_payload = mock_post.call_args_list[0].kwargs["payload"]
        second_payload = mock_post.call_args_list[1].kwargs["payload"]
        self.assertIn("response_format", first_payload)
        self.assertNotIn("response_format", second_payload)

    def test_post_json_surfaces_cloudflare_1010_helpfully(self) -> None:
        http_error = HTTPError(
            url="https://example.com",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=io.BytesIO(b"error code: 1010"),
        )
        with patch("llm_provider.request.urlopen", side_effect=http_error):
            with self.assertRaises(ProviderHTTPError) as exc:
                post_json(
                    url="https://example.com",
                    payload={"ping": True},
                    headers={},
                    timeout_seconds=30,
                )

        self.assertIn("Cloudflare", str(exc.exception))
        self.assertIn("1010", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
