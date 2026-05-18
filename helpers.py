import json
import sys
from pathlib import Path
from typing import Any
from dataclasses import dataclass

@dataclass
class ChoiceSpec:
    code: str
    label: str

def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve_resource_path(path).read_text(encoding="utf-8"))

def load_text(path: str | Path) -> str:
    p = resolve_resource_path(path)
    encodings_to_try = [
        "utf-8",
        "utf-8-sig",
        "cp1254",
        "iso-8859-9",
        "latin-1",
        "utf-16",
        "utf-16le",
        "utf-16be",
    ]
    for enc in encodings_to_try:
        try:
            text = p.read_text(encoding=enc)
            return text.replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeDecodeError:
            continue
    text = p.read_text(encoding="latin-1", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def resolve_resource_path(path: str | Path) -> Path:
    requested = Path(path)
    if requested.is_absolute():
        return requested
    candidates: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / requested)
    executable = Path(sys.executable).resolve()
    candidates.append(executable.parent / requested)
    candidates.append(Path.cwd() / requested)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]
