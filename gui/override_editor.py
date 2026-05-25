from __future__ import annotations

from typing import Any

from gui.i18n import tr


def edit_override_payload(
    *,
    parent: Any,
    title: str,
    subject_label: str,
    payload: dict[str, Any] | None,
    language: str,
) -> dict[str, Any] | None:
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QLabel,
        QPlainTextEdit,
        QSpinBox,
        QVBoxLayout,
    )

    current_payload = dict(payload or {})
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setMinimumWidth(560)
    layout = QVBoxLayout(dialog)
    layout.setSpacing(12)

    info = QLabel(tr("override_editor_desc", language, name=subject_label))
    info.setWordWrap(True)
    layout.addWidget(info)

    form = QFormLayout()
    form.setSpacing(10)

    prompt_append_input = QPlainTextEdit()
    prompt_append_input.setPlainText(str(current_payload.get("prompt_append", "") or ""))
    prompt_append_input.setMinimumHeight(96)

    cardinality_input = QComboBox()
    cardinality_input.addItem(tr("override_use_default", language), "")
    cardinality_input.addItem("single", "single")
    cardinality_input.addItem("multiple", "multiple")
    cardinality_input.addItem("repeat_entity", "repeat_entity")
    set_combo_value(cardinality_input, str(current_payload.get("cardinality", "") or ""))

    selection_rule_input = QComboBox()
    selection_rule_input.addItem(tr("override_use_default", language), "")
    for value in ["latest", "earliest", "highest", "lowest", "all", "manual_review"]:
        selection_rule_input.addItem(value, value)
    set_combo_value(selection_rule_input, str(current_payload.get("selection_rule", "") or ""))

    max_candidates_enabled = QCheckBox(tr("override_enable_max_candidates", language))
    max_candidates_input = QSpinBox()
    max_candidates_input.setRange(1, 50)
    max_candidates_value = current_payload.get("max_candidates")
    max_candidates_enabled.setChecked(max_candidates_value is not None)
    max_candidates_input.setValue(int(max_candidates_value or 3))
    max_candidates_input.setEnabled(max_candidates_enabled.isChecked())

    post_processing = current_payload.get("post_processing") or []
    limit_length_value = extract_limit_output_length(post_processing)
    limit_length_enabled = QCheckBox(tr("override_limit_output_length", language))
    limit_length_enabled.setChecked(limit_length_value is not None)
    limit_length_input = QSpinBox()
    limit_length_input.setRange(1, 5000)
    limit_length_input.setValue(int(limit_length_value or 100))
    limit_length_input.setEnabled(limit_length_enabled.isChecked())

    form.addRow(tr("override_prompt_append", language), prompt_append_input)
    form.addRow(tr("override_cardinality", language), cardinality_input)
    form.addRow(tr("override_selection_rule", language), selection_rule_input)
    form.addRow("", max_candidates_enabled)
    form.addRow(tr("override_max_candidates", language), max_candidates_input)
    form.addRow("", limit_length_enabled)
    form.addRow(tr("override_limit_length_value", language), limit_length_input)
    layout.addLayout(form)

    max_candidates_enabled.toggled.connect(max_candidates_input.setEnabled)
    limit_length_enabled.toggled.connect(limit_length_input.setEnabled)

    button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
    if ok_button is not None:
        ok_button.setText(tr("ok_button", language))
        ok_button.setAutoDefault(False)
        ok_button.setDefault(False)
    cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
    if cancel_button is not None:
        cancel_button.setText(tr("cancel_button", language))
    button_box.rejected.connect(dialog.reject)
    layout.addWidget(button_box)

    result_payload: dict[str, Any] | None = None

    def validate_and_accept() -> None:
        nonlocal result_payload
        result: dict[str, Any] = {}
        prompt_append = prompt_append_input.toPlainText().strip()
        if prompt_append:
            result["prompt_append"] = prompt_append

        cardinality = str(cardinality_input.currentData() or "").strip()
        if cardinality:
            result["cardinality"] = cardinality

        selection_rule = str(selection_rule_input.currentData() or "").strip()
        if selection_rule:
            result["selection_rule"] = selection_rule

        if max_candidates_enabled.isChecked():
            result["max_candidates"] = int(max_candidates_input.value())

        post_processing_items = merge_post_processing(
            existing=post_processing,
            limit_output_length=int(limit_length_input.value()) if limit_length_enabled.isChecked() else None,
        )
        if post_processing_items:
            result["post_processing"] = post_processing_items

        result_payload = result
        dialog.accept()

    button_box.accepted.connect(validate_and_accept)

    if dialog.exec() == 0:
        return None
    return result_payload


def override_summary(payload: dict[str, Any] | None, *, language: str) -> str:
    if not payload:
        return tr("override_summary_empty", language)
    parts: list[str] = []
    if str(payload.get("prompt_append") or "").strip():
        parts.append(tr("override_prompt_append", language))
    for key, label_key in [
        ("cardinality", "override_cardinality"),
        ("selection_rule", "override_selection_rule"),
        ("max_candidates", "override_max_candidates"),
    ]:
        value = payload.get(key)
        if value not in {None, ""}:
            parts.append(f"{tr(label_key, language)}: {value}")
    limit_output_length = extract_limit_output_length(payload.get("post_processing") or [])
    if limit_output_length is not None:
        parts.append(f"{tr('override_limit_length_value', language)}: {limit_output_length}")
    return " · ".join(parts) if parts else tr("override_summary_empty", language)


def extract_limit_output_length(post_processing: list[Any] | None) -> int | None:
    for item in post_processing or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2 and item[0] == "limit_output_length":
            try:
                return int(item[1])
            except (TypeError, ValueError):
                return None
    return None


def merge_post_processing(*, existing: list[Any] | None, limit_output_length: int | None) -> list[Any]:
    merged: list[Any] = []
    for item in existing or []:
        if isinstance(item, (list, tuple)) and item and item[0] == "limit_output_length":
            continue
        merged.append(item)
    if limit_output_length is not None:
        merged.append(["limit_output_length", int(limit_output_length)])
    return merged


def set_combo_value(combo: Any, target_value: str) -> None:
    index = combo.findData(target_value)
    if index >= 0:
        combo.setCurrentIndex(index)
