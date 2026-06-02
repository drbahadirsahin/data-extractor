from __future__ import annotations

import re
from typing import Any


SIMPLE_DECIMAL_PATTERN = re.compile(r"^([+-]?)(?:(\d+)(?:([.,])(\d*))?|([.,])(\d+))$")


def is_redcap_integer_validation(validation: str | None) -> bool:
    return str(validation or "").strip().lower() == "integer"


def is_redcap_number_validation(validation: str | None) -> bool:
    normalized = str(validation or "").strip().lower()
    return normalized in {"number", "float"} or normalized.startswith("number_")


def is_redcap_numeric_validation(validation: str | None) -> bool:
    return is_redcap_integer_validation(validation) or is_redcap_number_validation(validation)


def normalize_redcap_numeric_text(value: Any, validation: str | None = None) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if is_redcap_integer_validation(validation):
        return normalize_integer_text(text)
    return normalize_decimal_text(text)


def normalize_integer_text(text: str) -> str:
    match = re.fullmatch(r"([+-]?)(\d+)", text)
    if not match:
        return text
    sign, digits = match.groups()
    normalized_digits = strip_leading_zeroes(digits)
    if normalized_digits == "0":
        sign = ""
    return f"{'-' if sign == '-' else ''}{normalized_digits}"


def normalize_decimal_text(text: str) -> str:
    if "," in text and "." in text:
        return text
    match = SIMPLE_DECIMAL_PATTERN.fullmatch(text)
    if not match:
        return text
    sign, integer_part, separator, fraction, leading_separator, leading_fraction = match.groups()
    integer = strip_leading_zeroes(integer_part or "0")
    fraction_part = fraction if separator else leading_fraction
    has_nonzero = any(char != "0" for char in f"{integer}{fraction_part or ''}")
    normalized_sign = "-" if sign == "-" and has_nonzero else ""
    if fraction_part is None or fraction_part == "":
        return f"{normalized_sign}{integer}"
    return f"{normalized_sign}{integer}.{fraction_part}"


def strip_leading_zeroes(value: str) -> str:
    stripped = str(value or "").lstrip("0")
    return stripped or "0"
