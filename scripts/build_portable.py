from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


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
        run_pyinstaller(args.name, staged_config, dist_dir)

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


def run_pyinstaller(name: str, staged_config: Path, dist_dir: Path) -> None:
    separator = ";" if os.name == "nt" else ":"
    add_data = [
        f"{staged_config}{separator}.",
        f"{ROOT / 'project_config_blank.json'}{separator}.",
        f"{ROOT / 'prostate_dictionary.csv'}{separator}.",
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
