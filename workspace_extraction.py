from __future__ import annotations

import json
from dataclasses import dataclass

from dictionary_parser import load_data_dictionary
from document_parser import load_file
from project_config import ProjectConfig
from run_extraction import ExtractionFieldResult, ExtractionResponse, get_response


@dataclass
class PatientExtractionResult:
    queue_label: str
    patient_mode: str
    identifier_type: str | None
    identifier_value: str | None
    documents: list[str]
    document_results: list[tuple[str, ExtractionResponse]]
    merged_response: ExtractionResponse
    approved: bool = False


def extract_patient_documents(
    *,
    config: ProjectConfig,
    queue_label: str,
    patient_mode: str,
    identifier_type: str | None,
    identifier_value: str | None,
    documents: list[str],
) -> PatientExtractionResult:
    data_dictionary = load_data_dictionary(config)
    document_results: list[tuple[str, ExtractionResponse]] = []
    for document_path in documents:
        document_text = load_file(document_path)
        response = get_response(config, data_dictionary, document_text)
        document_results.append((document_path, response))

    merged_response = merge_document_responses(
        project_name=config.project_name,
        responses=[response for _, response in document_results],
    )
    return PatientExtractionResult(
        queue_label=queue_label,
        patient_mode=patient_mode,
        identifier_type=identifier_type,
        identifier_value=identifier_value,
        documents=list(documents),
        document_results=document_results,
        merged_response=merged_response,
    )


def merge_document_responses(*, project_name: str, responses: list[ExtractionResponse]) -> ExtractionResponse:
    field_order: list[str] = []
    grouped: dict[str, list[ExtractionFieldResult]] = {}
    for response in responses:
        for result in response.results:
            if result.field_name not in grouped:
                field_order.append(result.field_name)
                grouped[result.field_name] = []
            grouped[result.field_name].append(result)

    merged_results: list[ExtractionFieldResult] = []
    for field_name in field_order:
        merged_results.append(merge_field_results(grouped[field_name]))
    return ExtractionResponse(project_name=project_name, results=merged_results)


def merge_field_results(results: list[ExtractionFieldResult]) -> ExtractionFieldResult:
    ranked = sorted(results, key=result_rank_key, reverse=True)
    best = ranked[0].model_copy(deep=True)

    distinct_values = {
        json.dumps(result.final_value, ensure_ascii=False, sort_keys=True, default=str)
        for result in results
        if result.final_value is not None
    }
    if len(distinct_values) > 1:
        best.status = "conflict"
        best.needs_review = True
        review_reasons = list(best.review_reasons or [])
        if "multiple_documents_disagree" not in review_reasons:
            review_reasons.append("multiple_documents_disagree")
        best.review_reasons = review_reasons
        best.selection_reason = "multiple_documents_disagree"
    elif any(result.needs_review for result in results):
        best.needs_review = True
        best.review_reasons = dedupe_review_reasons(results)

    return best


def result_rank_key(result: ExtractionFieldResult) -> tuple[int, float]:
    status_rank = {
        "found": 4,
        "uncertain": 3,
        "conflict": 2,
        "not_found": 1,
    }.get(result.status, 0)
    confidence = float(result.confidence or 0.0)
    return status_rank, confidence


def dedupe_review_reasons(results: list[ExtractionFieldResult]) -> list[str]:
    seen: set[str] = set()
    reasons: list[str] = []
    for result in results:
        for reason in result.review_reasons or []:
            if reason in seen:
                continue
            seen.add(reason)
            reasons.append(reason)
    return reasons
