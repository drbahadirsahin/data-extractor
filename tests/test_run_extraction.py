import unittest
import json
from unittest.mock import patch

from dictionary_parser import FieldSpec
from llm_provider import LLMResponse
from project_config import ProjectConfig
from run_extraction import (
    ExtractionFieldResult,
    ExtractionResponse,
    ModelCallResult,
    ModelOutputError,
    _settings_with_ignored_providers,
    build_model_output_schema,
    call_llm,
    normalize_json_response_text,
    run_batch_with_fallback,
    run_single_batch,
)


class FakeProvider:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def generate(self, messages, schema, settings):
        self.calls.append(dict(settings))
        return self._responses.pop(0)


def make_field(field_name: str) -> FieldSpec:
    return FieldSpec(
        field_name=field_name,
        form_name="hasta_bilgileri",
        field_type="text",
        field_label=field_name,
    )


def make_model_result(
    field_name: str,
    *,
    status: str = "found",
    final_value: object = "değer",
    final_value_code: str | None = None,
) -> dict:
    return {
        "field_name": field_name,
        "form_name": "hasta_bilgileri",
        "status": status,
        "cardinality": "single",
        "selection_rule": "latest",
        "candidates": [],
        "confidence": 0.9 if status == "found" else None,
        "final_value": final_value,
        "final_value_code": final_value_code,
        "selection_reason": "synthetic test" if status == "found" else None,
        "needs_review": False,
        "review_reasons": [],
    }


def make_model_json(field_names: list[str]) -> str:
    return json.dumps(
        {
            "project_name": "Test",
            "results": [make_model_result(field_name) for field_name in field_names],
        },
        ensure_ascii=False,
    )


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


class RunExtractionStructuredOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = ProjectConfig(
            project_name="Test",
            dictionary_path="dummy.csv",
            batch_size=15,
            llm={"provider": "llm_gateway", "model": "deepseek/deepseek-v4-flash"},
        )

    def test_batch_schema_requires_complete_exact_field_results(self) -> None:
        schema = build_model_output_schema([make_field("hasta_ad"), make_field("tarih")])
        result_schema = schema["$defs"]["ModelExtractionFieldResult"]
        candidate_schema = schema["$defs"]["ModelCandidate"]

        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(result_schema["additionalProperties"])
        self.assertFalse(candidate_schema["additionalProperties"])
        self.assertEqual(schema["properties"]["results"]["minItems"], 2)
        self.assertEqual(schema["properties"]["results"]["maxItems"], 2)
        self.assertEqual(
            result_schema["properties"]["field_name"]["enum"],
            ["hasta_ad", "tarih"],
        )
        self.assertEqual(set(result_schema["required"]), set(result_schema["properties"]))

    def test_found_without_usable_value_is_rejected_without_raw_content_leak(self) -> None:
        sensitive_marker = "Hasta TC 12345678901"
        payload = {
            "project_name": "Test",
            "results": [
                {
                    **make_model_result(
                        "hasta_ad",
                        final_value=None,
                        final_value_code=None,
                    ),
                    "candidates": [
                        {
                            "value_raw": sensitive_marker,
                            "value_normalized": None,
                            "value_code": None,
                            "confidence": 0.8,
                            "evidence": None,
                            "context_date": None,
                            "context_label": None,
                        }
                    ],
                }
            ],
        }
        call_result = ModelCallResult(
            content=json.dumps(payload),
            provider_name="Alibaba",
            request_id="gen-test",
        )

        with patch("run_extraction._call_llm_with_metadata", return_value=call_result):
            with self.assertRaises(ModelOutputError) as raised:
                run_single_batch(self.config, "synthetic document", [make_field("hasta_ad")])

        self.assertEqual(raised.exception.reason, "found_without_value")
        self.assertEqual(raised.exception.provider_name, "Alibaba")
        self.assertEqual(raised.exception.request_id, "gen-test")
        self.assertNotIn(sensitive_marker, str(raised.exception))

    def test_invalid_provider_is_ignored_on_same_batch_retry(self) -> None:
        fields = [make_field("hasta_ad")]
        invalid_payload = {
            "project_name": "Test",
            "results": [make_model_result("hasta_ad", final_value=None)],
        }
        responses = [
            ModelCallResult(json.dumps(invalid_payload), "Alibaba", "gen-bad"),
            ModelCallResult(make_model_json(["hasta_ad"]), "DeepInfra", "gen-good"),
        ]

        with patch("run_extraction._call_llm_with_metadata", side_effect=responses) as llm_call:
            parsed = run_batch_with_fallback(self.config, "synthetic document", fields)

        self.assertEqual(parsed.results[0].final_value, "değer")
        self.assertEqual(llm_call.call_count, 2)
        self.assertEqual(llm_call.call_args_list[0].kwargs["ignored_providers"], [])
        self.assertEqual(llm_call.call_args_list[1].kwargs["ignored_providers"], ["alibaba"])

    def test_invalid_batch_splits_by_actual_field_count(self) -> None:
        fields = [make_field(f"alan_{index}") for index in range(4)]
        call_sizes: list[int] = []

        def fake_run_single(_config, _document, batch_fields, **_kwargs):
            call_sizes.append(len(batch_fields))
            if len(batch_fields) == 4:
                raise ModelOutputError("schema", "Alibaba")
            return ExtractionResponse(
                project_name="Test",
                results=[
                    ExtractionFieldResult(field_name=field.field_name, status="found", final_value="x")
                    for field in batch_fields
                ],
            )

        with patch("run_extraction.run_single_batch", side_effect=fake_run_single):
            parsed = run_batch_with_fallback(self.config, "synthetic document", fields)

        self.assertEqual(call_sizes, [4, 4, 2, 2])
        self.assertEqual(len(parsed.results), 4)

    def test_ignored_provider_settings_preserve_existing_preferences(self) -> None:
        original = {
            "provider": "llm_gateway",
            "extra_body": {
                "provider": {"order": ["DeepInfra"], "ignore": ["Venice"]},
                "custom": True,
            },
        }

        scoped = _settings_with_ignored_providers(original, ["Alibaba", "venice"])

        self.assertEqual(scoped["extra_body"]["provider"]["order"], ["DeepInfra"])
        self.assertEqual(scoped["extra_body"]["provider"]["ignore"], ["venice", "alibaba"])
        self.assertTrue(scoped["extra_body"]["custom"])
        self.assertEqual(original["extra_body"]["provider"]["ignore"], ["Venice"])

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
