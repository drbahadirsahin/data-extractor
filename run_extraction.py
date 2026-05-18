import argparse
import json
from copy import deepcopy
import re

from project_config import load_project_config, ProjectConfig
from dictionary_parser import load_data_dictionary, FieldSpec
from helpers import  load_json
from document_parser import load_file
from typing import Any
from pathlib import Path
from llm_provider import create_provider, merge_llm_settings

from pydantic import BaseModel, ValidationError

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

def run_batch_with_fallback(config: ProjectConfig, document_text: str, fields: list[FieldSpec]) -> ExtractionResponse:
    try:
        response = run_single_batch(config, document_text, fields)
        return response
    except RuntimeError as exc:
        if str(exc) == "TRUNCATED_JSON":
            if config.batch_size == 1:
                raise ValueError("Batch size is 1, but model response was truncated. Try increasing max_tokens.") from exc
            if len(fields) == 1:
                raise ValueError("Only one field in the batch, but model response was truncated. Try increasing max_tokens.") from exc
            print("Model response was truncated. Retrying with smaller batch size...")
            smaller_chunk_size = max(1, config.batch_size // 2)
            left = run_batch_with_fallback(config, document_text, fields[:smaller_chunk_size])
            right = run_batch_with_fallback(config, document_text, fields[smaller_chunk_size:])
            return ExtractionResponse(project_name=config.project_name, results=left.results + right.results)
        else:
            raise

def run_single_batch(config: ProjectConfig, document_text:str, fields: list[FieldSpec]) -> ExtractionResponse:
    prompts = build_prompt(config, document_text, fields)
    raw_json = call_llm(config, prompts)

    try:
        parsed = ExtractionResponse.model_validate_json(raw_json)
    except ValidationError as exc:
        if "EOF while parsing" in str(exc):
            raise RuntimeError("TRUNCATED_JSON") from exc
        raise ValueError(
            f"Model returned invalid JSON schema: {exc}\n\nRaw response:\n{raw_json}"
        ) from exc

    return validate_and_fill_missing(config, parsed, fields)


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

def call_llm(config: ProjectConfig, messages: list[dict[str, Any]]) -> str:
    app_settings = load_json("app_config.json")
    schema = ExtractionResponse.model_json_schema()
    llm_settings = merge_llm_settings(app_settings.get("llm", {}), config.llm)
    provider = create_provider(llm_settings)
    response = provider.generate(messages, schema, llm_settings)

    write_debug_response(response.raw if getattr(response, "raw", None) is not None else response, config.debug_path)
    content = response.content
    thinking = response.thinking
    if content:
        return normalize_json_response_text(content)

    if llm_settings.get("think", False):
        print("LLM provider returned empty message.content with thinking enabled. Retrying with thinking disabled...")
        retry_settings = deepcopy(llm_settings)
        retry_settings["think"] = False
        retry_provider = create_provider(retry_settings)
        retry_response = retry_provider.generate(messages, schema, retry_settings)
        write_debug_response(
            retry_response.raw if getattr(retry_response, "raw", None) is not None else retry_response,
            config.debug_path,
        )
        if retry_response.content:
            return normalize_json_response_text(retry_response.content)
        raise ValueError(
            "LLM provider returned empty message.content both with thinking enabled and after retrying with thinking disabled. "
            f"Thinking preview: {thinking[:500] if thinking else '<NO THINKING>'} "
            f"| Retry thinking preview: {retry_response.thinking[:500] if retry_response.thinking else '<NO THINKING>'}"
        )

    raise ValueError(
        "LLM provider returned empty message.content. "
        f"Thinking preview: {thinking[:500] if thinking else '<NO THINKING>'}"
    )

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
