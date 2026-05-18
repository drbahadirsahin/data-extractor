from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CURRENT_SETTINGS_VERSION = 1
APP_HOME_ENV_VAR = "LLM_EXTRACTOR_HOME"
PORTABLE_MARKER = ".llm_extractor_portable"
PORTABLE_DIRNAME = ".llm_extractor_data"


@dataclass
class InferenceSettings:
    mode: str = "auto"
    selected_provider: str | None = None
    local_ollama_base_url: str = "http://127.0.0.1:11434"
    remote_ollama_base_url: str | None = None
    openai_compatible_base_url: str | None = None
    openai_compatible_model: str | None = None
    timeout_seconds: int = 600
    api_key_secret_name: str = "llm_api_key"

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "InferenceSettings":
        payload = payload or {}
        return cls(
            mode=str(payload.get("mode", "auto")),
            selected_provider=coerce_optional_str(payload.get("selected_provider")),
            local_ollama_base_url=str(payload.get("local_ollama_base_url", "http://127.0.0.1:11434")),
            remote_ollama_base_url=coerce_optional_str(payload.get("remote_ollama_base_url")),
            openai_compatible_base_url=coerce_optional_str(payload.get("openai_compatible_base_url")),
            openai_compatible_model=coerce_optional_str(payload.get("openai_compatible_model")),
            timeout_seconds=int(payload.get("timeout_seconds", 600)),
            api_key_secret_name=str(payload.get("api_key_secret_name", "llm_api_key")),
        )


@dataclass
class RedcapProjectToken:
    api_url: str
    project_id: str
    project_name: str
    token_secret_name: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "RedcapProjectToken | None":
        payload = payload or {}
        api_url = coerce_optional_str(payload.get("api_url"))
        project_id = coerce_optional_str(payload.get("project_id"))
        project_name = coerce_optional_str(payload.get("project_name"))
        token_secret_name = coerce_optional_str(payload.get("token_secret_name"))
        if not api_url or not project_id or not project_name or not token_secret_name:
            return None
        return cls(
            api_url=api_url,
            project_id=project_id,
            project_name=project_name,
            token_secret_name=token_secret_name,
        )


@dataclass
class RedcapSettings:
    api_url: str | None = None
    api_token_secret_name: str = "redcap_api_token"
    selected_project_id: str | None = None
    selected_project_name: str | None = None
    selected_project_token_secret_name: str | None = None
    saved_project_tokens: list[RedcapProjectToken] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "RedcapSettings":
        payload = payload or {}
        saved_project_tokens: list[RedcapProjectToken] = []
        for item in payload.get("saved_project_tokens", []):
            parsed = RedcapProjectToken.from_dict(item)
            if parsed is not None:
                saved_project_tokens.append(parsed)
        return cls(
            api_url=coerce_optional_str(payload.get("api_url")),
            api_token_secret_name=str(payload.get("api_token_secret_name", "redcap_api_token")),
            selected_project_id=coerce_optional_str(payload.get("selected_project_id")),
            selected_project_name=coerce_optional_str(payload.get("selected_project_name")),
            selected_project_token_secret_name=coerce_optional_str(payload.get("selected_project_token_secret_name")),
            saved_project_tokens=saved_project_tokens,
        )


@dataclass
class UISettings:
    language: str = "tr"
    last_open_directory: str | None = None
    window_width: int = 1440
    window_height: int = 960

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "UISettings":
        payload = payload or {}
        return cls(
            language=str(payload.get("language", "tr")),
            last_open_directory=coerce_optional_str(payload.get("last_open_directory")),
            window_width=int(payload.get("window_width", 1440)),
            window_height=int(payload.get("window_height", 960)),
        )


@dataclass
class AppSettings:
    version: int = CURRENT_SETTINGS_VERSION
    first_run_completed: bool = False
    portable_mode: bool = False
    workspace_root: str | None = None
    preferred_project_config_path: str | None = None
    last_system_recommendation: str | None = None
    inference: InferenceSettings = field(default_factory=InferenceSettings)
    redcap: RedcapSettings = field(default_factory=RedcapSettings)
    ui: UISettings = field(default_factory=UISettings)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "AppSettings":
        payload = payload or {}
        return cls(
            version=int(payload.get("version", CURRENT_SETTINGS_VERSION)),
            first_run_completed=bool(payload.get("first_run_completed", False)),
            portable_mode=bool(payload.get("portable_mode", False)),
            workspace_root=coerce_optional_str(payload.get("workspace_root")),
            preferred_project_config_path=coerce_optional_str(payload.get("preferred_project_config_path")),
            last_system_recommendation=coerce_optional_str(payload.get("last_system_recommendation")),
            inference=InferenceSettings.from_dict(payload.get("inference")),
            redcap=RedcapSettings.from_dict(payload.get("redcap")),
            ui=UISettings.from_dict(payload.get("ui")),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["version"] = CURRENT_SETTINGS_VERSION
        return payload


class SettingsStore:
    def __init__(self, app_home: str | Path | None = None) -> None:
        self.app_home = ensure_app_home(app_home)
        self.settings_path = self.app_home / "settings.json"

    def load(self) -> AppSettings:
        if not self.settings_path.exists():
            return AppSettings(portable_mode=is_portable_mode(self.app_home))
        payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
        settings = AppSettings.from_dict(payload)
        settings.portable_mode = settings.portable_mode or is_portable_mode(self.app_home)
        return settings

    def save(self, settings: AppSettings) -> AppSettings:
        settings.version = CURRENT_SETTINGS_VERSION
        settings.portable_mode = settings.portable_mode or is_portable_mode(self.app_home)
        self.settings_path.write_text(
            json.dumps(settings.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        ensure_private_file_permissions(self.settings_path)
        return settings

    def load_or_create(self) -> AppSettings:
        settings = self.load()
        if not self.settings_path.exists():
            self.save(settings)
        return settings


def resolve_app_home(app_home: str | Path | None = None) -> Path:
    if app_home is not None:
        return Path(app_home).expanduser().resolve()
    env_home = os.getenv(APP_HOME_ENV_VAR)
    if env_home:
        return Path(env_home).expanduser().resolve()
    portable_root = find_portable_root()
    if portable_root is not None:
        return (portable_root / PORTABLE_DIRNAME).resolve()
    return (Path.cwd().resolve() / PORTABLE_DIRNAME).resolve()


def ensure_app_home(app_home: str | Path | None = None) -> Path:
    resolved = resolve_app_home(app_home)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def find_portable_root() -> Path | None:
    candidates = portable_root_candidates()
    for candidate in candidates:
        if (candidate / PORTABLE_MARKER).exists():
            return candidate
    if is_frozen_app() and candidates:
        return candidates[0]
    return None


def portable_root_candidates() -> list[Path]:
    candidates: list[Path] = []
    if is_frozen_app():
        candidates.extend(frozen_app_roots())
    candidates.append(Path.cwd().resolve())
    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def frozen_app_roots() -> list[Path]:
    executable = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        for parent in executable.parents:
            if parent.suffix == ".app":
                return [parent.parent.resolve(), parent.resolve()]
    return [executable.parent.resolve()]


def is_portable_mode(app_home: str | Path) -> bool:
    app_home_path = Path(app_home).resolve()
    portable_root = find_portable_root()
    if portable_root is None:
        return False
    return app_home_path == (portable_root / PORTABLE_DIRNAME).resolve()


def ensure_private_file_permissions(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        path.chmod(0o600)
    except PermissionError:
        pass


def coerce_optional_str(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)
