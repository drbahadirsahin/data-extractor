from __future__ import annotations

import json
from pathlib import Path

from settings_store import ensure_app_home, ensure_private_file_permissions


class SecretsStore:
    """
    Stores user-entered secrets on disk with restrictive file permissions.
    This is a convenience store, not a secure vault. Any secret needed to
    protect a server-side API key should live on a backend you control.
    """

    def __init__(self, app_home: str | Path | None = None) -> None:
        self.app_home = ensure_app_home(app_home)
        self.secrets_path = self.app_home / "secrets.json"

    def get(self, name: str, default: str | None = None) -> str | None:
        return self._load_payload().get(name, default)

    def set(self, name: str, value: str) -> None:
        payload = self._load_payload()
        payload[str(name)] = str(value)
        self._write_payload(payload)

    def delete(self, name: str) -> None:
        payload = self._load_payload()
        if name in payload:
            payload.pop(name, None)
            self._write_payload(payload)

    def has(self, name: str) -> bool:
        return name in self._load_payload()

    def list_names(self) -> list[str]:
        return sorted(self._load_payload().keys())

    def clear(self) -> None:
        self._write_payload({})

    def _load_payload(self) -> dict[str, str]:
        if not self.secrets_path.exists():
            return {}
        raw = json.loads(self.secrets_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        return {str(key): str(value) for key, value in raw.items()}

    def _write_payload(self, payload: dict[str, str]) -> None:
        self.secrets_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        ensure_private_file_permissions(self.secrets_path)
