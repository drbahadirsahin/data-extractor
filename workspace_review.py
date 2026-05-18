from __future__ import annotations

import json
from typing import Any

from run_extraction import ExtractionFieldResult
from workspace_extraction import PatientExtractionResult


def serialize_review_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def parse_review_value(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.lower() in {"true", "false"}:
        return stripped.lower() == "true"
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return stripped


def count_patient_result_status(result: PatientExtractionResult) -> tuple[int, int, int]:
    found_count = sum(1 for item in result.merged_response.results if item.status == "found")
    review_count = sum(1 for item in result.merged_response.results if item.needs_review)
    total_count = len(result.merged_response.results)
    return found_count, review_count, total_count


def build_patient_result_label(result: PatientExtractionResult) -> str:
    found_count, review_count, total_count = count_patient_result_status(result)
    approval = "approved" if result.approved else "pending"
    return (
        f"{result.queue_label} | {found_count}/{total_count} found | "
        f"{review_count} review | {approval}"
    )


def get_result_row_severity(result: ExtractionFieldResult) -> str:
    if result.status == "conflict":
        return "critical"
    if result.needs_review:
        return "warning"
    if result.status == "uncertain":
        return "warning"
    return "normal"


def format_candidates(result: ExtractionFieldResult) -> str:
    if not result.candidates:
        return ""
    lines: list[str] = []
    for candidate in result.candidates:
        value = candidate.get("value_normalized")
        evidence = candidate.get("evidence")
        confidence = candidate.get("confidence")
        lines.append(
            f"- {serialize_review_value(value)} | conf={confidence if confidence is not None else '-'}"
            f" | kanıt={evidence or '-'}"
        )
    return "\n".join(lines)

