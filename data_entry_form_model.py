from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from data_entry_browser import RecordDetail, RecordFieldValue
from helpers import ChoiceSpec


TEXT_EDITOR = "text"
TEXT_AREA_EDITOR = "textarea"
DROPDOWN_EDITOR = "dropdown"
RADIO_EDITOR = "radio"
CHECKBOX_EDITOR = "checkbox"
READONLY_EDITOR = "readonly"
DESCRIPTION_EDITOR = "description"
DYNAMIC_DROPDOWN_EDITOR = "dynamic_dropdown"


@dataclass(frozen=True)
class FormChoiceModel:
    code: str
    label: str


@dataclass(frozen=True)
class FormFieldModel:
    field_name: str
    form_name: str
    label: str
    editor: str
    value: str | list[str] = ""
    field_type: str = ""
    choices: list[FormChoiceModel] = field(default_factory=list)
    note: str | None = None
    validation: str | None = None
    validation_min: str | None = None
    validation_max: str | None = None
    required: bool = False
    branching_logic: str | None = None
    read_only: bool = False
    present: bool = True
    dirty: bool = False
    event_id: str = ""
    instance: str = ""

    @property
    def value_text(self) -> str:
        if isinstance(self.value, list):
            return ", ".join(self.value)
        return str(self.value)


@dataclass(frozen=True)
class FormSectionModel:
    form_name: str
    title: str
    fields: list[FormFieldModel] = field(default_factory=list)


@dataclass(frozen=True)
class FormRenderModel:
    project_id: str
    record: str
    title: str
    dirty: bool = False
    conflict: bool = False
    sections: list[FormSectionModel] = field(default_factory=list)

    @property
    def fields(self) -> list[FormFieldModel]:
        return [field for section in self.sections for field in section.fields]


def build_form_render_model(
    detail: RecordDetail,
    field_specs_by_form: dict[str, list[Any]],
    *,
    form_labels: dict[str, str] | None = None,
    title: str | None = None,
) -> FormRenderModel:
    form_labels = form_labels or {}
    direct_values = direct_value_map(detail.field_values)
    checkbox_values = checkbox_value_map(detail.field_values)
    sections: list[FormSectionModel] = []
    for form_name, field_specs in field_specs_by_form.items():
        fields = [
            build_field_model(
                spec,
                direct_values=direct_values,
                checkbox_values=checkbox_values,
            )
            for spec in field_specs
        ]
        sections.append(
            FormSectionModel(
                form_name=form_name,
                title=form_labels.get(form_name) or form_name,
                fields=fields,
            )
        )
    return FormRenderModel(
        project_id=detail.project_id,
        record=detail.record,
        title=title or detail.record,
        dirty=detail.dirty,
        conflict=detail.conflict,
        sections=sections,
    )


def build_field_model(
    field_spec: Any,
    *,
    direct_values: dict[str, RecordFieldValue],
    checkbox_values: dict[str, set[str]],
) -> FormFieldModel:
    field_name = metadata_text(field_spec, "field_name")
    field_type = metadata_text(field_spec, "field_type").lower()
    form_name = metadata_text(field_spec, "form_name")
    choices = choices_for_field(field_spec, field_type=field_type)
    direct_value = direct_values.get(field_name)
    editor = editor_for_field(field_spec, field_type=field_type)
    read_only = editor in {READONLY_EDITOR, DESCRIPTION_EDITOR}
    if editor == CHECKBOX_EDITOR:
        value: str | list[str] = sorted(checkbox_values.get(field_name, set()))
        present = bool(value) or direct_value is not None
        dirty = bool(direct_value.dirty) if direct_value is not None else False
    elif editor == DESCRIPTION_EDITOR:
        value = metadata_text(field_spec, "field_label")
        present = True
        dirty = False
    else:
        value = direct_value.value if direct_value is not None else ""
        present = bool(direct_value.present) if direct_value is not None else False
        dirty = bool(direct_value.dirty) if direct_value is not None else False
    return FormFieldModel(
        field_name=field_name,
        form_name=form_name,
        label=metadata_text(field_spec, "field_label") or field_name,
        editor=editor,
        value=value,
        field_type=field_type,
        choices=choices,
        note=metadata_optional_text(field_spec, "field_note"),
        validation=metadata_optional_text(field_spec, "text_validation"),
        validation_min=metadata_optional_text(field_spec, "text_validation_min"),
        validation_max=metadata_optional_text(field_spec, "text_validation_max"),
        required=metadata_bool(field_spec, "required"),
        branching_logic=metadata_optional_text(field_spec, "branching_logic"),
        read_only=read_only,
        present=present,
        dirty=dirty,
        event_id=direct_value.event_id if direct_value is not None else "",
        instance=direct_value.instance if direct_value is not None else "",
    )


def direct_value_map(values: Iterable[RecordFieldValue]) -> dict[str, RecordFieldValue]:
    mapped: dict[str, RecordFieldValue] = {}
    for value in values:
        if "___" in value.field_name:
            continue
        mapped.setdefault(value.field_name, value)
    return mapped


def checkbox_value_map(values: Iterable[RecordFieldValue]) -> dict[str, set[str]]:
    mapped: dict[str, set[str]] = {}
    for value in values:
        if "___" not in value.field_name:
            continue
        field_name, code = value.field_name.rsplit("___", 1)
        if checkbox_value_is_selected(value.value):
            mapped.setdefault(field_name, set()).add(code)
    return mapped


def checkbox_value_is_selected(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized not in {"", "0", "false", "no", "hayir", "hay\u0131r"}


def choices_for_field(field_spec: Any, *, field_type: str) -> list[FormChoiceModel]:
    if field_type == "yesno":
        return [
            FormChoiceModel(code="1", label="Evet"),
            FormChoiceModel(code="0", label="Hayir"),
        ]
    if field_type == "truefalse":
        return [
            FormChoiceModel(code="1", label="True"),
            FormChoiceModel(code="0", label="False"),
        ]
    options = getattr(field_spec, "choices_options", None)
    if options is None and isinstance(field_spec, dict):
        options = field_spec.get("choices_options")
    if options:
        return [choice_model(option) for option in options]
    raw_choices = metadata_optional_text(field_spec, "choices")
    return [choice_model(option) for option in ChoiceSpecParser.parse(raw_choices)]


def choice_model(option: Any) -> FormChoiceModel:
    if isinstance(option, FormChoiceModel):
        return option
    if isinstance(option, ChoiceSpec):
        return FormChoiceModel(code=str(option.code), label=str(option.label))
    if isinstance(option, dict):
        return FormChoiceModel(
            code=str(option.get("code") or ""),
            label=str(option.get("label") or option.get("code") or ""),
        )
    return FormChoiceModel(code=str(option), label=str(option))


class ChoiceSpecParser:
    @staticmethod
    def parse(raw: str | None) -> list[ChoiceSpec]:
        if not raw:
            return []
        choices: list[ChoiceSpec] = []
        for part in str(raw).replace("\n", " ").split("|"):
            cleaned = part.strip()
            if not cleaned:
                continue
            if "," in cleaned:
                code, label = cleaned.split(",", 1)
                choices.append(ChoiceSpec(code=code.strip(), label=label.strip()))
            else:
                choices.append(ChoiceSpec(code=cleaned, label=cleaned))
        return choices


def editor_for_field(field_spec: Any, *, field_type: str) -> str:
    if field_type == "notes":
        return TEXT_AREA_EDITOR
    if field_type == "dropdown":
        return DROPDOWN_EDITOR
    if field_type in {"radio", "yesno", "truefalse"}:
        return RADIO_EDITOR
    if field_type == "checkbox":
        return CHECKBOX_EDITOR
    if field_type == "descriptive":
        return DESCRIPTION_EDITOR
    if field_type in {"calc", "file", "slider"}:
        return READONLY_EDITOR
    if field_type == "sql":
        return DYNAMIC_DROPDOWN_EDITOR
    return TEXT_EDITOR


def metadata_text(field_spec: Any, attribute: str) -> str:
    value = getattr(field_spec, attribute, None)
    if value in {None, ""} and isinstance(field_spec, dict):
        value = field_spec.get(attribute)
    if value in {None, ""}:
        return ""
    return str(value)


def metadata_optional_text(field_spec: Any, attribute: str) -> str | None:
    value = metadata_text(field_spec, attribute).strip()
    return value or None


def metadata_bool(field_spec: Any, attribute: str) -> bool:
    value = getattr(field_spec, attribute, None)
    if value in {None, ""} and isinstance(field_spec, dict):
        value = field_spec.get(attribute)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "required"}
