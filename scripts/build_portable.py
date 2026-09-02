from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MACOS_BUNDLE_IDENTIFIER = "org.drbahadirsahin.dataextractor"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a portable LLM Extractor release package.")
    parser.add_argument("--name", default="LLMExtractor")
    parser.add_argument("--release-config", default="app_config.json")
    parser.add_argument("--dist-dir", default="dist")
    parser.add_argument("--skip-pyinstaller", action="store_true")
    args = parser.parse_args()

    release_config = (ROOT / args.release_config).resolve()
    if not release_config.exists():
        raise SystemExit(f"Release config not found: {release_config}")
    version = read_version(release_config)
    platform_key = build_platform_key()
    staging_dir = ROOT / "build" / "release_config"
    staging_dir.mkdir(parents=True, exist_ok=True)
    staged_config = staging_dir / "app_config.json"
    shutil.copy2(release_config, staged_config)

    dist_dir = (ROOT / args.dist_dir).resolve()
    if not args.skip_pyinstaller:
        ensure_pyinstaller_available()
        run_pyinstaller(args.name, staged_config, dist_dir, version)

    package_dir = dist_dir / f"{args.name}-{version}-{platform_key}"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True)

    artifact = find_pyinstaller_artifact(dist_dir, args.name)
    if artifact.is_dir():
        if artifact.suffix == ".app":
            shutil.copytree(artifact, package_dir / artifact.name)
        else:
            copy_directory_contents(artifact, package_dir)
    else:
        shutil.copy2(artifact, package_dir / artifact.name)
    (package_dir / ".llm_extractor_portable").write_text("portable\n", encoding="utf-8")
    copy_release_notes(package_dir, platform_key)

    archive_path = dist_dir / f"{package_dir.name}.zip"
    if archive_path.exists():
        archive_path.unlink()
    zip_directory(package_dir, archive_path)
    print(f"Built portable package: {archive_path}")
    print(f"SHA-256: {sha256_file(archive_path)}")
    return 0


def read_version(config_path: Path) -> str:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    release = payload.get("release", {}) if isinstance(payload, dict) else {}
    return str(release.get("version") or payload.get("version") or "0.1.0-early.1")


def build_platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "x64"
    if system == "darwin":
        return f"macos-{arch}"
    if system == "windows":
        return f"windows-{arch}"
    return f"{system}-{arch}"


def ensure_pyinstaller_available() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "PyInstaller is not installed. Install release dependencies with "
            "`python -m pip install -r requirements-release.txt`."
        ) from exc


def run_pyinstaller(name: str, staged_config: Path, dist_dir: Path, version: str) -> None:
    if sys.platform == "darwin":
        run_macos_pyinstaller(name, staged_config, dist_dir, version)
        return
    separator = ";" if os.name == "nt" else ":"
    add_data = [
        f"{staged_config}{separator}.",
        f"{ROOT / 'project_config_blank.json'}{separator}.",
        f"{ROOT / 'prostate_dictionary.csv'}{separator}.",
        f"{ROOT / 'gui' / 'assets'}{separator}gui/assets",
    ]
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        name,
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(ROOT / "build" / "pyinstaller"),
        "--specpath",
        str(ROOT / "build" / "pyinstaller"),
    ]
    for item in add_data:
        command.extend(["--add-data", item])
    command.append(str(ROOT / "main.py"))
    subprocess.run(command, cwd=ROOT, check=True)


def run_macos_pyinstaller(name: str, staged_config: Path, dist_dir: Path, version: str) -> None:
    spec_path = ROOT / "build" / "pyinstaller" / f"{name}.spec"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    datas = [
        (str(staged_config), "."),
        (str(ROOT / "project_config_blank.json"), "."),
        (str(ROOT / "prostate_dictionary.csv"), "."),
        (str(ROOT / "gui" / "assets"), "gui/assets"),
    ]
    info_plist = {
        "CFBundleDisplayName": "LLM Extractor",
        "CFBundleName": "LLM Extractor",
        "CFBundleVersion": macos_bundle_build_version(version),
        "NSPrincipalClass": "NSApplication",
        "LSApplicationCategoryType": "public.app-category.medical",
    }
    spec_path.write_text(
        build_macos_spec(
            name=name,
            entrypoint=ROOT / "main.py",
            datas=datas,
            version=macos_bundle_short_version(version),
            info_plist=info_plist,
        ),
        encoding="utf-8",
    )
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(ROOT / "build" / "pyinstaller"),
        str(spec_path),
    ]
    subprocess.run(command, cwd=ROOT, check=True)


def build_macos_spec(
    *,
    name: str,
    entrypoint: Path,
    datas: list[tuple[str, str]],
    version: str,
    info_plist: dict[str, str],
) -> str:
    return f"""# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    [{str(entrypoint)!r}],
    pathex=[],
    binaries=[],
    datas={datas!r},
    hiddenimports=[],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name={name!r},
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name={name!r},
)
app = BUNDLE(
    coll,
    name={f"{name}.app"!r},
    icon=None,
    bundle_identifier={MACOS_BUNDLE_IDENTIFIER!r},
    version={version!r},
    info_plist={info_plist!r},
)
"""


def macos_bundle_short_version(version: str) -> str:
    short_version = str(version).strip().lstrip("v").split("-", 1)[0].strip()
    return short_version or "0.0.0"


def macos_bundle_build_version(version: str) -> str:
    numbers = re.findall(r"\d+", str(version))
    if not numbers:
        return "0"
    return ".".join(str(int(number)) for number in numbers[:4])


def find_pyinstaller_artifact(dist_dir: Path, name: str) -> Path:
    candidates = [
        dist_dir / f"{name}.app",
        dist_dir / name,
        dist_dir / f"{name}.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SystemExit(f"PyInstaller artifact not found in {dist_dir}")


def copy_directory_contents(source: Path, destination: Path) -> None:
    for child in source.iterdir():
        target = destination / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)


def copy_release_notes(package_dir: Path, platform_key: str) -> None:
    if platform_key.startswith("macos-"):
        macos_readme = ROOT / "release" / "README_MACOS_TR.txt"
        if macos_readme.exists():
            shutil.copy2(macos_readme, package_dir / "ILK_OKU_MACOS.txt")


def zip_directory(source_dir: Path, archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in source_dir.rglob("*"):
            archive.write(path, path.relative_to(source_dir.parent))


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
