from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

from http_client import urlopen
from redcap_client import build_redcap_api_url_candidates, extract_xml_error_message


class IdentityRegistryError(RuntimeError):
    pass


@dataclass
class IdentityRegistryConfig:
    api_url: str
    prefix: str = "tc_hash"
    lookup_action: str = "lookup-record-by-tc"
    create_action: str = "create-record-by-tc"
    tc_field: str = "tc_identity"
    record_id_field: str = "record"
    timeout_seconds: int = 30

    @property
    def enabled(self) -> bool:
        return bool(self.api_url.strip() and self.prefix.strip() and self.lookup_action.strip())

    @property
    def can_create(self) -> bool:
        return bool(self.enabled and self.create_action.strip())


@dataclass
class IdentityRegistryCreateResult:
    record_id: str | None
    created: bool
    raw: Any


class IdentityRegistryClient:
    def __init__(self, config: IdentityRegistryConfig, api_token: str) -> None:
        self.config = config
        self.api_token = api_token.strip()
        self.api_urls = build_redcap_api_url_candidates(config.api_url)

    def lookup_record_id(self, tc_identity_no: str) -> str | None:
        response = self._post_external_module(
            {
                self.config.tc_field: tc_identity_no,
                "action": self.config.lookup_action,
            }
        )
        return parse_lookup_record_id(response, self.config.record_id_field)

    def create_record_by_tc(self, tc_identity_no: str) -> IdentityRegistryCreateResult:
        if not self.config.can_create:
            raise IdentityRegistryError("identity_registry_create_action_missing")
        response = self._post_external_module(
            {
                self.config.tc_field: tc_identity_no,
                "action": self.config.create_action,
            }
        )
        return parse_create_record_response(response, self.config.record_id_field)

    def _post_external_module(self, extra_payload: dict[str, Any]) -> Any:
        payload = {
            "token": self.api_token,
            "content": "externalModule",
            "prefix": self.config.prefix,
            "format": "json",
            "returnFormat": "json",
        }
        payload.update(extra_payload)

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
                raise IdentityRegistryError(
                    f"Identity registry request failed with HTTP {exc.code}: {response_body[:500]}"
                ) from exc
            except error.URLError as exc:
                raise IdentityRegistryError(f"Identity registry request failed: {exc.reason}") from exc

        if last_http_error is not None:
            raise IdentityRegistryError(
                "Identity registry request failed. Tried these endpoints: "
                f"{', '.join(self.api_urls)}. "
                f"Last HTTP {last_http_error.code}: {last_response_body[:500]}"
            ) from last_http_error
        raise IdentityRegistryError("Identity registry request failed for an unknown reason.")

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

        stripped = raw.strip()
        if not stripped:
            return {}
        if "<error>" in stripped.lower():
            raise IdentityRegistryError(extract_xml_error_message(stripped))
        if stripped.startswith("{") or stripped.startswith("["):
            return json.loads(stripped)
        parsed_form = parse.parse_qs(stripped, keep_blank_values=True)
        if parsed_form:
            return {key: values[0] if values else "" for key, values in parsed_form.items()}
        return stripped


def load_identity_registry_config(app_config: dict[str, Any]) -> IdentityRegistryConfig:
    payload = app_config.get("identity_registry", {}) if isinstance(app_config, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    return IdentityRegistryConfig(
        api_url=str(payload.get("api_url") or payload.get("base_url") or ""),
        prefix=str(payload.get("prefix", "tc_hash") or "tc_hash"),
        lookup_action=str(payload.get("lookup_action", "lookup-record-by-tc") or "lookup-record-by-tc"),
        create_action=str(
            payload.get("create_action")
            or payload.get("register_action")
            or "create-record-by-tc"
        ),
        tc_field=str(payload.get("tc_field", "tc_identity") or "tc_identity"),
        record_id_field=str(payload.get("record_id_field", "record") or "record"),
        timeout_seconds=int(payload.get("timeout_seconds", 30) or 30),
    )


def parse_lookup_record_id(payload: Any, record_id_field: str) -> str | None:
    if isinstance(payload, str):
        stripped = payload.strip()
        return stripped or None
    if isinstance(payload, list):
        for item in payload:
            value = parse_lookup_record_id(item, record_id_field)
            if value:
                return value
        return None
    if isinstance(payload, dict):
        if payload.get("found") in {False, "false", "False", 0, "0"}:
            return None
        direct = payload.get(record_id_field)
        if direct not in {None, ""}:
            return str(direct)
        matches = payload.get("matches")
        if isinstance(matches, list):
            for item in matches:
                if not isinstance(item, dict):
                    continue
                match_record = item.get(record_id_field)
                if match_record not in {None, ""}:
                    return str(match_record)
        nested = payload.get("data")
        if nested is not None:
            return parse_lookup_record_id(nested, record_id_field)
    return None


def parse_create_record_response(payload: Any, record_id_field: str) -> IdentityRegistryCreateResult:
    record_id = parse_lookup_record_id(payload, record_id_field)
    created = False
    if isinstance(payload, dict):
        created = payload.get("created") in {True, "true", "True", 1, "1"}
    return IdentityRegistryCreateResult(record_id=record_id, created=created, raw=payload)
