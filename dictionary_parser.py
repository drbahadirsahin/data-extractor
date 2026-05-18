from dataclasses import dataclass, field, fields
from helpers import ChoiceSpec, load_json
from project_config import ProjectConfig
import pandas as pd
from typing import Any

@dataclass
class FieldSpec:
    field_name: str
    form_name: str
    field_type: str
    field_label: str
    choices: str | None = None
    choices_options: list[ChoiceSpec] = field(default_factory=list, init=False)
    field_note: str | None = None
    text_validation: str | None = None
    text_validation_min: str | None = None
    text_validation_max: str | None = None
    field_annotation: list[str] = field(default_factory=list)
    prompt_append: str | None = field(default_factory=str, init=False)
    cardinality: str | None = field(default="single", init=False, metadata={"choices": ["single", "multiple"]})
    selection_rule: str | None = field(default="latest", init=False)
    max_candidates: int | None = field(default=3, init=False)
    post_processing: list[tuple[str, Any]] | None = field(default_factory=list, init=False)

    def to_prompt_dict(self) -> dict[str, str | None | list[str] | list[ChoiceSpec]]:
        return {
            "field_name": self.field_name,
            "form_name": self.form_name,
            "field_type": self.field_type,
            "field_label": self.field_label,
            "choices": self.choices,
            "choices_options": [{"code": c.code, "label": c.label} for c in self.choices_options],
            "field_note": self.field_note,
            "text_validation": self.text_validation,
            "text_validation_min": self.text_validation_min,
            "text_validation_max": self.text_validation_max,
            "field_annotation": self.field_annotation,
            "prompt_append": self.prompt_append,
            "cardinality": self.cardinality,
            "selection_rule": self.selection_rule,
            "max_candidates": self.max_candidates,
            "post_processing": self.post_processing,
        }

    @staticmethod
    def parse_choices(raw: str | None) -> list[ChoiceSpec]:
        if raw is None or pd.isna(raw):
            return []
        cleaned = str(raw).replace("\n", " ").strip()
        if not cleaned:
            return []
        parts = [part.strip() for part in cleaned.split("|") if part.strip()]
        choices: list[ChoiceSpec] = []
        for part in parts:
            if "," in part:
                code, label = part.split(",", 1)
                choices.append(ChoiceSpec(code=code.strip(), label=label.strip()))
            else:
                choices.append(ChoiceSpec(code=part.strip(), label=part.strip()))

        return choices

    def __post_init__(self):
        self.choices_options = self.parse_choices(self.choices)
        for attribute in ["field_name", "form_name", "field_type", "field_label"]:
            setattr(self, attribute, coerce_required_metadata_text(getattr(self, attribute)))
        for attribute in ["choices", "field_note", "text_validation", "text_validation_min", "text_validation_max"]:
            setattr(self, attribute, coerce_optional_metadata_text(getattr(self, attribute)))

        if self.field_annotation is None:
            self.field_annotation = []
        elif isinstance(self.field_annotation, str):
            self.field_annotation = [self.field_annotation]
        elif not isinstance(self.field_annotation, list) and is_missing_metadata_value(self.field_annotation):
            self.field_annotation = []
        elif isinstance(self.field_annotation, list):
            self.field_annotation = [
                str(item)
                for item in self.field_annotation
                if not is_missing_metadata_value(item)
            ]
        else:
            self.field_annotation = [str(self.field_annotation)]

def parse_form_fields(config: ProjectConfig, data_dict: pd.DataFrame) -> list[FieldSpec | None]:
    if not config.target_forms:
        return []
    field_specs = []
    form_fields = data_dict[
        data_dict.form_name.isin(config.target_forms)
    ].to_dict(orient="index")
    for field_name, field_data in form_fields.items():
        field_specs.append(parse_field(config, field_data))
    return field_specs


def parse_fieldset(config: ProjectConfig, fieldset_data: pd.DataFrame) -> list[FieldSpec]:
    source_field_name_column = config.dictionary_legend.get("field_name", "field_name")
    appended_field_names = {
        field_data.get(source_field_name_column)
        for field_data in config.append_fields
    }
    target_field_names = set(config.target_fields or []) | {name for name in appended_field_names if name}
    target_forms = config.target_forms or []

    if not target_field_names:
        return []
    field_specs = []
    fields = fieldset_data[
        fieldset_data.field_name.isin(target_field_names)
    ].to_dict(orient="index")
    for field_name, field_data in fields.items():
        if field_name in fieldset_data[fieldset_data.form_name.isin(target_forms)].field_name.tolist():
            continue
        field_specs.append(parse_field(config, field_data))
    return field_specs

def get_extractable_fields(fields_: list[FieldSpec]) -> list[FieldSpec]:
    app_settings = load_json("app_config.json")
    extractable_types = app_settings.get("extractable_types", [])
    extractable_fields = []
    for field_ in fields_:
        if field_.field_type in extractable_types:
            extractable_fields.append(field_)
    return extractable_fields


def filter_hidden_fields(fields_: list[FieldSpec]) -> list[FieldSpec]:
    visible_fields: list[FieldSpec] = []
    for field_ in fields_:
        annotations = [str(item).strip().lower() for item in (field_.field_annotation or [])]
        if any("@hidden" in item for item in annotations):
            continue
        visible_fields.append(field_)
    return visible_fields


def parse_field(config: ProjectConfig, field_data: dict[str, str | None]) -> FieldSpec:
    init_field_names = [f.name for f in fields(FieldSpec) if f.init]
    field_data = {k: field_data[k] for k in init_field_names}
    return FieldSpec(**field_data)


def coerce_required_metadata_text(value: Any) -> str:
    if is_missing_metadata_value(value):
        return ""
    return str(value)


def coerce_optional_metadata_text(value: Any) -> str | None:
    if is_missing_metadata_value(value):
        return None
    return str(value)


def is_missing_metadata_value(value: Any) -> bool:
    if value is None:
        return True
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    try:
        return bool(missing)
    except (TypeError, ValueError):
        return False

def apply_overrides(config: ProjectConfig, field_specs: list[FieldSpec]) -> list[FieldSpec]:
    if not config.form_overrides and not config.field_overrides:
        return field_specs

    overridden_specs = []
    for spec in field_specs:
        # Applies form-level overrides to matching spec attributes
        if spec.form_name in config.form_overrides:
            override = config.form_overrides[spec.form_name]
            for key, value in override.items():
                if hasattr(spec, key):
                    setattr(spec, key, value)

        if spec.field_name in config.field_overrides:
            override = config.field_overrides[spec.field_name]
            for key, value in override.items():
                if hasattr(spec, key):
                    setattr(spec, key, value)
        overridden_specs.append(spec)


    return overridden_specs

def group_fields_by_form(fields_: list[FieldSpec]) -> dict[str, list[FieldSpec]]:
    groups: dict[str, list[FieldSpec]] = {}
    for field_ in fields_:
        groups.setdefault(field_.form_name, []).append(field_)
    return groups

def apply_repeating_forms(config: ProjectConfig, field_specs: list[FieldSpec]) -> list[FieldSpec]:
    if not config.repeating_forms:
        return field_specs

    repeated_specs = []
    for spec in field_specs:
        if spec.form_name in config.repeating_forms:
            spec.cardinality = "multiple"
            spec.max_candidates = 10
            repeated_specs.append(spec)
        else:
            repeated_specs.append(spec)

    return repeated_specs

def load_data_dictionary(config: ProjectConfig) -> dict[str, list[FieldSpec]]:
    # load data dictionary, relative to project root
    df = pd.read_csv(config.dictionary_path)
    df = pd.concat([df, pd.DataFrame(config.append_fields)], ignore_index=True)

    # check if there are any missing columns
    missing_columns = [col for col in config.dictionary_legend.values() if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing columns in data dictionary: {missing_columns}")

    rename_map = {source_name: target_name for target_name, source_name in config.dictionary_legend.items()}
    df = df.rename(columns=rename_map)

    combined_data = parse_form_fields(config, df) + parse_fieldset(config, df)

    combined_data = apply_repeating_forms(config, combined_data)

    combined_data = apply_overrides(config, combined_data)

    combined_data = get_extractable_fields(combined_data)
    combined_data = filter_hidden_fields(combined_data)

    combined_data = group_fields_by_form(combined_data)

    return combined_data
