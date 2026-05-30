from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from data_entry_browser import RecordDetail, RecordFieldValue
from helpers import ChoiceSpec


TEXT_EDITOR = "text"
TEXT_AREA_EDITOR = "textarea"
DATE_EDITOR = "date"
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
    hidden: bool = False
    present: bool = True
    dirty: bool = False
    event_id: str = ""
    instance: str = ""
    context_key: str = ""

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
    event_id: str = ""
    event_label: str = ""
    instance: str = ""
    context_key: str = ""


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
    event_labels: dict[str, str] | None = None,
    form_event_map: dict[str, list[str]] | None = None,
    title: str | None = None,
) -> FormRenderModel:
    form_labels = form_labels or {}
    event_labels = event_labels or {}
    form_event_map = normalize_form_event_map(form_event_map)
    field_values = list(detail.field_values)
    contexts_by_form = form_contexts_by_form(field_values, field_specs_by_form, form_event_map)
    direct_values_by_context, checkbox_values_by_context = value_maps_by_context(field_values)
    sections: list[FormSectionModel] = []
    for form_name, event_id, instance in ordered_form_contexts(field_specs_by_form, contexts_by_form):
        field_specs = field_specs_by_form[form_name]
        context = context_key_tuple(event_id, instance)
        direct_values = direct_values_by_context.get(context, {})
        checkbox_values = checkbox_values_by_context.get(context, {})
        fields = [
            build_field_model(
                spec,
                direct_values=direct_values,
                checkbox_values=checkbox_values,
                event_id=event_id,
                instance=instance,
            )
            for spec in field_specs
        ]
        fields = [field for field in fields if not field.hidden]
        if not fields:
            continue
        sections.append(
            FormSectionModel(
                form_name=form_name,
                title=form_labels.get(form_name) or form_name,
                fields=fields,
                event_id=event_id,
                event_label=event_display_label(event_id, event_labels=event_labels, instance=instance),
                instance=instance,
                context_key=section_context_key(form_name, event_id, instance),
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
    event_id: str = "",
    instance: str = "",
) -> FormFieldModel:
    field_name = metadata_text(field_spec, "field_name")
    field_type = metadata_text(field_spec, "field_type").lower()
    form_name = metadata_text(field_spec, "form_name")
    choices = choices_for_field(field_spec, field_type=field_type)
    direct_value = direct_values.get(field_name)
    editor = editor_for_field(field_spec, field_type=field_type)
    validation = metadata_optional_text(field_spec, "text_validation")
    if editor == TEXT_EDITOR and is_date_validation(validation):
        editor = DATE_EDITOR
    annotations = metadata_annotations(field_spec)
    read_only = editor in {READONLY_EDITOR, DESCRIPTION_EDITOR} or annotation_has(annotations, "@READONLY")
    hidden = annotation_has(annotations, "@HIDDEN")
    field_event_id = direct_value.event_id if direct_value is not None else normalize_context_part(event_id)
    field_instance = direct_value.instance if direct_value is not None else normalize_context_part(instance)
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
        validation=validation,
        validation_min=metadata_optional_text(field_spec, "text_validation_min"),
        validation_max=metadata_optional_text(field_spec, "text_validation_max"),
        required=metadata_bool(field_spec, "required"),
        branching_logic=metadata_optional_text(field_spec, "branching_logic"),
        read_only=read_only,
        hidden=hidden,
        present=present,
        dirty=dirty,
        event_id=field_event_id,
        instance=field_instance,
        context_key=field_context_key(field_name, field_event_id, field_instance),
    )


def direct_value_map(
    values: Iterable[RecordFieldValue],
    *,
    event_id: str = "",
    instance: str = "",
) -> dict[str, RecordFieldValue]:
    mapped: dict[str, RecordFieldValue] = {}
    for value in values:
        if "___" in value.field_name:
            continue
        if not record_value_matches_context(value, event_id=event_id, instance=instance):
            continue
        existing = mapped.get(value.field_name)
        if existing is None or record_value_is_better(value, existing):
            mapped[value.field_name] = value
    return mapped


def record_value_is_better(candidate: RecordFieldValue, current: RecordFieldValue) -> bool:
    if candidate.dirty and not current.dirty:
        return True
    candidate_has_value = str(candidate.value or "") != ""
    current_has_value = str(current.value or "") != ""
    if candidate_has_value and not current_has_value:
        return True
    if candidate.present and not current.present:
        return True
    return False


def checkbox_value_map(
    values: Iterable[RecordFieldValue],
    *,
    event_id: str = "",
    instance: str = "",
) -> dict[str, set[str]]:
    mapped: dict[str, set[str]] = {}
    for value in values:
        if "___" not in value.field_name:
            continue
        if not record_value_matches_context(value, event_id=event_id, instance=instance):
            continue
        field_name, code = value.field_name.rsplit("___", 1)
        if checkbox_value_is_selected(value.value):
            mapped.setdefault(field_name, set()).add(code)
    return mapped


def checkbox_value_is_selected(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized not in {"", "0", "false", "no", "hayir", "hay\u0131r"}


def value_maps_by_context(
    values: Iterable[RecordFieldValue],
) -> tuple[dict[tuple[str, str], dict[str, RecordFieldValue]], dict[tuple[str, str], dict[str, set[str]]]]:
    direct_maps: dict[tuple[str, str], dict[str, RecordFieldValue]] = {}
    checkbox_maps: dict[tuple[str, str], dict[str, set[str]]] = {}
    for value in values:
        context = context_key_tuple(value.event_id, value.instance)
        if "___" in value.field_name:
            field_name, code = value.field_name.rsplit("___", 1)
            if checkbox_value_is_selected(value.value):
                checkbox_maps.setdefault(context, {}).setdefault(field_name, set()).add(code)
            continue
        mapped = direct_maps.setdefault(context, {})
        existing = mapped.get(value.field_name)
        if existing is None or record_value_is_better(value, existing):
            mapped[value.field_name] = value
    return direct_maps, checkbox_maps


def form_contexts_by_form(
    values: Iterable[RecordFieldValue],
    field_specs_by_form: dict[str, list[Any]],
    form_event_map: dict[str, list[str]],
) -> dict[str, list[tuple[str, str]]]:
    value_list = list(values)
    contexts: dict[str, list[tuple[str, str]]] = {}
    for form_name, field_specs in field_specs_by_form.items():
        field_names = {metadata_text(spec, "field_name") for spec in field_specs if metadata_text(spec, "field_name")}
        form_contexts: list[tuple[str, str]] = []
        for event_name in form_event_map.get(form_name, []):
            append_context(form_contexts, event_name, "")
        for value in value_list:
            if redcap_base_field_name(value.field_name) not in field_names:
                continue
            append_context(form_contexts, value.event_id, value.instance)
        if not form_contexts:
            form_contexts.append(("", ""))
        contexts[form_name] = form_contexts
    return contexts


def ordered_form_contexts(
    field_specs_by_form: dict[str, list[Any]],
    contexts_by_form: dict[str, list[tuple[str, str]]],
) -> list[tuple[str, str, str]]:
    has_event_context = any(
        event_id or instance
        for contexts in contexts_by_form.values()
        for event_id, instance in contexts
    )
    if not has_event_context:
        return [
            (form_name, event_id, instance)
            for form_name in field_specs_by_form
            for event_id, instance in contexts_by_form.get(form_name, [("", "")])
        ]
    ordered_contexts: list[tuple[str, str]] = []
    for form_name in field_specs_by_form:
        for event_id, instance in contexts_by_form.get(form_name, []):
            append_context(ordered_contexts, event_id, instance)
    ordered: list[tuple[str, str, str]] = []
    for event_id, instance in ordered_contexts:
        for form_name in field_specs_by_form:
            if (event_id, instance) in contexts_by_form.get(form_name, []):
                ordered.append((form_name, event_id, instance))
    return ordered


def append_context(contexts: list[tuple[str, str]], event_id: str | None, instance: str | None) -> None:
    context = (normalize_context_part(event_id), normalize_context_part(instance))
    if context not in contexts:
        contexts.append(context)


def record_value_matches_context(value: RecordFieldValue, *, event_id: str, instance: str) -> bool:
    return context_key_tuple(value.event_id, value.instance) == context_key_tuple(event_id, instance)


def context_key_tuple(event_id: Any, instance: Any) -> tuple[str, str]:
    return (normalize_context_part(event_id), normalize_context_part(instance))


def normalize_context_part(value: Any) -> str:
    return str(value or "").strip()


def redcap_base_field_name(field_name: str) -> str:
    text = str(field_name or "")
    if "___" in text:
        return text.rsplit("___", 1)[0]
    return text


def field_context_key(field_name: str, event_id: str = "", instance: str = "") -> str:
    event_key = normalize_context_part(event_id)
    instance_key = normalize_context_part(instance)
    if not event_key and not instance_key:
        return str(field_name)
    return f"{field_name}@@event={event_key}@@instance={instance_key}"


def section_context_key(form_name: str, event_id: str = "", instance: str = "") -> str:
    return field_context_key(form_name, event_id, instance)


def event_display_label(event_id: str, *, event_labels: dict[str, str], instance: str = "") -> str:
    context_parts: list[str] = []
    if event_id:
        context_parts.append(event_labels.get(event_id) or humanize_event_name(event_id))
    if instance:
        context_parts.append(f"Tekrar {instance}")
    return " / ".join(context_parts)


def humanize_event_name(event_id: str) -> str:
    text = str(event_id or "").strip()
    if not text:
        return ""
    text = text.replace("_arm_", " arm ")
    return text.replace("_", " ").strip().title()


def normalize_form_event_map(form_event_map: dict[str, list[str]] | None) -> dict[str, list[str]]:
    if not form_event_map:
        return {}
    normalized: dict[str, list[str]] = {}
    for form_name, events in form_event_map.items():
        if not form_name:
            continue
        bucket: list[str] = []
        for event_name in events or []:
            event_key = normalize_context_part(event_name)
            if event_key and event_key not in bucket:
                bucket.append(event_key)
        if bucket:
            normalized[str(form_name)] = bucket
    return normalized


def is_date_validation(validation: str | None) -> bool:
    return str(validation or "").strip().lower().startswith("date")


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


def metadata_annotations(field_spec: Any) -> list[str]:
    value = getattr(field_spec, "field_annotation", None)
    if value is None and isinstance(field_spec, dict):
        value = field_spec.get("field_annotation")
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).replace("\n", " ").split() if part.strip()]


def annotation_has(annotations: list[str], target: str) -> bool:
    target = target.upper()
    return any(str(item).upper() == target for item in annotations)
