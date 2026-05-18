from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import hashlib

ROOT = Path(__file__).resolve().parents[1]
PLATFORM_PATTERN = re.compile(r"LLMExtractor-(?P<version>.+)-(?P<platform>(?:macos|windows|linux)-[A-Za-z0-9_]+)\.zip$")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an update manifest from portable release archives.")
    parser.add_argument("--dist-dir", default="dist")
    parser.add_argument("--base-url", required=True, help="Release asset base URL without trailing slash.")
    parser.add_argument("--output", default="dist/update_manifest.json")
    parser.add_argument("--notes", default="Early release.")
    args = parser.parse_args()

    dist_dir = (ROOT / args.dist_dir).resolve()
    archives = sorted(dist_dir.glob("LLMExtractor-*.zip"))
    if not archives:
        raise SystemExit(f"No portable archives found in {dist_dir}")

    version = None
    platforms: dict[str, dict[str, str]] = {}
    for archive in archives:
        match = PLATFORM_PATTERN.match(archive.name)
        if not match:
            continue
        archive_version = match.group("version")
        platform_key = match.group("platform")
        if version is None:
            version = archive_version
        elif version != archive_version:
            raise SystemExit(f"Mixed release versions found: {version} and {archive_version}")
        platforms[platform_key] = {
            "url": f"{args.base_url.rstrip('/')}/{archive.name}",
            "sha256": sha256_file(archive),
        }

    if not platforms or version is None:
        raise SystemExit(f"No recognized LLMExtractor release archives found in {dist_dir}")

    payload = {
        "version": version,
        "notes": args.notes,
        "platforms": platforms,
    }
    output_path = (ROOT / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote update manifest: {output_path}")
    return 0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
