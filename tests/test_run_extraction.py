import unittest
from unittest.mock import patch

from llm_provider import LLMResponse
from project_config import ProjectConfig
from run_extraction import call_llm, normalize_json_response_text


class FakeProvider:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def generate(self, messages, schema, settings):
        self.calls.append(dict(settings))
        return self._responses.pop(0)


class RunExtractionCallLlmTests(unittest.TestCase):
    def test_normalize_json_response_text_strips_markdown_fence(self) -> None:
        raw = '```json\n{"project_name":"Test","results":[]}\n```'
        self.assertEqual(normalize_json_response_text(raw), '{"project_name":"Test","results":[]}')

    def test_normalize_json_response_text_extracts_json_from_wrapped_text(self) -> None:
        raw = 'İşte sonuç:\n{"project_name":"Test","results":[]}\nTeşekkürler.'
        self.assertEqual(normalize_json_response_text(raw), '{"project_name":"Test","results":[]}')

    def test_call_llm_retries_without_thinking_when_content_is_empty(self) -> None:
        config = ProjectConfig(
            project_name="Test",
            dictionary_path="dummy.csv",
            llm={"provider": "ollama", "model": "qwen3.5:9b", "think": True, "temperature": 0, "max_tokens": 512},
        )
        provider = FakeProvider(
            [
                LLMResponse(content="", thinking="reasoning only", raw={"message": {"thinking": "reasoning only"}}),
                LLMResponse(content='{"project_name":"Test","results":[]}', raw={"message": {"content": "{}"}}),
            ]
        )

        with patch("run_extraction.create_provider", return_value=provider):
            raw_json = call_llm(config, [{"role": "user", "content": "test"}])

        self.assertEqual(raw_json, '{"project_name":"Test","results":[]}')
        self.assertEqual(len(provider.calls), 2)
        self.assertTrue(provider.calls[0]["think"])
        self.assertFalse(provider.calls[1]["think"])

    def test_call_llm_raises_if_retry_is_still_empty(self) -> None:
        config = ProjectConfig(
            project_name="Test",
            dictionary_path="dummy.csv",
            llm={"provider": "ollama", "model": "qwen3.5:9b", "think": True, "temperature": 0, "max_tokens": 512},
        )
        provider = FakeProvider(
            [
                LLMResponse(content="", thinking="first reasoning", raw={"message": {"thinking": "first reasoning"}}),
                LLMResponse(content="", thinking="second reasoning", raw={"message": {"thinking": "second reasoning"}}),
            ]
        )

        with patch("run_extraction.create_provider", return_value=provider):
            with self.assertRaises(ValueError) as exc:
                call_llm(config, [{"role": "user", "content": "test"}])

        self.assertIn("retrying with thinking disabled", str(exc.exception))

    def test_call_llm_returns_json_without_markdown_fence(self) -> None:
        config = ProjectConfig(
            project_name="Test",
            dictionary_path="dummy.csv",
            llm={"provider": "ollama", "model": "gemma4", "think": False, "temperature": 0, "max_tokens": 512},
        )
        provider = FakeProvider(
            [
                LLMResponse(
                    content='```json\n{"project_name":"Test","results":[]}\n```',
                    raw={"message": {"content": "```json ... ```"}},
                ),
            ]
        )

        with patch("run_extraction.create_provider", return_value=provider):
            raw_json = call_llm(config, [{"role": "user", "content": "test"}])

        self.assertEqual(raw_json, '{"project_name":"Test","results":[]}')


if __name__ == "__main__":
    unittest.main()
