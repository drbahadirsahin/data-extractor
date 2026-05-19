from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import platform
import re
import shlex
import subprocess
import sys
import tempfile
import textwrap
import time
from typing import Any
from urllib import request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from http_client import urlopen
from release_profile import app_version, update_settings


class UpdateError(RuntimeError):
    pass


PACKAGE_PLATFORM_PATTERN = re.compile(
    r"LLMExtractor-.+-(?P<platform>(?:macos|windows|linux)-[A-Za-z0-9_]+)$"
)


def check_for_update(app_config: dict[str, Any]) -> dict[str, Any] | None:
    settings = update_settings(app_config)
    manifest_url = str(settings.get("manifest_url") or "").strip()
    if not manifest_url:
        return None
    manifest = fetch_json(manifest_url, timeout_seconds=int(settings.get("timeout_seconds", 8)))
    current = app_version(app_config)
    latest = str(manifest.get("version") or "").strip()
    newer = bool(latest and version_is_newer(latest, current))
    logging.info(
        "Update manifest checked: current=%s latest=%s newer=%s platform_keys=%s",
        current,
        latest or "<missing>",
        newer,
        ",".join(platform_keys()),
    )
    if not newer:
        return None
    platform_payload = platform_update_payload(manifest)
    if not platform_payload:
        logging.warning("Update manifest has no payload for platform keys: %s", platform_keys())
        return None
    return {
        "version": latest,
        "notes": manifest.get("notes") or "",
        "payload": platform_payload,
    }


def fetch_json(url: str, *, timeout_seconds: int) -> dict[str, Any]:
    manifest_request = request.Request(
        cache_busted_url(url),
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": f"LLMExtractor/{int(time.time())}",
        },
    )
    with urlopen(manifest_request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise UpdateError("Update manifest is not a JSON object.")
    return payload


def cache_busted_url(url: str) -> str:
    split = urlsplit(str(url))
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    query["_llm_extractor_cache_bust"] = str(int(time.time() * 1000))
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))


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
    keys: list[str] = []

    def add_key(key: str) -> None:
        if key and key not in keys:
            keys.append(key)

    add_key(packaged_platform_key())
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "x64"
    if system == "darwin":
        add_key(f"macos-{arch}")
        add_key("macos")
    elif system == "windows":
        add_key(f"windows-{arch}")
        if arch == "arm64":
            add_key("windows-x64")
        add_key("windows")
    elif system == "linux":
        add_key(f"linux-{arch}")
        add_key("linux")
    else:
        add_key(f"{system}-{arch}")
        add_key(system)
    return keys


def packaged_platform_key() -> str | None:
    try:
        root = current_app_root()
    except Exception:
        return None
    match = PACKAGE_PLATFORM_PATTERN.match(root.name)
    if match:
        return match.group("platform")
    return None


def version_is_newer(candidate: str, current: str) -> bool:
    return version_key(candidate) > version_key(current)


def version_key(value: str) -> tuple[tuple[int, ...], int, tuple[tuple[int, int, str], ...]]:
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
    release_rank = 1 if not suffix else 0
    return tuple(numbers), release_rank, prerelease_key(suffix)


def prerelease_key(value: str) -> tuple[tuple[int, int, str], ...]:
    parts: list[tuple[int, int, str]] = []
    for part in re.split(r"[._-]+", value):
        if not part:
            continue
        if part.isdigit():
            parts.append((0, int(part), ""))
        else:
            parts.append((1, 0, part.lower()))
    return tuple(parts)


def download_update(payload: dict[str, Any], *, progress_callback=None) -> Path:
    url = str(payload.get("url") or "").strip()
    if not url:
        raise UpdateError("Update payload does not contain a URL.")
    destination = Path(tempfile.mkdtemp(prefix="llm_extractor_update_")) / "update.zip"
    with urlopen(url, timeout=int(payload.get("timeout_seconds", 120))) as response:
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
    validate_self_update_target()
    app_root = current_app_root()
    executable = current_executable()
    if os.name == "nt":
        script_path = archive_path.parent / "apply_update.ps1"
        launcher_path = archive_path.parent / "apply_update.cmd"
        script_path.write_text(
            build_windows_apply_update_script(
                archive_path=archive_path,
                app_root=app_root,
                executable=executable,
                parent_pid=os.getpid(),
            ),
            encoding="utf-8",
        )
        launcher_path.write_text(
            build_windows_update_launcher_script(
                script_path=script_path,
                app_root=app_root,
            ),
            encoding="utf-8",
        )
        stage_log = write_windows_stage_log(
            app_root=app_root,
            archive_path=archive_path,
            script_path=script_path,
            launcher_path=launcher_path,
        )
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 7
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
        launcher_command = windows_update_launcher_command(launcher_path)
        append_update_log(stage_log, f"Launcher command={launcher_command!r}")
        try:
            process = subprocess.Popen(
                launcher_command,
                close_fds=True,
                cwd=tempfile.gettempdir(),
                creationflags=creationflags,
                startupinfo=startupinfo,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            append_update_log(stage_log, f"Launcher process failed to start: {exc}")
            raise
        append_update_log(stage_log, f"Launcher process started with pid={process.pid}")
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
    logging.info("Starting update apply script: %s", script_path)
    subprocess.Popen(["/bin/sh", str(script_path)], close_fds=True)


def write_windows_stage_log(
    *,
    app_root: Path,
    archive_path: Path,
    script_path: Path,
    launcher_path: Path,
) -> Path:
    data_dir = app_root / ".llm_extractor_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / "update_stage.log"
    append_update_log(log_path, "Staging Windows update helper")
    append_update_log(log_path, f"APP_ROOT={app_root}")
    append_update_log(log_path, f"ARCHIVE={archive_path}")
    append_update_log(log_path, f"PS_SCRIPT={script_path}")
    append_update_log(log_path, f"CMD_LAUNCHER={launcher_path}")
    return log_path


def windows_update_launcher_command(launcher_path: Path) -> list[str]:
    return ["cmd.exe", "/d", "/c", str(launcher_path)]


def append_update_log(log_path: Path, message: str) -> None:
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {message}\n")
    except OSError:
        logging.exception("Could not write update log: %s", log_path)


def validate_self_update_target() -> None:
    executable = current_executable()
    if sys.platform != "darwin":
        return
    if is_macos_app_translocated(executable):
        raise UpdateError(
            "macOS uygulamayı geçici App Translocation konumundan çalıştırıyor; "
            "bu durumda güncelleme kalıcı uygulama klasörüne yazılamaz. "
            "Uygulamanın zipten çıkan LLMExtractor-... klasörünü seçerek macOS hazırlığını tamamlayın."
        )
    app_bundle = macos_app_bundle_for_executable(executable)
    if app_bundle is not None and not (app_bundle.parent / ".llm_extractor_portable").exists():
        raise UpdateError(
            "Otomatik güncelleme için LLMExtractor.app zipten çıkan LLMExtractor-... klasörünün içinde çalışmalıdır. "
            "Uygulamayı tek başına başka bir klasöre taşıdıysanız zip dosyasını yeniden açın ve uygulamayı üst klasörüyle birlikte çalıştırın."
        )


def is_macos_app_translocated(path: Path | None = None) -> bool:
    target = path or current_executable()
    return sys.platform == "darwin" and "AppTranslocation" in str(target)


def macos_app_bundle_for_executable(path: Path | None = None) -> Path | None:
    target = path or current_executable()
    for parent in target.parents:
        if parent.suffix == ".app":
            return parent
    return None


def macos_needs_portable_repair() -> bool:
    return sys.platform == "darwin" and is_frozen_app() and is_macos_app_translocated(current_executable())


def normalize_macos_portable_root(path: Path) -> Path:
    root = Path(path).expanduser().resolve()
    if root.suffix == ".app":
        root = root.parent
    marker = root / ".llm_extractor_portable"
    app_bundles = sorted(child for child in root.glob("*.app") if child.is_dir())
    if not marker.exists() or not app_bundles:
        raise UpdateError(
            "Seçilen klasör geçerli bir LLMExtractor klasörü değil. "
            "Zipten çıkan LLMExtractor-... üst klasörünü seçin."
        )
    return root


def macos_portable_app_bundle(root: Path) -> Path:
    portable_root = normalize_macos_portable_root(root)
    app_bundles = sorted(child for child in portable_root.glob("*.app") if child.is_dir())
    if not app_bundles:
        raise UpdateError("Seçilen klasörde LLMExtractor.app bulunamadı.")
    preferred = portable_root / "LLMExtractor.app"
    if preferred.exists():
        return preferred
    return app_bundles[0]


def remove_macos_quarantine(root: Path) -> None:
    portable_root = normalize_macos_portable_root(root)
    command = ["/usr/bin/xattr", "-dr", "com.apple.quarantine", str(portable_root)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise UpdateError(message or "macOS güvenlik hazırlığı tamamlanamadı.")


def repair_macos_portable_and_relaunch(root: Path) -> Path:
    portable_root = normalize_macos_portable_root(root)
    remove_macos_quarantine(portable_root)
    app_bundle = macos_portable_app_bundle(portable_root)
    subprocess.Popen(["/usr/bin/open", "-n", str(app_bundle)], close_fds=True)
    return app_bundle


def build_posix_apply_update_script(*, archive_path: Path, app_root: Path, executable: Path, parent_pid: int) -> str:
    archive = shlex.quote(str(archive_path))
    root = shlex.quote(str(app_root))
    exe = shlex.quote(str(executable))
    log = shlex.quote(str(archive_path.parent / "apply_update.log"))
    return textwrap.dedent(
        f"""
        #!/bin/sh
        set -eu
        ARCHIVE={archive}
        APP_ROOT={root}
        EXECUTABLE={exe}
        PARENT_PID={int(parent_pid)}
        LOG={log}

        exec >> "$LOG" 2>&1
        echo "Starting update apply at $(date)"
        echo "APP_ROOT=$APP_ROOT"
        echo "EXECUTABLE=$EXECUTABLE"
        echo "ARCHIVE=$ARCHIVE"

        i=0
        while kill -0 "$PARENT_PID" 2>/dev/null && [ "$i" -lt 120 ]; do
          sleep 0.5
          i=$((i + 1))
        done
        echo "Parent wait finished after $i iterations"

        EXTRACT_DIR="$(mktemp -d /tmp/llm_extractor_update.XXXXXX)"
        echo "Extracting to $EXTRACT_DIR"
        unzip -q "$ARCHIVE" -d "$EXTRACT_DIR"
        CHILDREN="$(find "$EXTRACT_DIR" -mindepth 1 -maxdepth 1 ! -name __MACOSX)"
        CHILD_COUNT="$(printf "%s\\n" "$CHILDREN" | sed '/^$/d' | wc -l | tr -d ' ')"
        if [ "$CHILD_COUNT" = "1" ]; then
          SOURCE_ROOT="$CHILDREN"
        else
          SOURCE_ROOT="$EXTRACT_DIR"
        fi
        echo "SOURCE_ROOT=$SOURCE_ROOT"

        PRESERVE_ROOT="$(mktemp -d /tmp/llm_extractor_preserve.XXXXXX)"
        if [ -d "$APP_ROOT/.llm_extractor_data" ]; then
          echo "Preserving portable data"
          mv "$APP_ROOT/.llm_extractor_data" "$PRESERVE_ROOT/.llm_extractor_data"
        fi

        BACKUP_ROOT="$APP_ROOT.old"
        rm -rf "$BACKUP_ROOT"
        if [ -e "$APP_ROOT" ]; then
          echo "Moving current app root to backup"
          mv "$APP_ROOT" "$BACKUP_ROOT"
        fi
        mkdir -p "$(dirname "$APP_ROOT")"
        echo "Installing update"
        mv "$SOURCE_ROOT" "$APP_ROOT"
        if [ -d "$PRESERVE_ROOT/.llm_extractor_data" ] && [ ! -d "$APP_ROOT/.llm_extractor_data" ]; then
          echo "Restoring portable data"
          mv "$PRESERVE_ROOT/.llm_extractor_data" "$APP_ROOT/.llm_extractor_data"
        fi
        rm -rf "$BACKUP_ROOT"

        APP_BUNDLE="$(find "$APP_ROOT" -maxdepth 1 -name '*.app' -type d | head -n 1)"
        NEW_EXECUTABLE=""
        if [ -n "$APP_BUNDLE" ] && [ -d "$APP_BUNDLE/Contents/MacOS" ]; then
          NEW_EXECUTABLE="$APP_BUNDLE/Contents/MacOS/LLMExtractor"
          if [ ! -x "$NEW_EXECUTABLE" ]; then
            NEW_EXECUTABLE="$(find "$APP_BUNDLE/Contents/MacOS" -maxdepth 1 -type f -perm -111 | head -n 1 || true)"
          fi
        fi
        if [ -n "$APP_BUNDLE" ] && command -v open >/dev/null 2>&1; then
          echo "Opening $APP_BUNDLE"
          if open -n "$APP_BUNDLE"; then
            echo "Relaunch requested with open"
            echo "Update apply finished at $(date)"
            exit 0
          else
            OPEN_STATUS=$?
            echo "open failed with status $OPEN_STATUS; trying executable fallback"
          fi
        fi
        if [ -n "$NEW_EXECUTABLE" ] && [ -x "$NEW_EXECUTABLE" ]; then
          echo "Opening executable fallback $NEW_EXECUTABLE"
          nohup "$NEW_EXECUTABLE" >/dev/null 2>&1 &
        elif [ -x "$EXECUTABLE" ]; then
          echo "Opening original executable fallback"
          nohup "$EXECUTABLE" >/dev/null 2>&1 &
        fi
        echo "Update apply finished at $(date)"
        """
    ).strip()


def build_windows_update_launcher_script(*, script_path: Path, app_root: Path) -> str:
    return textwrap.dedent(
        f"""
        @echo off
        setlocal
        set "APP_ROOT={str(app_root)}"
        set "PS_SCRIPT={str(script_path)}"
        set "DATA_DIR=%APP_ROOT%\\.llm_extractor_data"
        if not exist "%DATA_DIR%" mkdir "%DATA_DIR%" >nul 2>nul
        set "LOG=%DATA_DIR%\\apply_update_launcher.log"
        echo %DATE% %TIME% Starting Windows update launcher>> "%LOG%"
        echo APP_ROOT=%APP_ROOT%>> "%LOG%"
        echo PS_SCRIPT=%PS_SCRIPT%>> "%LOG%"
        set "PS_EXE=%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
        if not exist "%PS_EXE%" set "PS_EXE=powershell.exe"
        echo PS_EXE=%PS_EXE%>> "%LOG%"
        "%PS_EXE%" -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" >> "%LOG%" 2>&1
        set "EXIT_CODE=%ERRORLEVEL%"
        echo %DATE% %TIME% PowerShell exited with %EXIT_CODE%>> "%LOG%"
        exit /b %EXIT_CODE%
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
        $TempLog = Join-Path (Split-Path -Parent $Archive) "apply_update.log"
        $OldDataDir = Join-Path $AppRoot ".llm_extractor_data"
        $PersistentLog = Join-Path $OldDataDir "apply_update.log"
        $BackupRoot = "$AppRoot.old"
        $script:PersistentLoggingEnabled = $true

        function Ensure-LogTarget {{
            if (-not $script:PersistentLoggingEnabled) {{
                return
            }}
            if (-not (Test-Path -LiteralPath $AppRoot)) {{
                return
            }}
            if (-not (Test-Path -LiteralPath $OldDataDir)) {{
                New-Item -ItemType Directory -Path $OldDataDir -Force | Out-Null
            }}
        }}

        function Write-UpdateLog($Message) {{
            $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            $line = "$stamp $Message"
            Add-Content -LiteralPath $TempLog -Value $line
            try {{
                Ensure-LogTarget
                Add-Content -LiteralPath $PersistentLog -Value $line
            }} catch {{
            }}
        }}

        function Invoke-WithRetry($Description, [scriptblock]$Action, [int]$Attempts = 120) {{
            for ($i = 0; $i -lt $Attempts; $i++) {{
                try {{
                    & $Action
                    Write-UpdateLog "$Description succeeded"
                    return
                }} catch {{
                    Write-UpdateLog "$Description failed on attempt $($i + 1): $($_.Exception.Message)"
                    Start-Sleep -Milliseconds 500
                }}
            }}
            throw "$Description failed after $Attempts attempts"
        }}

        function Copy-DirectoryChildren($SourceDir, $DestinationDir) {{
            if (-not (Test-Path -LiteralPath $SourceDir)) {{
                return
            }}
            if (-not (Test-Path -LiteralPath $DestinationDir)) {{
                New-Item -ItemType Directory -Path $DestinationDir -Force | Out-Null
            }}
            $Items = Get-ChildItem -LiteralPath $SourceDir -Force
            foreach ($Item in $Items) {{
                $Destination = Join-Path $DestinationDir $Item.Name
                if (Test-Path -LiteralPath $Destination) {{
                    Write-UpdateLog "Removing existing copied backup child before retry: $Destination"
                    Remove-Item -LiteralPath $Destination -Recurse -Force
                }}
                Write-UpdateLog "Copying child $($Item.FullName) to $Destination"
                Copy-Item -LiteralPath $Item.FullName -Destination $Destination -Recurse -Force
            }}
        }}

        function Remove-AppRoot {{
            $script:PersistentLoggingEnabled = $false
            if (-not (Test-Path -LiteralPath $AppRoot)) {{
                return
            }}
            Remove-Item -LiteralPath $AppRoot -Recurse -Force
        }}

        function Restore-BackupIfPresent {{
            if (-not (Test-Path -LiteralPath $BackupRoot)) {{
                return
            }}
            if (Test-Path -LiteralPath $AppRoot) {{
                Remove-Item -LiteralPath $AppRoot -Recurse -Force
            }}
            Move-Item -LiteralPath $BackupRoot -Destination $AppRoot
            $script:PersistentLoggingEnabled = $true
            Write-UpdateLog "Restored backup after failed update"
        }}

        try {{
            Write-UpdateLog "Starting update apply"
            Write-UpdateLog "APP_ROOT=$AppRoot"
            Write-UpdateLog "EXECUTABLE=$Executable"
            Write-UpdateLog "ARCHIVE=$Archive"
            Write-UpdateLog "PERSISTENT_LOG=$PersistentLog"
            Set-Location -LiteralPath ([System.IO.Path]::GetTempPath())

            for ($i = 0; $i -lt 240; $i++) {{
                $process = Get-Process -Id $ParentPid -ErrorAction SilentlyContinue
                if ($null -eq $process) {{ break }}
                Start-Sleep -Milliseconds 500
            }}
            Write-UpdateLog "Parent wait finished"
            Start-Sleep -Milliseconds 1500

            $ExtractDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
            New-Item -ItemType Directory -Path $ExtractDir | Out-Null
            Write-UpdateLog "Extracting to $ExtractDir"
            Expand-Archive -LiteralPath $Archive -DestinationPath $ExtractDir -Force
            $Children = Get-ChildItem -LiteralPath $ExtractDir | Where-Object {{ $_.Name -ne "__MACOSX" }}
            if ($Children.Count -eq 1) {{
                $SourceRoot = $Children[0].FullName
            }} else {{
                $SourceRoot = $ExtractDir
            }}
            Write-UpdateLog "SOURCE_ROOT=$SourceRoot"

            $ParentRoot = Split-Path -Parent $AppRoot
            $PreserveRoot = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
            $PreservedDataDir = Join-Path $PreserveRoot ".llm_extractor_data"
            New-Item -ItemType Directory -Path $PreserveRoot | Out-Null
            if (Test-Path -LiteralPath $OldDataDir) {{
                Invoke-WithRetry "Preserve portable data" {{
                    Copy-Item -LiteralPath $OldDataDir -Destination $PreservedDataDir -Recurse -Force
                }}
            }}

            if (Test-Path -LiteralPath $BackupRoot) {{
                Invoke-WithRetry "Remove previous backup" {{
                    Remove-Item -LiteralPath $BackupRoot -Recurse -Force
                }}
            }}
            if (Test-Path -LiteralPath $AppRoot) {{
                Invoke-WithRetry "Copy current app root to backup" {{
                    Copy-DirectoryChildren $AppRoot $BackupRoot
                }}
                Invoke-WithRetry "Remove current app root" {{
                    Remove-AppRoot
                }}
            }}
            New-Item -ItemType Directory -Path $ParentRoot -Force | Out-Null
            Invoke-WithRetry "Install update into app root" {{
                Move-Item -LiteralPath $SourceRoot -Destination $AppRoot
            }}

            $NewDataDir = Join-Path $AppRoot ".llm_extractor_data"
            if (Test-Path -LiteralPath $PreservedDataDir) {{
                if (Test-Path -LiteralPath $NewDataDir) {{
                    Invoke-WithRetry "Remove packaged data dir" {{
                        Remove-Item -LiteralPath $NewDataDir -Recurse -Force
                    }}
                }}
                Invoke-WithRetry "Restore portable data" {{
                    Copy-Item -LiteralPath $PreservedDataDir -Destination $NewDataDir -Recurse -Force
                }}
            }}
            $OldDataDir = $NewDataDir
            $PersistentLog = Join-Path $OldDataDir "apply_update.log"
            $script:PersistentLoggingEnabled = $true
            Write-UpdateLog "Persistent log switched to $PersistentLog"

            $ExecutableName = Split-Path -Leaf $Executable
            $NewExecutable = Join-Path $AppRoot $ExecutableName
            if (-not (Test-Path -LiteralPath $NewExecutable)) {{
                $Candidate = Get-ChildItem -LiteralPath $AppRoot -Filter "*.exe" | Select-Object -First 1
                if ($null -ne $Candidate) {{
                    $NewExecutable = $Candidate.FullName
                }}
            }}
            if (Test-Path -LiteralPath $NewExecutable) {{
                Write-UpdateLog "Starting $NewExecutable"
                Start-Process -FilePath $NewExecutable -WorkingDirectory $AppRoot
            }} else {{
                Write-UpdateLog "New executable not found"
                throw "Updated executable not found."
            }}
            if (Test-Path -LiteralPath $BackupRoot) {{
                try {{
                    Remove-Item -LiteralPath $BackupRoot -Recurse -Force
                    Write-UpdateLog "Backup removed"
                }} catch {{
                    Write-UpdateLog "Backup removal skipped: $($_.Exception.Message)"
                }}
            }}
            Write-UpdateLog "Update apply finished"
        }} catch {{
            Write-UpdateLog "Update apply failed: $($_.Exception.Message)"
            try {{
                Restore-BackupIfPresent
            }} catch {{
                Write-UpdateLog "Backup restore failed: $($_.Exception.Message)"
            }}
            throw
        }}
        """
    ).strip()


def make_portable_marker(root: Path) -> None:
    (root / ".llm_extractor_portable").write_text("portable\n", encoding="utf-8")
