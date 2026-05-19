from __future__ import annotations

from typing import Any

OPENAI_COMPATIBLE_PROVIDER_NAMES = {"openai", "openai_compatible", "openrouter"}
GATEWAY_PROVIDER_NAMES = {"llm_gateway", "managed_gateway"}
REMOTE_CHAT_PROVIDER_NAMES = OPENAI_COMPATIBLE_PROVIDER_NAMES | GATEWAY_PROVIDER_NAMES
DIRECT_SECRET_KEYS = {"api_key", "gateway_client_token"}


def managed_llm_settings_from_config(app_config: dict[str, Any] | None) -> dict[str, Any] | None:
    config = app_config or {}
    llm = config.get("llm", {})
    if not isinstance(llm, dict):
        return None
    provider = normalize_provider_name(llm.get("provider"))
    if provider not in REMOTE_CHAT_PROVIDER_NAMES:
        return None
    base_url = str(llm.get("base_url") or "").strip()
    model = str(llm.get("model") or "").strip()
    if not base_url or not model:
        return None
    return sanitize_llm_settings(llm)


def sanitize_llm_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in dict(settings or {}).items()
        if str(key) not in DIRECT_SECRET_KEYS
    }


def normalize_provider_name(value: Any) -> str:
    return str(value or "").strip().lower()
