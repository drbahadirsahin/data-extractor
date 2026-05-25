from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Iterable
from urllib import error, parse, request

from data_entry_store import IdentityHashEntry, RedcapDataValue, RemoteRecordManifest
from http_client import urlopen
from redcap_client import build_redcap_api_url_candidates, extract_xml_error_message


class DataEntrySyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class DataEntrySyncConfig:
    api_url: str
    prefix: str = "tc_hash"
    manifest_action: str = "get-sync-manifest"
    record_data_action: str = "get-record-data"
    identity_hash_action: str = "get-identity-hash-map"
    timeout_seconds: int = 60

    @property
    def enabled(self) -> bool:
        return bool(self.api_url.strip() and self.prefix.strip())


@dataclass(frozen=True)
class SyncManifestResponse:
    project_id: str | None
    dag_unique_name: str | None
    identity_hash_updated_at: str | None
    records: list[RemoteRecordManifest]
    raw: Any


@dataclass(frozen=True)
class RecordDataResponse:
    project_id: str | None
    values: list[RedcapDataValue]
    raw: Any


@dataclass(frozen=True)
class IdentityHashMapResponse:
    project_id: str | None
    entries: list[IdentityHashEntry]
    raw: Any


WIDE_RECORD_META_KEYS = {
    "project_id",
    "record",
    "record_id",
    "id",
    "event_id",
    "redcap_event_name",
    "event",
    "redcap_repeat_instrument",
    "redcap_repeat_instance",
    "instance",
    "redcap_data_access_group",
    "dag_unique_name",
    "data_access_group_unique_name",
    "dag",
    "sync_updated_at",
    "record_last_modified_at",
    "remote_updated_at",
    "last_modified_at",
    "identity_hash_updated_at",
    "identity_updated_at",
}


class DataEntrySyncClient:
    def __init__(self, config: DataEntrySyncConfig, api_token: str) -> None:
        self.config = config
        self.api_token = api_token.strip()
        self.api_urls = build_redcap_api_url_candidates(config.api_url)

    def get_sync_manifest(self, *, since: str | None = None) -> SyncManifestResponse:
        response = self._post_external_module(
            self._payload_with_optional_params(
                {"action": self.config.manifest_action},
                since=since,
            )
        )
        return parse_sync_manifest_response(response)

    def get_record_data(
        self,
        *,
        records: Iterable[str] | None = None,
        fields: Iterable[str] | None = None,
        events: Iterable[str] | None = None,
        since: str | None = None,
    ) -> RecordDataResponse:
        response = self._post_external_module(
            self._payload_with_optional_params(
                {"action": self.config.record_data_action},
                records=records,
                fields=fields,
                events=events,
                since=since,
            )
        )
        return parse_record_data_response(response)

    def get_identity_hash_map(self, *, since: str | None = None) -> IdentityHashMapResponse:
        response = self._post_external_module(
            self._payload_with_optional_params(
                {"action": self.config.identity_hash_action},
                since=since,
            )
        )
        return parse_identity_hash_map_response(response)

    def _payload_with_optional_params(
        self,
        payload: dict[str, Any],
        *,
        records: Iterable[str] | None = None,
        fields: Iterable[str] | None = None,
        events: Iterable[str] | None = None,
        since: str | None = None,
    ) -> dict[str, Any]:
        for key, value in {
            "records": records,
            "fields": fields,
            "events": events,
        }.items():
            encoded = encode_list_param(value)
            if encoded is not None:
                payload[key] = encoded
        if since:
            payload["since"] = str(since)
        return payload

    def _post_external_module(self, extra_payload: dict[str, Any]) -> Any:
        payload = {
            "token": self.api_token,
            "content": "externalModule",
            "prefix": self.config.prefix,
            "format": "json",
            "returnFormat": "json",
        }
        payload.update(extra_payload)
        action = str(payload.get("action") or "")
        logging.info(
            "Data-entry sync external module request: api_urls=%s prefix=%s action=%s params=%s",
            ", ".join(self.api_urls),
            payload.get("prefix"),
            action,
            ", ".join(sorted(key for key in payload.keys() if key != "token")),
        )

        last_http_error: error.HTTPError | None = None
        last_response_body = ""
        for api_url in self.api_urls:
            try:
                response = self._post_form_once(api_url, payload)
                logging.info(
                    "Data-entry sync external module response received: api_url=%s action=%s type=%s",
                    api_url,
                    action,
                    type(response).__name__,
                )
                return response
            except error.HTTPError as exc:
                response_body = exc.read().decode("utf-8", errors="replace")
                last_http_error = exc
                last_response_body = response_body
                logging.info(
                    "Data-entry sync external module HTTP error: api_url=%s action=%s code=%s body=%s",
                    api_url,
                    action,
                    exc.code,
                    response_body[:500],
                )
                if exc.code in {404, 405, 501}:
                    continue
                raise DataEntrySyncError(
                    f"Data-entry sync request failed with HTTP {exc.code}: {response_body[:500]}"
                ) from exc
            except error.URLError as exc:
                raise DataEntrySyncError(f"Data-entry sync request failed: {exc.reason}") from exc

        if last_http_error is not None:
            raise DataEntrySyncError(
                "Data-entry sync request failed. Tried these endpoints: "
                f"{', '.join(self.api_urls)}. "
                f"Last HTTP {last_http_error.code}: {last_response_body[:500]}"
            ) from last_http_error
        raise DataEntrySyncError("Data-entry sync request failed for an unknown reason.")

    def _post_form_once(self, api_url: str, payload: dict[str, Any]) -> Any:
        body = parse.urlencode(payload).encode("utf-8")
        http_request = request.Request(
            url=api_url,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json, application/xml, text/xml;q=0.9, */*;q=0.8",
                "User-Agent": "llm-extractor/1.0",
            },
            method="POST",
        )
        with urlopen(http_request, timeout=self.config.timeout_seconds) as response:
            raw = response.read().decode("utf-8")
        return parse_external_module_response(raw)


def load_data_entry_sync_config(app_config: dict[str, Any], *, api_url: str | None = None) -> DataEntrySyncConfig:
    payload = app_config.get("data_entry_sync", {}) if isinstance(app_config, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    identity_payload = app_config.get("identity_registry", {}) if isinstance(app_config, dict) else {}
    if not isinstance(identity_payload, dict):
        identity_payload = {}
    resolved_api_url = api_url or payload.get("api_url") or identity_payload.get("api_url") or identity_payload.get("base_url") or ""
    return DataEntrySyncConfig(
        api_url=str(resolved_api_url or ""),
        prefix=str(payload.get("prefix") or identity_payload.get("prefix") or "tc_hash"),
        manifest_action=str(payload.get("manifest_action") or "get-sync-manifest"),
        record_data_action=str(payload.get("record_data_action") or "get-record-data"),
        identity_hash_action=str(payload.get("identity_hash_action") or "get-identity-hash-map"),
        timeout_seconds=int(payload.get("timeout_seconds", 60) or 60),
    )


def parse_external_module_response(raw: str) -> Any:
    stripped = raw.strip()
    if not stripped:
        return {}
    if "<error>" in stripped.lower():
        raise DataEntrySyncError(extract_xml_error_message(stripped))
    if stripped.startswith("{") or stripped.startswith("["):
        payload = json.loads(stripped)
        if isinstance(payload, dict) and payload.get("error") not in {None, ""}:
            raise DataEntrySyncError(str(payload.get("error")))
        return payload
    parsed_form = parse.parse_qs(stripped, keep_blank_values=True)
    if parsed_form:
        return {key: values[0] if values else "" for key, values in parsed_form.items()}
    return stripped


def parse_sync_manifest_response(payload: Any) -> SyncManifestResponse:
    data = unwrap_payload(payload)
    if isinstance(data, list):
        records_payload = data
        root: dict[str, Any] = {}
    elif isinstance(data, dict):
        root = data
        records_payload = first_list(root, ["records", "data", "rows", "manifest"])
    else:
        root = {}
        records_payload = []

    project_id = optional_text(root.get("project_id"))
    dag_unique_name = first_text(root, ["dag_unique_name", "data_access_group_unique_name", "dag"])
    top_identity_updated_at = first_text(root, ["identity_hash_updated_at", "identity_updated_at"])
    records: list[RemoteRecordManifest] = []
    for item in records_payload:
        if not isinstance(item, dict):
            continue
        record = first_text(item, ["record", "record_id", "id"])
        if not record:
            continue
        record_project_id = first_text(item, ["project_id"]) or project_id or ""
        record_last_modified_at = first_text(item, ["record_last_modified_at", "last_modified_at", "remote_updated_at"])
        identity_hash_updated_at = first_text(item, ["identity_hash_updated_at", "identity_updated_at"]) or top_identity_updated_at
        sync_updated_at = first_text(item, ["sync_updated_at"]) or max_timestamp(
            record_last_modified_at,
            identity_hash_updated_at,
        )
        records.append(
            RemoteRecordManifest(
                project_id=record_project_id,
                record=record,
                remote_updated_at=sync_updated_at or record_last_modified_at or identity_hash_updated_at or "",
                dag_unique_name=first_text(item, ["dag_unique_name", "data_access_group_unique_name", "dag"])
                or dag_unique_name,
                record_last_modified_at=record_last_modified_at,
                identity_hash_updated_at=identity_hash_updated_at,
            )
        )
    return SyncManifestResponse(
        project_id=project_id,
        dag_unique_name=dag_unique_name,
        identity_hash_updated_at=top_identity_updated_at,
        records=records,
        raw=payload,
    )


def parse_record_data_response(payload: Any) -> RecordDataResponse:
    data = unwrap_payload(payload)
    if isinstance(data, list):
        root: dict[str, Any] = {}
        records_payload = data
    elif isinstance(data, dict):
        root = nested_response_root(data)
        records_payload = [root] if looks_like_record_context(root) else first_record_payload(root)
    else:
        root = {}
        records_payload = []

    project_id = optional_text(root.get("project_id"))
    values: list[RedcapDataValue] = []

    if records_payload and all(isinstance(item, dict) and "field_name" in item for item in records_payload):
        values.extend(parse_record_rows(records_payload, root=root, record_context={}))
    else:
        for record_context in records_payload:
            if not isinstance(record_context, dict):
                continue
            values.extend(parse_record_context(record_context, root=root))

    return RecordDataResponse(project_id=project_id, values=values, raw=payload)


def first_record_payload(root: dict[str, Any]) -> list[Any]:
    for key in ["rows", "values", "record_data", "redcap_data", "data", "records"]:
        value = root.get(key)
        if isinstance(value, list):
            if not value or any(isinstance(item, dict) for item in value):
                return value
            continue
        if isinstance(value, dict):
            if looks_like_response_container(value):
                return [value] if looks_like_record_context(value) else first_record_payload(value)
            return record_mapping_to_contexts(value)
    return []


def nested_response_root(root: dict[str, Any]) -> dict[str, Any]:
    for key in ["payload", "result", "data"]:
        nested = root.get(key)
        if isinstance(nested, dict) and looks_like_response_container(nested):
            return nested_response_root(nested)
    return root


def record_mapping_to_contexts(value: dict[str, Any]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for record_key, record_payload in value.items():
        if isinstance(record_payload, list):
            contexts.append({"record": str(record_key), "rows": record_payload})
        elif isinstance(record_payload, dict):
            merged = dict(record_payload)
            merged.setdefault("record", str(record_key))
            contexts.append(merged)
        else:
            contexts.append({"record": str(record_key), "value": record_payload})
    return contexts


def looks_like_record_context(value: dict[str, Any]) -> bool:
    if first_text(value, ["record", "record_id"]):
        return True
    return bool("field_name" in value or "field" in value)


def looks_like_response_container(value: dict[str, Any]) -> bool:
    if any(key in value for key in ["records", "rows", "values", "record_data", "redcap_data"]):
        return True
    return "project_id" in value and not looks_like_record_context(value)


def parse_record_context(record_context: dict[str, Any], *, root: dict[str, Any]) -> list[RedcapDataValue]:
    if "field_name" in record_context or "field" in record_context:
        return parse_record_rows([record_context], root=root, record_context={})
    parsed: list[RedcapDataValue] = []
    for key in ["rows", "values", "fields", "redcap_data", "data"]:
        nested = record_context.get(key)
        if isinstance(nested, list):
            parsed.extend(parse_nested_record_list(nested, root=root, record_context=record_context))
        elif isinstance(nested, dict):
            parsed.extend(parse_nested_record_dict(nested, root=root, record_context=record_context))
    if parsed:
        return parsed
    return parse_wide_record_row(record_context, root=root)


def parse_nested_record_list(
    rows: list[Any],
    *,
    root: dict[str, Any],
    record_context: dict[str, Any],
) -> list[RedcapDataValue]:
    dict_rows = [row for row in rows if isinstance(row, dict)]
    if not dict_rows:
        return []
    if all("field_name" in row or "field" in row for row in dict_rows):
        return parse_record_rows(dict_rows, root=root, record_context=record_context)
    parsed: list[RedcapDataValue] = []
    for row in dict_rows:
        merged = dict(row)
        for key in WIDE_RECORD_META_KEYS:
            if key in record_context and key not in merged:
                merged[key] = record_context[key]
        parsed.extend(parse_wide_record_row(merged, root=root))
    return parsed


def parse_nested_record_dict(
    values: dict[str, Any],
    *,
    root: dict[str, Any],
    record_context: dict[str, Any],
) -> list[RedcapDataValue]:
    if "field_name" in values or "field" in values:
        return parse_record_rows([values], root=root, record_context=record_context)
    parsed: list[RedcapDataValue] = []
    nested_context = dict(record_context)
    for key in WIDE_RECORD_META_KEYS:
        if key in values:
            nested_context[key] = values[key]
    for key in ["rows", "values", "fields", "redcap_data", "data"]:
        nested = values.get(key)
        if isinstance(nested, list):
            parsed.extend(parse_nested_record_list(nested, root=root, record_context=nested_context))
        elif isinstance(nested, dict) and nested is not values:
            parsed.extend(parse_nested_record_dict(nested, root=root, record_context=nested_context))
    if parsed:
        return parsed
    wide_row = dict(record_context)
    wide_row.update(values)
    return parse_wide_record_row(wide_row, root=root)


def parse_record_rows(
    rows: list[Any],
    *,
    root: dict[str, Any],
    record_context: dict[str, Any],
) -> list[RedcapDataValue]:
    parsed: list[RedcapDataValue] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        field_name = first_text(row, ["field_name", "field"])
        record = first_text(row, ["record", "record_id"]) or first_text(record_context, ["record", "record_id"])
        if not field_name or not record:
            continue
        project_id = first_text(row, ["project_id"]) or first_text(record_context, ["project_id"]) or first_text(root, ["project_id"])
        remote_updated_at = first_text(
            row,
            ["sync_updated_at", "record_last_modified_at", "remote_updated_at", "last_modified_at"],
        ) or first_text(
            record_context,
            ["sync_updated_at", "record_last_modified_at", "remote_updated_at", "last_modified_at"],
        )
        parsed.append(
            RedcapDataValue(
                project_id=project_id or "",
                event_id=first_text(row, ["event_id", "redcap_event_name", "event"]),
                record=record,
                field_name=field_name,
                value=optional_text(row.get("value")) or "",
                instance=first_text(row, ["instance", "redcap_repeat_instance"]),
                dag_unique_name=first_text(
                    row,
                    ["dag_unique_name", "data_access_group_unique_name", "redcap_data_access_group", "dag"],
                )
                or first_text(
                    record_context,
                    ["dag_unique_name", "data_access_group_unique_name", "redcap_data_access_group", "dag"],
                ),
                remote_updated_at=remote_updated_at,
            )
        )
    return parsed


def parse_wide_record_row(row: dict[str, Any], *, root: dict[str, Any]) -> list[RedcapDataValue]:
    record = first_text(row, ["record", "record_id"])
    if not record:
        return []
    project_id = first_text(row, ["project_id"]) or first_text(root, ["project_id"]) or ""
    event_id = first_text(row, ["event_id", "redcap_event_name", "event"])
    instance = first_text(row, ["instance", "redcap_repeat_instance"])
    dag_unique_name = first_text(
        row,
        ["dag_unique_name", "data_access_group_unique_name", "redcap_data_access_group", "dag"],
    )
    remote_updated_at = first_text(
        row,
        ["sync_updated_at", "record_last_modified_at", "remote_updated_at", "last_modified_at"],
    )
    values: list[RedcapDataValue] = []
    for key, raw_value in row.items():
        if key in WIDE_RECORD_META_KEYS:
            continue
        if isinstance(raw_value, (dict, list)):
            continue
        values.append(
            RedcapDataValue(
                project_id=project_id,
                event_id=event_id,
                record=record,
                field_name=str(key),
                value=optional_text(raw_value) or "",
                instance=instance,
                dag_unique_name=dag_unique_name,
                remote_updated_at=remote_updated_at,
            )
        )
    return values


def parse_identity_hash_map_response(payload: Any) -> IdentityHashMapResponse:
    data = unwrap_payload(payload)
    if isinstance(data, list):
        root: dict[str, Any] = {}
        rows = data
    elif isinstance(data, dict):
        root = data
        rows = first_list(root, ["rows", "data", "records", "hashes"])
    else:
        root = {}
        rows = []
    project_id = optional_text(root.get("project_id"))
    entries: list[IdentityHashEntry] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        record = first_text(row, ["record", "record_id"])
        identity_hash = first_text(row, ["identity_hash", "tc_hash", "hash"])
        if not record or not identity_hash:
            continue
        entries.append(
            IdentityHashEntry(
                project_id=first_text(row, ["project_id"]) or project_id or "",
                tc_hash=identity_hash,
                record=record,
                dag_unique_name=first_text(row, ["dag_unique_name", "data_access_group_unique_name", "dag"]),
                remote_updated_at=first_text(row, ["identity_hash_updated_at", "remote_updated_at", "updated_at"]),
            )
        )
    return IdentityHashMapResponse(project_id=project_id, entries=entries, raw=payload)


def unwrap_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        for key in ["payload", "result"]:
            nested = payload.get(key)
            if isinstance(nested, (dict, list)):
                return nested
    return payload


def first_list(payload: dict[str, Any], keys: list[str]) -> list[Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def first_text(payload: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = optional_text(payload.get(key))
        if value:
            return value
    return None


def optional_text(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)


def max_timestamp(*values: str | None) -> str | None:
    candidates = [str(value) for value in values if value]
    if not candidates:
        return None
    return max(candidates)


def encode_list_param(values: Iterable[str] | None) -> str | None:
    if values is None:
        return None
    cleaned = [str(value) for value in values if str(value) != ""]
    if not cleaned:
        return None
    return json.dumps(cleaned, ensure_ascii=False)
