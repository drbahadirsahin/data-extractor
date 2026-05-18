from __future__ import annotations

import os
from typing import Any

DEFAULT_APP_VERSION = "0.1.0-early.1"


def release_config(app_config: dict[str, Any] | None) -> dict[str, Any]:
    config = app_config or {}
    release = config.get("release", {})
    return release if isinstance(release, dict) else {}


def app_version(app_config: dict[str, Any] | None) -> str:
    release = release_config(app_config)
    version = release.get("version") or (app_config or {}).get("version")
    return str(version or DEFAULT_APP_VERSION)


def release_profile(app_config: dict[str, Any] | None) -> str:
    env_profile = os.getenv("LLM_EXTRACTOR_PROFILE")
    if env_profile:
        return normalize_profile(env_profile)
    release = release_config(app_config)
    return normalize_profile(str(release.get("profile") or "user"))


def normalize_profile(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"dev", "developer", "advanced", "debug"}:
        return "dev"
    return "user"


def is_user_profile(app_config: dict[str, Any] | None) -> bool:
    return release_profile(app_config) == "user" and not is_dev_override_enabled()


def is_dev_override_enabled() -> bool:
    return os.getenv("LLM_EXTRACTOR_DEV_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def show_advanced_ui(app_config: dict[str, Any] | None) -> bool:
    if is_dev_override_enabled():
        return True
    release = release_config(app_config)
    features = release.get("features", {})
    if not isinstance(features, dict):
        features = {}
    if "show_advanced_ui" in features:
        return bool(features.get("show_advanced_ui"))
    return release_profile(app_config) == "dev"


def show_model_settings(app_config: dict[str, Any] | None) -> bool:
    if is_dev_override_enabled():
        return True
    release = release_config(app_config)
    features = release.get("features", {})
    if not isinstance(features, dict):
        features = {}
    if "show_model_settings" in features:
        return bool(features.get("show_model_settings"))
    return release_profile(app_config) == "dev"


def update_settings(app_config: dict[str, Any] | None) -> dict[str, Any]:
    release = release_config(app_config)
    updates = release.get("updates", {})
    return updates if isinstance(updates, dict) else {}


def startup_updates_enabled(app_config: dict[str, Any] | None) -> bool:
    updates = update_settings(app_config)
    if not updates:
        return False
    return bool(updates.get("enabled", False) and updates.get("check_on_startup", True))
