from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_entry_form_model import (
    CHECKBOX_EDITOR,
    DESCRIPTION_EDITOR,
    FormFieldModel,
    FormRenderModel,
)
from data_entry_store import DataEntryStore
from redcap_numeric import is_redcap_numeric_validation, normalize_redcap_numeric_text


@dataclass(frozen=True)
class DataEntryFieldChange:
    project_id: str
    record: str
    field_name: str
    old_value: str
    new_value: str
    event_id: str = ""
    repeat_instrument: str = ""
    instance: str = ""
    field_label: str = ""
    editor: str = ""


@dataclass(frozen=True)
class DataEntryChangeSet:
    project_id: str
    record: str
    changes: list[DataEntryFieldChange] = field(default_factory=list)
    unchanged_count: int = 0
    skipped_readonly_count: int = 0

    @property
    def has_changes(self) -> bool:
        return bool(self.changes)


@dataclass(frozen=True)
class AppliedDataEntryChanges:
    change_ids: list[int]
    change_set: DataEntryChangeSet

    @property
    def queued_count(self) -> int:
        return len(self.change_ids)


def build_form_change_set(
    model: FormRenderModel,
    submitted_values: dict[str, Any],
) -> DataEntryChangeSet:
    changes: list[DataEntryFieldChange] = []
    unchanged_count = 0
    skipped_readonly_count = 0
    for field in model.fields:
        if field.read_only or field.editor == DESCRIPTION_EDITOR:
            skipped_readonly_count += 1
            continue
        if field.editor == CHECKBOX_EDITOR:
            field_changes, field_unchanged = checkbox_field_changes(model, field, submitted_values)
            changes.extend(field_changes)
            unchanged_count += field_unchanged
            continue
        submitted_key = field_submission_key(field)
        if submitted_key not in submitted_values:
            continue
        old_value = normalize_field_scalar_value(field, field.value_text)
        new_value = normalize_field_scalar_value(field, submitted_values.get(submitted_key))
        if old_value == new_value:
            unchanged_count += 1
            continue
        changes.append(
            DataEntryFieldChange(
                project_id=model.project_id,
                record=model.record,
                field_name=field.field_name,
                old_value=old_value,
                new_value=new_value,
                event_id=field.event_id,
                repeat_instrument=field.repeat_instrument,
                instance=field.instance,
                field_label=field.label,
                editor=field.editor,
            )
        )
    return DataEntryChangeSet(
        project_id=model.project_id,
        record=model.record,
        changes=changes,
        unchanged_count=unchanged_count,
        skipped_readonly_count=skipped_readonly_count,
    )


def apply_form_changes(
    store: DataEntryStore,
    model: FormRenderModel,
    submitted_values: dict[str, Any],
    *,
    source: str = "manual_form",
) -> AppliedDataEntryChanges:
    change_set = build_form_change_set(model, submitted_values)
    change_ids: list[int] = []
    for change in change_set.changes:
        change_ids.append(
            store.queue_local_change(
                project_id=change.project_id,
                record=change.record,
                field_name=change.field_name,
                new_value=change.new_value,
                event_id=change.event_id,
                repeat_instrument=change.repeat_instrument,
                instance=change.instance,
                source=source,
                payload={
                    "old_value": change.old_value,
                    "field_label": change.field_label,
                    "editor": change.editor,
                },
            )
        )
    return AppliedDataEntryChanges(change_ids=change_ids, change_set=change_set)


def checkbox_field_changes(
    model: FormRenderModel,
    field: FormFieldModel,
    submitted_values: dict[str, Any],
) -> tuple[list[DataEntryFieldChange], int]:
    old_selected = set(field.value if isinstance(field.value, list) else [])
    changes: list[DataEntryFieldChange] = []
    unchanged_count = 0
    field_key = field_submission_key(field)
    for choice in field.choices:
        submitted_key = f"{field_key}___{choice.code}"
        if submitted_key not in submitted_values:
            continue
        old_value = "1" if choice.code in old_selected else "0"
        new_value = normalize_checkbox_submission(submitted_values.get(submitted_key))
        if old_value == new_value:
            unchanged_count += 1
            continue
        changes.append(
            DataEntryFieldChange(
                project_id=model.project_id,
                record=model.record,
                field_name=f"{field.field_name}___{choice.code}",
                old_value=old_value,
                new_value=new_value,
                event_id=field.event_id,
                repeat_instrument=field.repeat_instrument,
                instance=field.instance,
                field_label=f"{field.label}: {choice.label}",
                editor=field.editor,
            )
        )
    return changes, unchanged_count


def field_submission_key(field: FormFieldModel) -> str:
    return field.context_key or field.field_name


def normalize_scalar_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def normalize_field_scalar_value(field: FormFieldModel, value: Any) -> str:
    normalized = normalize_scalar_value(value)
    if is_redcap_numeric_validation(field.validation):
        return normalize_redcap_numeric_text(normalized, field.validation)
    return normalized


def normalize_checkbox_submission(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "y", "on", "checked"}:
        return "1"
    return "0"
