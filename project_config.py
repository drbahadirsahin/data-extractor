import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from helpers import ChoiceSpec, load_json

@dataclass
class ProjectConfig:
    project_name: str
    project_id: str = ""
    dictionary_path: str = ""
    form_labels: dict[str, str] = field(default_factory=dict)
    event_labels: dict[str, str] = field(default_factory=dict)
    form_event_map: dict[str, list[str]] = field(default_factory=dict)
    target_forms: list[str] | None = None
    target_fields: list[str] | None = None
    llm: dict[str, Any] = field(default_factory=dict)
    dictionary_legend: dict[str, str] = field(default_factory=dict)
    prompting: dict[str, Any] = field(default_factory=dict)
    batch_size: int = 15
    append_fields: list[dict[str, Any]] = field(default_factory=list)
    field_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    form_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    repeating_forms : list[str] | None = None
    repeating_events: list[str] | None = None
    debug_path: str | None = field(default=None, init=False)

    def __post_init__(self):
        self.llm = dict(self.llm)
        self.form_labels = dict(self.form_labels)
        self.event_labels = dict(self.event_labels)
        self.dictionary_legend = dict(self.dictionary_legend)
        self.prompting = dict(self.prompting)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("debug_path", None)
        return payload

def load_project_config(path: str) -> ProjectConfig:
    return ProjectConfig(**load_json(path))


def save_project_config(path: str | Path, config: ProjectConfig) -> None:
    Path(path).write_text(
        json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
