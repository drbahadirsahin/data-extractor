import argparse
from collections import Counter
from dataclasses import dataclass
import json
from copy import deepcopy
import re

from project_config import load_project_config, ProjectConfig
from dictionary_parser import load_data_dictionary, FieldSpec
from helpers import  load_json
from document_parser import load_file
from typing import Any, Literal, TypeAlias
from pathlib import Path
from llm_provider import create_provider, merge_llm_settings

from pydantic import BaseModel, ConfigDict, Field, ValidationError


ModelScalarValue: TypeAlias = str | int | float | bool
ModelValue: TypeAlias = ModelScalarValue | list[ModelScalarValue | None]


class ModelCandidate(BaseModel):
    """Strict, transport-only candidate contract returned by the model."""

    model_config = ConfigDict(extra="forbid")

    value_raw: str | None
    value_normalized: ModelValue | None
    value_code: str | None
    confidence: float | None = Field(..., ge=0.0, le=1.0)
    evidence: str | None
    context_date: str | None
    context_label: str | None


class ModelExtractionFieldResult(BaseModel):
    """Strict model-output contract kept separate from the permissive app model."""

    model_config = ConfigDict(extra="forbid")

    field_name: str
    form_name: str | None
    status: Literal["found", "not_found", "uncertain", "conflict"]
    cardinality: Literal["single", "multiple", "repeat_entity"]
    selection_rule: Literal["latest", "earliest", "highest", "lowest", "all", "manual_review"]
    candidates: list[ModelCandidate] | None
    confidence: float | None = Field(..., ge=0.0, le=1.0)
    final_value: ModelValue | None
    final_value_code: str | None
    selection_reason: str | None
    needs_review: bool
    review_reasons: list[str]


class ModelExtractionResponse(BaseModel):
    """Strict top-level contract used only for provider output validation."""

    model_config = ConfigDict(extra="forbid")

    project_name: str
    results: list[ModelExtractionFieldResult]


MODEL_OUTPUT_ERROR_MESSAGES = {
    "truncated": "Model output was truncated.",
    "invalid_json": "Model output was not valid JSON.",
    "schema": "Model output did not match the required schema.",
    "field_coverage": "Model output did not contain exactly one result for each target field.",
    "found_without_value": "Model marked a field as found without returning a usable value.",
    "empty_content": "LLM provider returned empty message.content.",
    "empty_content_after_thinking_retry": (
        "LLM provider returned empty message.content after retrying with thinking disabled."
    ),
}


class ModelOutputError(ValueError):
    """A retryable model-output failure whose message never includes raw output."""

    def __init__(
        self,
        reason: str,
        provider_name: str | None = None,
        request_id: str | None = None,
    ) -> None:
        self.reason = reason
        self.provider_name = _safe_metadata_text(provider_name)
        self.request_id = _safe_metadata_text(request_id)
        super().__init__(MODEL_OUTPUT_ERROR_MESSAGES.get(reason, "Model output was invalid."))


@dataclass(frozen=True)
class ModelCallResult:
    content: str
    provider_name: str | None
    request_id: str | None


def _safe_metadata_text(value: Any, *, limit: int = 160) -> str | None:
    if value is None:
        return None
    text = " ".join("".join(char if char.isprintable() else " " for char in str(value)).split())
    return text[:limit] or None


def _model_error_context(error: ModelOutputError) -> str:
    parts: list[str] = []
    if error.provider_name:
        parts.append(f"provider={error.provider_name}")
    if error.request_id:
        parts.append(f"request_id={error.request_id}")
    return f" ({', '.join(parts)})" if parts else ""

class ExtractionFieldResult(BaseModel):
    field_name: str
    form_name: str | None = None
    status: str = "not_found"  # found | not_found | uncertain | conflict
    cardinality: str = "single" # single | multiple | repeat_entity
    selection_rule: str = "latest"  # latest | earliest | highest | lowest | all | manual_review#
    candidates: list[dict[str, Any]] | None = None
    confidence: float | None = None
    final_value: str | int | float | bool | list[Any] | None = None
    final_value_code: str | None = None
    selection_reason: str | None = None
    needs_review: bool = False
    review_reasons: list[str] = []

class ExtractionResponse(BaseModel):
    project_name: str
    results: list[ExtractionFieldResult]


def build_field_payload(fields: list[FieldSpec]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for field in fields:
        item = field.to_prompt_dict()
        payload.append(item)
    return payload


def build_prompt(config: ProjectConfig, document_text:str, fields: list[FieldSpec]) -> list[dict[str, Any]]:
    project_instructions = config.prompting.get("instructions", "")
    project_instructions_block = "\n".join(f"- {line}" for line in project_instructions)
    payload = build_field_payload(fields)
    target_fields_json = json.dumps(payload, indent=2, ensure_ascii=False)
    app_settings = load_json("app_config.json")
    system_prompt = app_settings.get("system_prompt", "")
    instructions = app_settings.get("instructions", [])
    instruction_block = "\n".join(f"- {line}" for line in instructions)
    user_prompt = f"""
Kurallar:
{project_instructions_block}

Ek kurallar:
{instruction_block}

Hedef alanlar (REDCap-türevi metadata + özel talimatlar):
{target_fields_json}

Her hedef alan için tam olarak bir sonuç döndür. Alan atlama, aynı alanı tekrarlama veya
hedef listesinde bulunmayan bir field_name döndürme. status="found" ise kullanılabilir
bir final_value/final_value_code veya değer taşıyan en az bir candidate döndür.

Dönüş şeması:
{{
  "project_name": "{config.project_name}",
  "results": [
    {{
      "field_name": "string",
      "form_name": "string or null",
      "status": "found | not_found | uncertain | conflict",
      "cardinality": "single | multiple | repeat_entity",
      "selection_rule": "latest | earliest | highest | lowest | all | manual_review",
      "candidates": [
        {{
          "value_raw": "string or null",
          "value_normalized": "string | number | boolean | array | null",
          "value_code": "string or null",
          "confidence": 0.0,
          "evidence": "short quote from document or null",
          "context_date": "YYYY-MM-DD or DD.MM.YYYY or null",
          "context_label": "string or null"
        }}
      ],
      "final_value": "string | number | boolean | array | null",
      "final_value_code": "string or null",
      "confidence": 0.0,
      "selection_reason": "string or null",
      "needs_review": true,
      "review_reasons": ["string"]
    }}
  ]
}}

Belge metni:
<<<DOCUMENT>>>
{document_text}
<<<END_DOCUMENT>>>
""".strip()

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

def chunk_fields(fields: list[FieldSpec], chunk_size: int = 10) -> list[list[FieldSpec]]:
    return [fields[i:i + chunk_size] for i in range(0, len(fields), chunk_size)]


def build_model_output_schema(fields: list[FieldSpec]) -> dict[str, Any]:
    """Build the strict provider schema for exactly this batch of fields."""

    schema = ModelExtractionResponse.model_json_schema()
    results_schema = schema["properties"]["results"]
    results_schema["minItems"] = len(fields)
    results_schema["maxItems"] = len(fields)

    field_names = list(dict.fromkeys(field.field_name for field in fields))
    result_definition = schema.get("$defs", {}).get("ModelExtractionFieldResult", {})
    field_name_schema = result_definition.get("properties", {}).get("field_name")
    if isinstance(field_name_schema, dict):
        field_name_schema["enum"] = field_names
    return schema


def run_batch_with_fallback(
    config: ProjectConfig,
    document_text: str,
    fields: list[FieldSpec],
    *,
    ignored_providers: list[str] | None = None,
) -> ExtractionResponse:
    ignored_providers = _unique_provider_names(ignored_providers or [])
    first_failed_provider: str | None = None
    try:
        return run_single_batch(
            config,
            document_text,
            fields,
            ignored_providers=ignored_providers,
        )
    except ModelOutputError as first_error:
        first_failed_provider = first_error.provider_name
        print("Model output failed validation. Retrying the same batch once...")

    retry_ignored_providers = _unique_provider_names(
        [*ignored_providers, first_failed_provider]
    )
    try:
        return run_single_batch(
            config,
            document_text,
            fields,
            is_retry=True,
            ignored_providers=retry_ignored_providers,
        )
    except ModelOutputError as retry_error:
        if len(fields) == 1:
            if retry_error.reason == "truncated":
                raise ValueError(
                    "Model response was truncated for a single target field after one retry. "
                    f"Try increasing max_tokens.{_model_error_context(retry_error)}"
                ) from retry_error
            raise ValueError(
                "Model could not return a valid result for a single target field after one retry."
                f"{_model_error_context(retry_error)}"
            ) from retry_error

        split_index = len(fields) // 2
        split_ignored_providers = _unique_provider_names(
            [*retry_ignored_providers, retry_error.provider_name]
        )
        print("Model output remained invalid. Retrying as smaller batches...")
        left = run_batch_with_fallback(
            config,
            document_text,
            fields[:split_index],
            ignored_providers=split_ignored_providers,
        )
        right = run_batch_with_fallback(
            config,
            document_text,
            fields[split_index:],
            ignored_providers=split_ignored_providers,
        )
        return ExtractionResponse(project_name=config.project_name, results=left.results + right.results)


def run_single_batch(
    config: ProjectConfig,
    document_text: str,
    fields: list[FieldSpec],
    *,
    is_retry: bool = False,
    ignored_providers: list[str] | None = None,
) -> ExtractionResponse:
    prompts = build_prompt(config, document_text, fields)
    if is_retry:
        prompts.append(
            {
                "role": "user",
                "content": (
                    "The previous response did not satisfy the output contract. Return JSON only, "
                    "with exactly one complete result for every target field."
                ),
            }
        )
    call_result = _call_llm_with_metadata(
        config,
        prompts,
        schema=build_model_output_schema(fields),
        ignored_providers=ignored_providers,
    )
    raw_json = call_result.content

    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        reason = "truncated" if _json_error_looks_truncated(exc, raw_json) else "invalid_json"
        raise ModelOutputError(reason, call_result.provider_name, call_result.request_id) from exc

    try:
        model_response = ModelExtractionResponse.model_validate(payload)
    except ValidationError as exc:
        raise ModelOutputError("schema", call_result.provider_name, call_result.request_id) from exc

    try:
        validate_model_output_semantics(model_response, fields)
    except ModelOutputError as exc:
        raise ModelOutputError(
            exc.reason,
            call_result.provider_name,
            call_result.request_id,
        ) from exc
    parsed = ExtractionResponse.model_validate(model_response.model_dump())

    return validate_and_fill_missing(config, parsed, fields)


def _json_error_looks_truncated(exc: json.JSONDecodeError, raw_json: str) -> bool:
    stripped_length = len(raw_json.rstrip())
    return exc.msg.startswith("Unterminated string") or exc.pos >= max(0, stripped_length - 1)


def validate_model_output_semantics(
    parsed: ModelExtractionResponse,
    fields: list[FieldSpec],
) -> None:
    expected_names = [field.field_name for field in fields]
    returned_names = [result.field_name for result in parsed.results]
    counts = Counter(returned_names)

    missing_names = set(expected_names) - set(returned_names)
    unknown_names = set(returned_names) - set(expected_names)
    duplicate_names = {name for name, count in counts.items() if count > 1}
    if missing_names or unknown_names or duplicate_names or len(returned_names) != len(expected_names):
        raise ModelOutputError("field_coverage")

    for result in parsed.results:
        if result.status == "found" and not _model_result_has_usable_value(result):
            raise ModelOutputError("found_without_value")


def _model_result_has_usable_value(result: ModelExtractionFieldResult) -> bool:
    if _has_usable_value(result.final_value) or _has_usable_value(result.final_value_code):
        return True
    return any(
        _has_usable_value(candidate.value_normalized)
        or _has_usable_value(candidate.value_code)
        for candidate in (result.candidates or [])
    )


def _has_usable_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_has_usable_value(item) for item in value)
    return True


def post_process_result(result: ExtractionFieldResult, field: FieldSpec) -> ExtractionFieldResult:
    if not field.post_processing or not result.final_value:
        return result
    # Post process logic here
    for process in field.post_processing:
        if process[0] == 'limit_output_length':
            max_length = process[1]
            if isinstance(result.final_value, str) and len(result.final_value) > max_length:
                result.final_value = result.final_value[:max_length]
    return result


def validate_and_fill_missing(config: ProjectConfig, parsed: ExtractionResponse, fields: list[FieldSpec]) -> ExtractionResponse:
    field_map = {field.field_name: field for field in fields}

    cleaned_results = []
    # Fills missing fields from specs; auto-selects top candidate for singles; post-processes results
    for result in parsed.results:
        key = result.field_name
        if key not in field_map:
            continue
        field_spec = field_map[key]
        if result.cardinality is None:
            result.cardinality = field_spec.cardinality
        if result.form_name is None:
            result.form_name = field_spec.form_name
        if result.selection_rule is None:
            result.selection_rule = field_spec.selection_rule


        if result.cardinality == "multiple" and result.candidates is None:
            result.candidates = []
        if result.cardinality == "single" and result.final_value is None and result.candidates:
            top_candidate = max(result.candidates, key=lambda c: c.get("confidence", 0) or 0)
            result.final_value = top_candidate.get("value_normalized")
            result.final_value_code = top_candidate.get("value_code")
            result.confidence = top_candidate.get("confidence")
            result.selection_reason = "auto_filled_from_candidates"

        result = post_process_result(result, field_spec)
        cleaned_results.append(result)

    parsed.results = cleaned_results
    return parsed

def write_debug_response(response: Any, debug_path: str | None) -> None:
    if not debug_path:
        return
    p = Path(debug_path)
    if response is None:
        p.write_text("<NONE>", encoding="utf-8")
        return
    if hasattr(response, "model_dump_json"):
        try:
            p.write_text(response.model_dump_json(indent=2), encoding="utf-8")
            return
        except TypeError:
            p.write_text(response.model_dump_json(), encoding="utf-8")
            return
    if hasattr(response, "model_dump"):
        try:
            payload = response.model_dump()
            p.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            return
        except Exception:
            pass
    if hasattr(response, "dict"):
        try:
            payload = response.dict()
            p.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            return
        except Exception:
            pass
    p.write_text(str(response), encoding="utf-8")


def normalize_json_response_text(content: str) -> str:
    text = content.strip()
    if not text:
        return text

    fenced_match = re.match(r"^```(?:json|JSON)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fenced_match:
        inner = fenced_match.group(1).strip()
        if inner:
            return inner

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
        candidate = text[first_brace:last_brace + 1].strip()
        if candidate.startswith("{") and candidate.endswith("}"):
            return candidate

    first_bracket = text.find("[")
    last_bracket = text.rfind("]")
    if first_bracket != -1 and last_bracket != -1 and first_bracket < last_bracket:
        candidate = text[first_bracket:last_bracket + 1].strip()
        if candidate.startswith("[") and candidate.endswith("]"):
            return candidate

    return text


def response_finish_reason(response: Any) -> str | None:
    direct_reason = getattr(response, "finish_reason", None)
    if direct_reason:
        return str(direct_reason).strip().lower()

    raw = getattr(response, "raw", None)
    if not isinstance(raw, dict):
        return None
    choices = raw.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        choice_reason = choices[0].get("finish_reason")
        if choice_reason:
            return str(choice_reason).strip().lower()
    raw_reason = raw.get("finish_reason") or raw.get("done_reason")
    if raw_reason:
        return str(raw_reason).strip().lower()
    return None


def _unique_provider_names(values: list[str | None]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for value in values:
        name = _safe_metadata_text(value)
        if not name:
            continue
        normalized = name.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        names.append(normalized)
    return names


def _settings_with_ignored_providers(
    settings: dict[str, Any],
    ignored_providers: list[str] | None,
) -> dict[str, Any]:
    names = _unique_provider_names(ignored_providers or [])
    if not names:
        return settings

    scoped_settings = deepcopy(settings)
    raw_extra_body = scoped_settings.get("extra_body")
    extra_body = deepcopy(raw_extra_body) if isinstance(raw_extra_body, dict) else {}
    raw_provider = extra_body.get("provider")
    provider_preferences = deepcopy(raw_provider) if isinstance(raw_provider, dict) else {}
    existing_ignored = provider_preferences.get("ignore")
    provider_preferences["ignore"] = _unique_provider_names(
        [*(existing_ignored if isinstance(existing_ignored, list) else []), *names]
    )
    extra_body["provider"] = provider_preferences
    scoped_settings["extra_body"] = extra_body
    return scoped_settings


def _response_metadata(response: Any) -> tuple[str | None, str | None]:
    provider_name = getattr(response, "provider", None)
    request_id = getattr(response, "request_id", None)
    raw = getattr(response, "raw", None)
    if isinstance(raw, dict):
        provider_name = provider_name or raw.get("provider")
        request_id = request_id or raw.get("id")
    return _safe_metadata_text(provider_name), _safe_metadata_text(request_id)


def _call_llm_with_metadata(
    config: ProjectConfig,
    messages: list[dict[str, Any]],
    *,
    schema: dict[str, Any] | None = None,
    ignored_providers: list[str] | None = None,
) -> ModelCallResult:
    app_settings = load_json("app_config.json")
    output_schema = schema if schema is not None else ModelExtractionResponse.model_json_schema()
    llm_settings = merge_llm_settings(app_settings.get("llm", {}), config.llm)
    llm_settings = _settings_with_ignored_providers(llm_settings, ignored_providers)
    provider = create_provider(llm_settings)
    response = provider.generate(messages, output_schema, llm_settings)

    write_debug_response(response.raw if getattr(response, "raw", None) is not None else response, config.debug_path)
    provider_name, request_id = _response_metadata(response)
    if response_finish_reason(response) == "length":
        raise ModelOutputError("truncated", provider_name, request_id)
    content = response.content
    if content:
        return ModelCallResult(
            content=normalize_json_response_text(content),
            provider_name=provider_name,
            request_id=request_id,
        )

    if llm_settings.get("think", False):
        print("LLM provider returned empty message.content with thinking enabled. Retrying with thinking disabled...")
        retry_settings = deepcopy(llm_settings)
        retry_settings["think"] = False
        retry_provider = create_provider(retry_settings)
        retry_response = retry_provider.generate(messages, output_schema, retry_settings)
        write_debug_response(
            retry_response.raw if getattr(retry_response, "raw", None) is not None else retry_response,
            config.debug_path,
        )
        retry_provider_name, retry_request_id = _response_metadata(retry_response)
        if response_finish_reason(retry_response) == "length":
            raise ModelOutputError("truncated", retry_provider_name, retry_request_id)
        if retry_response.content:
            return ModelCallResult(
                content=normalize_json_response_text(retry_response.content),
                provider_name=retry_provider_name,
                request_id=retry_request_id,
            )
        raise ModelOutputError(
            "empty_content_after_thinking_retry",
            retry_provider_name,
            retry_request_id,
        )

    raise ModelOutputError("empty_content", provider_name, request_id)


def call_llm(
    config: ProjectConfig,
    messages: list[dict[str, Any]],
    schema: dict[str, Any] | None = None,
) -> str:
    """Return normalized model JSON while preserving the existing public API."""

    return _call_llm_with_metadata(config, messages, schema=schema).content

def get_response(config: ProjectConfig, data_dictionary: dict[str, Any], document_text: str) -> ExtractionResponse:
    app_settings = load_json("app_config.json")
    responses: list[ExtractionFieldResult] = []
    for form_name, fields in data_dictionary.items():
        for chunk in chunk_fields(fields, config.batch_size or app_settings.get("default_batch_size", 10)):
            response = run_batch_with_fallback(config, document_text, chunk)
            responses += response.results

    return ExtractionResponse(project_name=config.project_name, results=responses)


def run(config: str, case_text: str, output: str | None = None):
    config = load_project_config(config)
    data_dictionary = load_data_dictionary(config)

    if not data_dictionary:
        raise ValueError("No fields found in the data dictionary.")

    document_text = load_file(case_text)

    merged_response = get_response(config, data_dictionary, document_text)

    if output:
        with open(output, "w", encoding="utf-8") as f:
            json.dump(merged_response.model_dump(), f, ensure_ascii=False, indent=2)

    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--case-text", required=True)
    parser.add_argument("--output", required=False, help="Path to write the merged extraction results as JSON")
    args = parser.parse_args()

    run(args.config, args.case_text, args.output)

if __name__ == "__main__":
    main()
