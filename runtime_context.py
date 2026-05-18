from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from helpers import load_json
from release_profile import is_user_profile
from secrets_store import SecretsStore
from settings_store import AppSettings, SettingsStore
from system_profile import InferenceRecommendation, SystemProfile, collect_system_profile, recommend_inference_mode


@dataclass
class RuntimeContext:
    app_home: Path
    settings: AppSettings
    settings_store: SettingsStore
    secrets_store: SecretsStore
    system_profile: SystemProfile
    inference_recommendation: InferenceRecommendation
    app_config: dict[str, Any]


def bootstrap_runtime(app_home: str | Path | None = None) -> RuntimeContext:
    settings_store = SettingsStore(app_home)
    settings = settings_store.load_or_create()
    secrets_store = SecretsStore(settings_store.app_home)
    system_profile = collect_system_profile()
    recommendation = recommend_inference_mode(system_profile)
    app_config = load_app_config()
    settings_changed = False
    if apply_managed_release_defaults(settings, app_config):
        settings_changed = True

    redcap_config = app_config.get("redcap", {})
    configured_api_url = coerce_optional_str(redcap_config.get("api_url"))
    if configured_api_url and settings.redcap.api_url != configured_api_url:
        settings.redcap.api_url = configured_api_url
        settings_changed = True

    if settings.last_system_recommendation != recommendation.mode:
        settings.last_system_recommendation = recommendation.mode
        if settings.inference.mode == "auto" and settings.inference.selected_provider is None:
            settings.inference.selected_provider = recommendation.mode
        settings_changed = True

    if settings_changed:
        settings_store.save(settings)

    return RuntimeContext(
        app_home=settings_store.app_home,
        settings=settings,
        settings_store=settings_store,
        secrets_store=secrets_store,
        system_profile=system_profile,
        inference_recommendation=recommendation,
        app_config=app_config,
    )


def load_app_config() -> dict[str, Any]:
    try:
        payload = load_json("app_config.json")
    except FileNotFoundError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def apply_managed_release_defaults(settings: AppSettings, app_config: dict[str, Any]) -> bool:
    if not is_user_profile(app_config):
        return False
    llm = app_config.get("llm", {})
    if not isinstance(llm, dict):
        llm = {}
    changed = False
    if settings.inference.mode != "managed":
        settings.inference.mode = "managed"
        changed = True
    if settings.inference.selected_provider != "openai_compatible":
        settings.inference.selected_provider = "openai_compatible"
        changed = True
    base_url = coerce_optional_str(llm.get("base_url"))
    if base_url and settings.inference.openai_compatible_base_url != base_url:
        settings.inference.openai_compatible_base_url = base_url
        changed = True
    model = coerce_optional_str(llm.get("model"))
    if model and settings.inference.openai_compatible_model != model:
        settings.inference.openai_compatible_model = model
        changed = True
    timeout = int(llm.get("timeout_seconds", settings.inference.timeout_seconds) or settings.inference.timeout_seconds)
    if settings.inference.timeout_seconds != timeout:
        settings.inference.timeout_seconds = timeout
        changed = True
    secret_name = coerce_optional_str(llm.get("api_key_secret_name"))
    if secret_name and settings.inference.api_key_secret_name != secret_name:
        settings.inference.api_key_secret_name = secret_name
        changed = True
    return changed


def coerce_optional_str(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)
