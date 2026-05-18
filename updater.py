from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys
import tempfile
import textwrap
from typing import Any
from urllib import request

from release_profile import app_version, update_settings


class UpdateError(RuntimeError):
    pass


def check_for_update(app_config: dict[str, Any]) -> dict[str, Any] | None:
    settings = update_settings(app_config)
    manifest_url = str(settings.get("manifest_url") or "").strip()
    if not manifest_url:
        return None
    manifest = fetch_json(manifest_url, timeout_seconds=int(settings.get("timeout_seconds", 8)))
    current = app_version(app_config)
    latest = str(manifest.get("version") or "").strip()
    if not latest or not version_is_newer(latest, current):
        return None
    platform_payload = platform_update_payload(manifest)
    if not platform_payload:
        return None
    return {
        "version": latest,
        "notes": manifest.get("notes") or "",
        "payload": platform_payload,
    }


def fetch_json(url: str, *, timeout_seconds: int) -> dict[str, Any]:
    with request.urlopen(url, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise UpdateError("Update manifest is not a JSON object.")
    return payload


def platform_update_payload(manifest: dict[str, Any]) -> dict[str, Any] | None:
    platforms = manifest.get("platforms")
    if not isinstance(platforms, dict):
        return None
    keys = platform_keys()
    for key in keys:
        payload = platforms.get(key)
        if isinstance(payload, dict) and payload.get("url"):
            return payload
    return None


def platform_keys() -> list[str]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "x64"
    if system == "darwin":
        return [f"macos-{arch}", "macos"]
    if system == "windows":
        return [f"windows-{arch}", "windows"]
    if system == "linux":
        return [f"linux-{arch}", "linux"]
    return [f"{system}-{arch}", system]


def version_is_newer(candidate: str, current: str) -> bool:
    return version_key(candidate) > version_key(current)


def version_key(value: str) -> tuple[tuple[int, ...], str]:
    text = str(value).strip().lstrip("v")
    main, _, suffix = text.partition("-")
    numbers: list[int] = []
    for part in main.split("."):
        try:
            numbers.append(int(part))
        except ValueError:
            numbers.append(0)
    while len(numbers) < 3:
        numbers.append(0)
    return tuple(numbers), suffix


def download_update(payload: dict[str, Any], *, progress_callback=None) -> Path:
    url = str(payload.get("url") or "").strip()
    if not url:
        raise UpdateError("Update payload does not contain a URL.")
    destination = Path(tempfile.mkdtemp(prefix="llm_extractor_update_")) / "update.zip"
    with request.urlopen(url, timeout=int(payload.get("timeout_seconds", 120))) as response:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        with destination.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total)
    expected_sha = str(payload.get("sha256") or "").strip().lower()
    if expected_sha:
        actual_sha = sha256_file(destination)
        if actual_sha.lower() != expected_sha:
            raise UpdateError("Downloaded update failed SHA-256 verification.")
    return destination


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def current_app_root() -> Path:
    executable = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        for parent in executable.parents:
            if parent.suffix == ".app":
                portable_root = parent.parent.resolve()
                if (portable_root / ".llm_extractor_portable").exists():
                    return portable_root
                return portable_root
    return executable.parent


def current_executable() -> Path:
    return Path(sys.executable).resolve()


def stage_update_and_restart(archive_path: Path) -> None:
    if not is_frozen_app():
        raise UpdateError("Self-update is only available for packaged applications.")
    app_root = current_app_root()
    executable = current_executable()
    if os.name == "nt":
        script_path = archive_path.parent / "apply_update.ps1"
        script_path.write_text(
            build_windows_apply_update_script(
                archive_path=archive_path,
                app_root=app_root,
                executable=executable,
                parent_pid=os.getpid(),
            ),
            encoding="utf-8",
        )
        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
            ],
            close_fds=True,
        )
        return

    script_path = archive_path.parent / "apply_update.sh"
    script_path.write_text(
        build_posix_apply_update_script(
            archive_path=archive_path,
            app_root=app_root,
            executable=executable,
            parent_pid=os.getpid(),
        ),
        encoding="utf-8",
    )
    script_path.chmod(0o700)
    subprocess.Popen(["/bin/sh", str(script_path)], close_fds=True)


def build_posix_apply_update_script(*, archive_path: Path, app_root: Path, executable: Path, parent_pid: int) -> str:
    archive = shlex.quote(str(archive_path))
    root = shlex.quote(str(app_root))
    exe = shlex.quote(str(executable))
    return textwrap.dedent(
        f"""
        #!/bin/sh
        set -eu
        ARCHIVE={archive}
        APP_ROOT={root}
        EXECUTABLE={exe}
        PARENT_PID={int(parent_pid)}

        i=0
        while kill -0 "$PARENT_PID" 2>/dev/null && [ "$i" -lt 120 ]; do
          sleep 0.5
          i=$((i + 1))
        done

        EXTRACT_DIR="$(mktemp -d /tmp/llm_extractor_update.XXXXXX)"
        unzip -q "$ARCHIVE" -d "$EXTRACT_DIR"
        CHILDREN="$(find "$EXTRACT_DIR" -mindepth 1 -maxdepth 1 ! -name __MACOSX)"
        CHILD_COUNT="$(printf "%s\\n" "$CHILDREN" | sed '/^$/d' | wc -l | tr -d ' ')"
        if [ "$CHILD_COUNT" = "1" ]; then
          SOURCE_ROOT="$CHILDREN"
        else
          SOURCE_ROOT="$EXTRACT_DIR"
        fi

        PRESERVE_ROOT="$(mktemp -d /tmp/llm_extractor_preserve.XXXXXX)"
        if [ -d "$APP_ROOT/.llm_extractor_data" ]; then
          mv "$APP_ROOT/.llm_extractor_data" "$PRESERVE_ROOT/.llm_extractor_data"
        fi

        BACKUP_ROOT="$APP_ROOT.old"
        rm -rf "$BACKUP_ROOT"
        if [ -e "$APP_ROOT" ]; then
          mv "$APP_ROOT" "$BACKUP_ROOT"
        fi
        mkdir -p "$(dirname "$APP_ROOT")"
        mv "$SOURCE_ROOT" "$APP_ROOT"
        if [ -d "$PRESERVE_ROOT/.llm_extractor_data" ] && [ ! -d "$APP_ROOT/.llm_extractor_data" ]; then
          mv "$PRESERVE_ROOT/.llm_extractor_data" "$APP_ROOT/.llm_extractor_data"
        fi
        rm -rf "$BACKUP_ROOT"

        APP_BUNDLE="$(find "$APP_ROOT" -maxdepth 1 -name '*.app' -type d | head -n 1)"
        if [ -n "$APP_BUNDLE" ] && command -v open >/dev/null 2>&1; then
          open "$APP_BUNDLE"
        elif [ -x "$EXECUTABLE" ]; then
          "$EXECUTABLE" >/dev/null 2>&1 &
        fi
        """
    ).strip()


def build_windows_apply_update_script(*, archive_path: Path, app_root: Path, executable: Path, parent_pid: int) -> str:
    return textwrap.dedent(
        f"""
        $ErrorActionPreference = "Stop"
        $Archive = {str(archive_path)!r}
        $AppRoot = {str(app_root)!r}
        $Executable = {str(executable)!r}
        $ParentPid = {int(parent_pid)}

        for ($i = 0; $i -lt 120; $i++) {{
            $process = Get-Process -Id $ParentPid -ErrorAction SilentlyContinue
            if ($null -eq $process) {{ break }}
            Start-Sleep -Milliseconds 500
        }}

        $ExtractDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
        New-Item -ItemType Directory -Path $ExtractDir | Out-Null
        Expand-Archive -LiteralPath $Archive -DestinationPath $ExtractDir -Force
        $Children = Get-ChildItem -LiteralPath $ExtractDir | Where-Object {{ $_.Name -ne "__MACOSX" }}
        if ($Children.Count -eq 1) {{
            $SourceRoot = $Children[0].FullName
        }} else {{
            $SourceRoot = $ExtractDir
        }}

        $PreserveRoot = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
        New-Item -ItemType Directory -Path $PreserveRoot | Out-Null
        $DataDir = Join-Path $AppRoot ".llm_extractor_data"
        $PreservedData = Join-Path $PreserveRoot ".llm_extractor_data"
        if (Test-Path -LiteralPath $DataDir) {{
            Move-Item -LiteralPath $DataDir -Destination $PreservedData
        }}

        $BackupRoot = "$AppRoot.old"
        if (Test-Path -LiteralPath $BackupRoot) {{
            Remove-Item -LiteralPath $BackupRoot -Recurse -Force
        }}
        if (Test-Path -LiteralPath $AppRoot) {{
            Rename-Item -LiteralPath $AppRoot -NewName ([System.IO.Path]::GetFileName($BackupRoot))
        }}
        Move-Item -LiteralPath $SourceRoot -Destination $AppRoot
        if ((Test-Path -LiteralPath $PreservedData) -and -not (Test-Path -LiteralPath $DataDir)) {{
            Move-Item -LiteralPath $PreservedData -Destination $DataDir
        }}
        if (Test-Path -LiteralPath $BackupRoot) {{
            Remove-Item -LiteralPath $BackupRoot -Recurse -Force
        }}
        if (Test-Path -LiteralPath $Executable) {{
            Start-Process -FilePath $Executable
        }}
        """
    ).strip()


def make_portable_marker(root: Path) -> None:
    (root / ".llm_extractor_portable").write_text("portable\n", encoding="utf-8")
