from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

from dictionary_parser import (
    FieldSpec,
    apply_overrides,
    apply_repeating_forms,
    get_extractable_fields,
    group_fields_by_form,
    load_data_dictionary,
    parse_field,
)
from helpers import load_json
from project_config import ProjectConfig, load_project_config, save_project_config
from redcap_client import RedcapClient


@dataclass
class WorkspaceBundle:
    config_path: Path
    config: ProjectConfig
    grouped_fields: dict[str, list[FieldSpec]]

    @property
    def form_names(self) -> list[str]:
        return list(self.grouped_fields.keys())

    def form_display_name(self, form_name: str) -> str:
        verbose = str(self.config.form_labels.get(form_name, "")).strip()
        if verbose and verbose != form_name:
            return f"{verbose} | {form_name}"
        return form_name

    @property
    def all_field_names(self) -> list[str]:
        field_names: list[str] = []
        seen: set[str] = set()
        for fields in self.grouped_fields.values():
            for field in fields:
                if field.field_name in seen:
                    continue
                seen.add(field.field_name)
                field_names.append(field.field_name)
        return field_names

    def field_names_for_form(self, form_name: str) -> list[str]:
        return [field.field_name for field in self.grouped_fields.get(form_name, [])]


def load_workspace_bundle(config_path: str | Path) -> WorkspaceBundle:
    resolved = Path(config_path).expanduser().resolve()
    config = load_project_config(str(resolved))
    config.dictionary_path = resolve_relative_to_config(resolved, config.dictionary_path)
    grouped_fields = load_workspace_dictionary(config)
    return WorkspaceBundle(
        config_path=resolved,
        config=config,
        grouped_fields=grouped_fields,
    )


def reload_workspace_bundle(bundle: WorkspaceBundle) -> WorkspaceBundle:
    return load_workspace_bundle(bundle.config_path)


def ensure_project_config(
    *,
    app_home: str | Path,
    project_id: str,
    project_name: str,
    api_url: str,
    api_token: str,
    default_llm_settings: dict[str, Any] | None = None,
    search_roots: list[str | Path] | None = None,
) -> Path:
    for root in search_roots or default_search_roots(app_home):
        match = find_project_config_by_project_id(project_id, Path(root))
        if match is not None:
            ensure_server_metadata_in_config(match, api_url=api_url, api_token=api_token)
            return match

    managed_dir = Path(app_home).expanduser().resolve() / "projects" / project_id
    managed_dir.mkdir(parents=True, exist_ok=True)
    dictionary_path = managed_dir / "dictionary.csv"
    config_path = managed_dir / f"project_config_{project_id}.json"

    metadata_csv = RedcapClient(api_url=api_url, api_token=api_token).export_metadata_csv()
    dictionary_path.write_text(metadata_csv, encoding="utf-8")
    client = RedcapClient(api_url=api_url, api_token=api_token)
    try:
        form_labels = client.export_instruments()
    except Exception:
        form_labels = {}
    try:
        repeating_forms = client.export_repeating_forms()
    except Exception:
        repeating_forms = []
    try:
        repeating_events = client.export_repeating_events()
    except Exception:
        repeating_events = []
    try:
        form_event_map = client.export_form_event_mapping()
    except Exception:
        form_event_map = {}

    blank_config = load_blank_project_config()
    blank_config["project_name"] = project_name
    blank_config["project_id"] = project_id
    blank_config["dictionary_path"] = dictionary_path.name
    if default_llm_settings:
        blank_config["llm"] = dict(default_llm_settings)
    blank_config["form_labels"] = dict(form_labels)
    blank_config["repeating_forms"] = list(repeating_forms)
    blank_config["repeating_events"] = list(repeating_events)
    blank_config["form_event_map"] = dict(form_event_map)
    blank_config["dictionary_legend"] = default_redcap_api_dictionary_legend()
    blank_config["append_fields"] = []
    blank_config["field_overrides"] = {}
    blank_config["form_overrides"] = {}
    blank_config["target_forms"] = []
    blank_config["target_fields"] = []
    config_path.write_text(
        json.dumps(blank_config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return config_path


def save_workspace_bundle(bundle: WorkspaceBundle) -> None:
    config = deepcopy(bundle.config)
    config.dictionary_path = make_path_relative_to_config(bundle.config_path, config.dictionary_path)
    save_project_config(bundle.config_path, config)


def load_workspace_dictionary(config: ProjectConfig) -> dict[str, list[FieldSpec]]:
    df = pd.read_csv(config.dictionary_path)
    missing_columns = [col for col in config.dictionary_legend.values() if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing columns in data dictionary: {missing_columns}")

    rename_map = {source_name: target_name for target_name, source_name in config.dictionary_legend.items()}
    df = df.rename(columns=rename_map)
    records = df.to_dict(orient="records")
    field_specs = [parse_field(config, record) for record in records]
    field_specs = apply_repeating_forms(config, field_specs)
    field_specs = apply_overrides(config, field_specs)
    field_specs = get_extractable_fields(field_specs)
    field_specs = filter_hidden_fields(field_specs)
    return group_fields_by_form(field_specs)


def resolve_relative_to_config(config_path: Path, target_path: str) -> str:
    target = Path(target_path)
    if target.is_absolute():
        return str(target)
    return str((config_path.parent / target).resolve())


def make_path_relative_to_config(config_path: Path, target_path: str) -> str:
    target = Path(target_path)
    if not target.is_absolute():
        return str(target)
    try:
        return str(target.relative_to(config_path.parent))
    except ValueError:
        return str(target)


def load_blank_project_config() -> dict[str, Any]:
    return load_json("project_config_blank.json")


def default_redcap_api_dictionary_legend() -> dict[str, str]:
    return {
        "field_name": "field_name",
        "form_name": "form_name",
        "section_header": "section_header",
        "field_type": "field_type",
        "field_label": "field_label",
        "choices": "select_choices_or_calculations",
        "field_note": "field_note",
        "text_validation": "text_validation_type_or_show_slider_number",
        "text_validation_min": "text_validation_min",
        "text_validation_max": "text_validation_max",
        "identifier": "identifier",
        "branching_logic": "branching_logic",
        "required": "required_field",
        "custom_alignment": "custom_alignment",
        "question_number": "question_number",
        "matrix_group_name": "matrix_group_name",
        "matrix_ranking": "matrix_ranking",
        "field_annotation": "field_annotation",
    }


def default_search_roots(app_home: str | Path) -> list[Path]:
    roots = [Path(app_home).expanduser().resolve() / "projects"]
    cwd = Path.cwd().resolve()
    if should_search_current_working_directory(cwd):
        roots.append(cwd)
    deduped: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if root in seen or not root.exists():
            continue
        seen.add(root)
        deduped.append(root)
    return deduped


def should_search_current_working_directory(cwd: Path) -> bool:
    if is_packaged_app():
        return False
    try:
        home = Path.home().resolve()
    except Exception:
        home = None
    if home is not None and cwd == home:
        return False
    if cwd == cwd.parent:
        return False
    return any((cwd / marker).exists() for marker in ("app_config.json", "project_config_blank.json", ".git"))


def is_packaged_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def find_project_config_by_project_id(project_id: str, root: Path) -> Path | None:
    if not root.exists():
        return None
    candidates = sorted(root.rglob("*.json"))
    for candidate in candidates:
        if candidate.name in {"app_config.json", "project_config_blank.json"}:
            continue
        payload = load_project_config_payload(candidate)
        if payload.get("project_id") != project_id:
            continue
        dictionary_path = payload.get("dictionary_path")
        if not isinstance(dictionary_path, str) or not dictionary_path.strip():
            continue
        if not is_workspace_config_compatible(candidate.resolve()):
            continue
        return candidate.resolve()
    return None


def load_project_config_payload(path: Path) -> dict[str, Any]:
    try:
        payload = load_json(path)
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def is_workspace_config_compatible(config_path: Path) -> bool:
    try:
        config = load_project_config(str(config_path))
    except Exception:
        return False
    try:
        config.dictionary_path = resolve_relative_to_config(config_path, config.dictionary_path)
        load_workspace_dictionary(config)
    except Exception:
        return False
    return True


def ensure_server_metadata_in_config(config_path: Path, *, api_url: str, api_token: str) -> None:
    try:
        config = load_project_config(str(config_path))
    except Exception:
        return
    needs_form_labels = not (
        config.form_labels and any(
        str(label).strip() and str(label).strip() != str(form_name).strip()
        for form_name, label in config.form_labels.items()
        )
    )
    needs_repeating_forms = not bool(config.repeating_forms)
    needs_repeating_events = not bool(config.repeating_events)
    needs_form_event_map = not bool(config.form_event_map)
    if not needs_form_labels and not needs_repeating_forms and not needs_repeating_events and not needs_form_event_map:
        return

    client = RedcapClient(api_url=api_url, api_token=api_token)
    changed = False

    if needs_form_labels:
        try:
            form_labels = client.export_instruments()
        except Exception:
            form_labels = {}
        if form_labels:
            config.form_labels = dict(form_labels)
            changed = True

    if needs_repeating_forms:
        try:
            repeating_forms = client.export_repeating_forms()
        except Exception:
            repeating_forms = []
        if repeating_forms:
            config.repeating_forms = list(repeating_forms)
            changed = True

    if needs_repeating_events:
        try:
            repeating_events = client.export_repeating_events()
        except Exception:
            repeating_events = []
        if repeating_events:
            config.repeating_events = list(repeating_events)
            changed = True

    if needs_form_event_map:
        try:
            form_event_map = client.export_form_event_mapping()
        except Exception:
            form_event_map = {}
        if form_event_map:
            config.form_event_map = dict(form_event_map)
            changed = True

    if not changed:
        return

    config.dictionary_path = resolve_relative_to_config(config_path, config.dictionary_path)
    save_workspace_bundle(
        WorkspaceBundle(
            config_path=config_path,
            config=config,
            grouped_fields={},
        )
    )


def filter_hidden_fields(fields_: list[FieldSpec]) -> list[FieldSpec]:
    visible_fields: list[FieldSpec] = []
    for field_ in fields_:
        annotations = [str(item).strip().lower() for item in (field_.field_annotation or [])]
        if any("@hidden" in item for item in annotations):
            continue
        visible_fields.append(field_)
    return visible_fields


def get_fields_for_forms(bundle: WorkspaceBundle, selected_forms: set[str] | None = None) -> list[FieldSpec]:
    form_names = selected_forms or set(bundle.form_names)
    fields: list[FieldSpec] = []
    for form_name in bundle.form_names:
        if form_name not in form_names:
            continue
        fields.extend(bundle.grouped_fields.get(form_name, []))
    return fields


def build_scoped_project_config(
    bundle: WorkspaceBundle,
    selected_forms: set[str],
    selected_fields: set[str],
) -> ProjectConfig:
    scoped = deepcopy(bundle.config)
    scoped.dictionary_path = str(bundle.config.dictionary_path)

    if selected_forms:
        scoped.target_forms = sorted(selected_forms)
    else:
        scoped.target_forms = []

    if selected_fields:
        scoped.target_fields = sorted(selected_fields)
    else:
        scoped.target_fields = []

    return scoped


def summarize_selection(
    bundle: WorkspaceBundle,
    selected_forms: set[str],
    selected_fields: set[str],
) -> tuple[int, int, int, int]:
    forms_count = len(selected_forms)
    fields_count = len(selected_fields)
    total_forms = len(bundle.form_names)
    total_fields = len(bundle.all_field_names)
    return forms_count, total_forms, fields_count, total_fields
