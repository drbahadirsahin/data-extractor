from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

from http_client import urlopen


@dataclass
class RedcapProject:
    project_id: str
    project_title: str
    is_longitudinal: bool | None = None


@dataclass
class RedcapUserContext:
    username: str | None = None
    data_access_group: str | None = None
    data_access_group_unique_name: str | None = None
    api_import: bool | None = None
    api_export: bool | None = None


@dataclass
class RedcapUserContextModuleConfig:
    enabled: bool = False
    prefix: str = "tc_hash"
    action: str = "get-api-user-context"

    @property
    def can_request(self) -> bool:
        return bool(self.enabled and self.prefix.strip() and self.action.strip())


class RedcapAPIError(RuntimeError):
    pass


class RedcapClient:
    def __init__(self, api_url: str, api_token: str, timeout_seconds: int = 60) -> None:
        self.api_urls = build_redcap_api_url_candidates(api_url)
        self.api_url = self.api_urls[0]
        self.api_token = api_token.strip()
        self.timeout_seconds = timeout_seconds

    def list_projects(self) -> list[RedcapProject]:
        """
        REDCap project tokens are generally scoped to one project. The API still uses
        the project metadata export endpoint, so callers should usually expect a
        single returned project.
        """
        payload = {
            "token": self.api_token,
            "content": "project",
            "format": "csv",
            "returnFormat": "json",
        }
        response = self._post_form(payload)
        return parse_project_response(response)

    def get_project(self) -> RedcapProject | None:
        projects = self.list_projects()
        if not projects:
            return None
        return projects[0]

    def export_metadata_csv(self) -> str:
        payload = {
            "token": self.api_token,
            "content": "metadata",
            "format": "csv",
            "returnFormat": "json",
        }
        response = self._post_form(payload)
        stripped = response.strip()
        if "<error>" in stripped.lower():
            raise RedcapAPIError(extract_xml_error_message(stripped))
        return response

    def export_instruments(self) -> dict[str, str]:
        payload = {
            "token": self.api_token,
            "content": "instrument",
            "format": "csv",
            "returnFormat": "json",
        }
        response = self._post_form(payload)
        stripped = response.strip()
        if "<error>" in stripped.lower():
            raise RedcapAPIError(extract_xml_error_message(stripped))
        return parse_instrument_response(stripped)

    def export_repeating_forms(self) -> list[str]:
        payload = {
            "token": self.api_token,
            "content": "repeatingFormsEvents",
            "format": "csv",
            "returnFormat": "json",
        }
        response = self._post_form(payload)
        stripped = response.strip()
        if "<error>" in stripped.lower():
            raise RedcapAPIError(extract_xml_error_message(stripped))
        return parse_repeating_forms_response(stripped)

    def export_repeating_events(self) -> list[str]:
        payload = {
            "token": self.api_token,
            "content": "repeatingFormsEvents",
            "format": "csv",
            "returnFormat": "json",
        }
        response = self._post_form(payload)
        stripped = response.strip()
        if "<error>" in stripped.lower():
            raise RedcapAPIError(extract_xml_error_message(stripped))
        return parse_repeating_events_response(stripped)

    def export_events(self) -> list[dict[str, Any]]:
        payload = {
            "token": self.api_token,
            "content": "event",
            "format": "json",
            "returnFormat": "json",
        }
        response = self._post_form(payload)
        stripped = response.strip()
        if "<error>" in stripped.lower():
            raise RedcapAPIError(extract_xml_error_message(stripped))
        return parse_json_or_csv_list(stripped)

    def export_form_event_mapping(self) -> dict[str, list[str]]:
        payload = {
            "token": self.api_token,
            "content": "formEventMapping",
            "format": "json",
            "returnFormat": "json",
        }
        response = self._post_form(payload)
        stripped = response.strip()
        if "<error>" in stripped.lower():
            raise RedcapAPIError(extract_xml_error_message(stripped))
        return parse_form_event_mapping_response(stripped)

    def export_users(self) -> list[dict[str, Any]]:
        payload = {
            "token": self.api_token,
            "content": "user",
            "format": "json",
            "returnFormat": "json",
        }
        response = self._post_form(payload)
        stripped = response.strip()
        if "<error>" in stripped.lower():
            raise RedcapAPIError(extract_xml_error_message(stripped))
        return parse_json_or_csv_list(stripped)

    def get_user_context(self, username_hint: str | None = None) -> RedcapUserContext:
        return infer_user_context(self.export_users(), username_hint=username_hint)

    def get_external_module_user_context(
        self,
        *,
        prefix: str = "tc_hash",
        action: str = "get-api-user-context",
    ) -> RedcapUserContext:
        payload = {
            "token": self.api_token,
            "content": "externalModule",
            "prefix": prefix,
            "action": action,
            "format": "json",
            "returnFormat": "json",
        }
        response = self._post_form(payload)
        return parse_external_module_user_context_response(response)

    def import_records(
        self,
        records: list[dict[str, Any]],
        *,
        overwrite_behavior: str = "normal",
        return_content: str = "ids",
        force_auto_number: bool = False,
    ) -> list[str]:
        payload = {
            "token": self.api_token,
            "content": "record",
            "action": "import",
            "format": "json",
            "type": "flat",
            "overwriteBehavior": overwrite_behavior,
            "returnContent": return_content,
            "returnFormat": "json",
            "forceAutoNumber": "true" if force_auto_number else "false",
            "data": json.dumps(records, ensure_ascii=False),
        }
        response = self._post_form(payload)
        stripped = response.strip()
        if "<error>" in stripped.lower():
            raise RedcapAPIError(extract_xml_error_message(stripped))
        return parse_import_record_response(stripped)

    def _post_form_once(self, api_url: str, payload: dict[str, Any]) -> str:
        body = parse.urlencode(payload).encode("utf-8")
        http_request = request.Request(
            url=api_url,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json, text/csv, application/xml, text/xml;q=0.9, */*;q=0.8",
                "User-Agent": "llm-extractor/1.0",
            },
            method="POST",
        )
        with urlopen(http_request, timeout=self.timeout_seconds) as response:
            return response.read().decode("utf-8")

    def _post_form(self, payload: dict[str, Any]) -> str:
        last_http_error: error.HTTPError | None = None
        last_response_body = ""
        for api_url in self.api_urls:
            try:
                return self._post_form_once(api_url, payload)
            except error.HTTPError as exc:
                response_body = exc.read().decode("utf-8", errors="replace")
                last_http_error = exc
                last_response_body = response_body
                if exc.code in {404, 405, 501}:
                    continue
                raise RedcapAPIError(
                    f"REDCap API request failed with HTTP {exc.code}: {response_body[:500]}"
                ) from exc
            except error.URLError as exc:
                raise RedcapAPIError(f"REDCap API request failed: {exc.reason}") from exc

        if last_http_error is not None:
            raise RedcapAPIError(
                "REDCap API request failed. Tried these endpoints: "
                f"{', '.join(self.api_urls)}. "
                f"Last HTTP {last_http_error.code}: {last_response_body[:500]}"
            ) from last_http_error
        raise RedcapAPIError("REDCap API request failed for an unknown reason.")


def coerce_project_value(item: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = item.get(key)
        if value not in {None, ""}:
            return str(value)
    return None


def coerce_optional_bool(value: Any) -> bool | None:
    if value in {None, ""}:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


def coerce_optional_text(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    text = str(value).strip()
    return text or None


def load_redcap_user_context_module_config(app_config: dict[str, Any]) -> RedcapUserContextModuleConfig:
    payload = app_config.get("redcap_user_context", {}) if isinstance(app_config, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    return RedcapUserContextModuleConfig(
        enabled=bool(payload.get("enabled", False)),
        prefix=str(payload.get("prefix", "tc_hash") or "tc_hash"),
        action=str(payload.get("action", "get-api-user-context") or "get-api-user-context"),
    )


def normalize_redcap_api_url(api_url: str) -> str:
    return build_redcap_api_url_candidates(api_url)[0]


def build_redcap_api_url_candidates(api_url: str) -> list[str]:
    cleaned = api_url.strip()
    if not cleaned:
        return []
    stripped = cleaned.rstrip("/")
    lowered = stripped.lower()
    candidates: list[str] = []

    if lowered.endswith("/api/index.php"):
        candidates.append(stripped)
        candidates.append(stripped[: -len("/index.php")] + "/")
    elif lowered.endswith("/api"):
        candidates.append(stripped + "/")
        candidates.append(stripped + "/index.php")
    elif "/api/" in lowered:
        candidates.append(stripped)
        if not lowered.endswith("/index.php"):
            candidates.append(stripped + "/index.php")
    else:
        candidates.append(stripped + "/api/")
        candidates.append(stripped + "/api/index.php")

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def parse_project_response(response: str) -> list[RedcapProject]:
    stripped = response.strip()
    if not stripped:
        return []
    lowered = stripped.lower()
    if "<error>" in lowered:
        raise RedcapAPIError(extract_xml_error_message(stripped))
    if stripped.startswith("{") or stripped.startswith("["):
        return parse_project_json_response(stripped)
    return parse_project_csv_response(stripped)


def parse_project_json_response(response: str) -> list[RedcapProject]:
    raw = json.loads(response)
    if isinstance(raw, dict):
        raw_items = [raw]
    elif isinstance(raw, list):
        raw_items = raw
    else:
        raise RedcapAPIError(f"Unexpected REDCap response type: {type(raw).__name__}")
    return build_projects_from_items(raw_items)


def parse_project_csv_response(response: str) -> list[RedcapProject]:
    reader = csv.DictReader(io.StringIO(response))
    return build_projects_from_items(list(reader))


def build_projects_from_items(raw_items: list[dict[str, Any]]) -> list[RedcapProject]:
    projects: list[RedcapProject] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        project_id = coerce_project_value(item, ["project_id", "project_id_int", "id"])
        project_title = coerce_project_value(item, ["project_title", "title", "name"])
        if not project_id or not project_title:
            continue
        projects.append(
            RedcapProject(
                project_id=project_id,
                project_title=project_title,
                is_longitudinal=coerce_optional_bool(item.get("is_longitudinal")),
            )
        )
    return projects


def extract_xml_error_message(response: str) -> str:
    start_tag = "<error>"
    end_tag = "</error>"
    lowered = response.lower()
    start = lowered.find(start_tag)
    end = lowered.find(end_tag)
    if start >= 0 and end > start:
        message = response[start + len(start_tag) : end].strip()
        if message:
            return f"REDCap API error: {message}"
    return f"REDCap API returned an error response: {response[:500]}"


def parse_instrument_response(response: str) -> dict[str, str]:
    stripped = response.strip()
    if not stripped:
        return {}
    if stripped.startswith("{") or stripped.startswith("["):
        raw = json.loads(stripped)
        raw_items = [raw] if isinstance(raw, dict) else raw
    else:
        raw_items = list(csv.DictReader(io.StringIO(stripped)))

    instruments: dict[str, str] = {}
    for row in raw_items:
        if not isinstance(row, dict):
            continue
        instrument_name = str(row.get("instrument_name") or row.get("form_name") or "").strip()
        instrument_label = str(row.get("instrument_label") or row.get("form_label") or "").strip()
        if instrument_name:
            instruments[instrument_name] = instrument_label or instrument_name
    return instruments


def parse_repeating_forms_response(response: str) -> list[str]:
    raw_items = parse_json_or_csv_list(response)
    repeating_forms: list[str] = []
    seen: set[str] = set()
    for row in raw_items:
        if not isinstance(row, dict):
            continue
        form_name = str(row.get("form_name") or row.get("instrument_name") or "").strip()
        if not form_name or form_name in seen:
            continue
        seen.add(form_name)
        repeating_forms.append(form_name)
    return repeating_forms


def parse_repeating_events_response(response: str) -> list[str]:
    raw_items = parse_json_or_csv_list(response)
    repeating_events: list[str] = []
    seen: set[str] = set()
    for row in raw_items:
        if not isinstance(row, dict):
            continue
        form_name = str(row.get("form_name") or row.get("instrument_name") or "").strip()
        if form_name:
            continue
        event_name = str(row.get("event_name") or row.get("unique_event_name") or "").strip()
        if not event_name or event_name in seen:
            continue
        seen.add(event_name)
        repeating_events.append(event_name)
    return repeating_events


def parse_import_record_response(response: str) -> list[str]:
    stripped = response.strip()
    if not stripped:
        return []
    if stripped.startswith("{") or stripped.startswith("["):
        raw = json.loads(stripped)
        if isinstance(raw, list):
            return [str(item) for item in raw if item not in {None, ""}]
        if isinstance(raw, dict):
            ids = raw.get("ids")
            if isinstance(ids, list):
                return [str(item) for item in ids if item not in {None, ""}]
            for key in ["record_id", "id", "count"]:
                value = raw.get(key)
                if value not in {None, ""}:
                    return [str(value)]
            return []
    if stripped.isdigit():
        return [stripped]
    return [stripped]


def parse_json_or_csv_list(response: str) -> list[dict[str, Any]]:
    stripped = response.strip()
    if not stripped:
        return []
    if stripped.startswith("{") or stripped.startswith("["):
        raw = json.loads(stripped)
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
        if isinstance(raw, dict):
            return [raw]
        return []
    return [item for item in csv.DictReader(io.StringIO(stripped))]


def parse_external_module_user_context_response(response: str) -> RedcapUserContext:
    stripped = response.strip()
    if not stripped:
        return RedcapUserContext()
    if "<error>" in stripped.lower():
        raise RedcapAPIError(extract_xml_error_message(stripped))
    if stripped.startswith("{") or stripped.startswith("["):
        raw = json.loads(stripped)
    else:
        parsed_form = parse.parse_qs(stripped, keep_blank_values=True)
        raw = {key: values[0] if values else "" for key, values in parsed_form.items()}
    return user_context_from_external_module_payload(raw)


def user_context_from_external_module_payload(payload: Any) -> RedcapUserContext:
    if isinstance(payload, list):
        for item in payload:
            context = user_context_from_external_module_payload(item)
            if has_redcap_user_context_value(context):
                return context
        return RedcapUserContext()
    if not isinstance(payload, dict):
        return RedcapUserContext()

    for key in ["data", "context", "user_context", "api_user_context"]:
        nested = payload.get(key)
        if isinstance(nested, (dict, list)):
            context = user_context_from_external_module_payload(nested)
            if has_redcap_user_context_value(context):
                return context
    return build_user_context(payload)


def has_redcap_user_context_value(context: RedcapUserContext | None) -> bool:
    if context is None:
        return False
    return any(
        [
            context.username,
            context.data_access_group,
            context.data_access_group_unique_name,
        ]
    )


def parse_form_event_mapping_response(response: str) -> dict[str, list[str]]:
    items = parse_json_or_csv_list(response)
    mapping: dict[str, list[str]] = {}
    for item in items:
        form_name = (
            item.get("form")
            or item.get("form_name")
            or item.get("instrument")
            or item.get("instrument_name")
        )
        unique_event_name = item.get("unique_event_name") or item.get("event")
        if not form_name or not unique_event_name:
            continue
        form_key = str(form_name).strip()
        event_key = str(unique_event_name).strip()
        if not form_key or not event_key:
            continue
        bucket = mapping.setdefault(form_key, [])
        if event_key not in bucket:
            bucket.append(event_key)
    return mapping


def infer_user_context(users: list[dict[str, Any]], username_hint: str | None = None) -> RedcapUserContext:
    if not users:
        return RedcapUserContext()
    normalized_hint = (username_hint or "").strip().lower()
    if normalized_hint:
        for row in users:
            username = coerce_optional_text(
                row.get("username") or row.get("user") or row.get("redcap_user") or row.get("user_name")
            )
            if username and username.lower() == normalized_hint:
                return build_user_context(row)
    for row in users:
        marker = (
            row.get("current_user")
            or row.get("is_current_user")
            or row.get("api_user")
            or row.get("is_api_user")
        )
        if coerce_optional_bool(marker) is True:
            return build_user_context(row)
    if len(users) == 1:
        return build_user_context(users[0])
    return RedcapUserContext()


def build_user_context(row: dict[str, Any]) -> RedcapUserContext:
    username = coerce_optional_text(
        row.get("username") or row.get("user") or row.get("redcap_user") or row.get("user_name")
    )
    dag_label = coerce_optional_text(
        row.get("data_access_group")
        or row.get("redcap_data_access_group")
        or row.get("data_access_group_name")
        or row.get("dag")
        or row.get("dag_name")
    )
    dag_unique = coerce_optional_text(
        row.get("unique_group_name")
        or row.get("data_access_group_unique_name")
        or row.get("redcap_data_access_group")
        or row.get("data_access_group")
        or row.get("dag_unique_name")
        or row.get("dag")
    )
    return RedcapUserContext(
        username=username,
        data_access_group=dag_label,
        data_access_group_unique_name=dag_unique,
        api_import=coerce_optional_bool(row.get("api_import")),
        api_export=coerce_optional_bool(row.get("api_export")),
    )
