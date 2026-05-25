from __future__ import annotations

import re
from typing import Any

from data_entry_form_model import (
    CHECKBOX_EDITOR,
    DESCRIPTION_EDITOR,
    DROPDOWN_EDITOR,
    DYNAMIC_DROPDOWN_EDITOR,
    RADIO_EDITOR,
    READONLY_EDITOR,
    TEXT_AREA_EDITOR,
    TEXT_EDITOR,
    FormFieldModel,
    FormRenderModel,
)


class DataEntryFormWidget:
    def __init__(self, model: FormRenderModel | None = None) -> None:
        from PySide6.QtWidgets import QVBoxLayout, QWidget

        self.widget = QWidget()
        self.widget.setObjectName("DataEntryForm")
        self.layout = QVBoxLayout(self.widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(14)
        self.editor_widgets: dict[str, Any] = {}
        self.field_rows: dict[str, Any] = {}
        self.model: FormRenderModel | None = None
        if model is not None:
            self.set_model(model)

    def set_model(self, model: FormRenderModel) -> None:
        from PySide6.QtWidgets import QLabel, QTabWidget

        clear_layout(self.layout)
        self.editor_widgets = {}
        self.field_rows = {}
        self.model = model

        header = QLabel(model.title)
        header.setObjectName("DataEntryRecordTitle")
        header.setWordWrap(True)
        self.layout.addWidget(header)
        if len(model.sections) > 1:
            tabs = QTabWidget()
            tabs.setObjectName("DataEntryFormTabs")
            for section in model.sections:
                tabs.addTab(self.build_section_widget(section, show_title=False), section.title)
            self.layout.addWidget(tabs, 1)
        else:
            for section in model.sections:
                self.layout.addWidget(self.build_section_widget(section), 0)
        self.layout.addStretch(1)
        self.update_branching_visibility()

    def build_section_widget(self, section: Any, *, show_title: bool = True) -> Any:
        from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

        frame = QFrame()
        frame.setObjectName("DataEntryFormSection")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        if show_title:
            title = QLabel(section.title)
            title.setObjectName("SectionTitle")
            title.setWordWrap(True)
            layout.addWidget(title)
        for field in section.fields:
            layout.addWidget(self.build_field_row(field), 0)
        layout.addStretch(1)
        return frame

    def build_field_row(self, field: FormFieldModel) -> Any:
        from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

        row = QFrame()
        row.setObjectName("DataEntryFieldRow")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        label_text = field.label
        if field.required:
            label_text = f"{label_text} *"
        label = QLabel(label_text)
        label.setObjectName("DataEntryFieldLabel")
        label.setWordWrap(True)
        layout.addWidget(label)
        if field.note:
            note = QLabel(field.note)
            note.setObjectName("DataEntryFieldNote")
            note.setWordWrap(True)
            layout.addWidget(note)
        editor = self.build_editor(field)
        layout.addWidget(editor)
        if field.branching_logic:
            branching = QLabel(field.branching_logic)
            branching.setObjectName("DataEntryBranchingLogic")
            branching.setWordWrap(True)
            layout.addWidget(branching)
        self.field_rows[field.field_name] = row
        return row

    def build_editor(self, field: FormFieldModel) -> Any:
        if field.editor == TEXT_AREA_EDITOR:
            return self.build_text_area(field)
        if field.editor in {DROPDOWN_EDITOR, DYNAMIC_DROPDOWN_EDITOR}:
            return self.build_combo(field)
        if field.editor == RADIO_EDITOR:
            return self.build_radio_group(field)
        if field.editor == CHECKBOX_EDITOR:
            return self.build_checkbox_group(field)
        if field.editor in {READONLY_EDITOR, DESCRIPTION_EDITOR}:
            return self.build_readonly(field)
        return self.build_line_edit(field)

    def build_line_edit(self, field: FormFieldModel) -> Any:
        from PySide6.QtWidgets import QLineEdit

        editor = QLineEdit(field.value_text)
        editor.setObjectName("DataEntryLineEdit")
        editor.setProperty("field_name", field.field_name)
        editor.setReadOnly(field.read_only)
        configure_line_edit_validation(editor, field)
        editor.textChanged.connect(lambda _text=None: self.update_branching_visibility())
        self.editor_widgets[field.field_name] = editor
        return editor

    def build_text_area(self, field: FormFieldModel) -> Any:
        from PySide6.QtWidgets import QPlainTextEdit

        editor = QPlainTextEdit(field.value_text)
        editor.setObjectName("DataEntryTextArea")
        editor.setProperty("field_name", field.field_name)
        editor.setMinimumHeight(96)
        editor.setReadOnly(field.read_only)
        editor.textChanged.connect(self.update_branching_visibility)
        self.editor_widgets[field.field_name] = editor
        return editor

    def build_combo(self, field: FormFieldModel) -> Any:
        from PySide6.QtWidgets import QComboBox

        editor = QComboBox()
        editor.setObjectName("DataEntryCombo")
        editor.setProperty("field_name", field.field_name)
        editor.addItem("", "")
        for choice in field.choices:
            editor.addItem(choice.label, choice.code)
        index = editor.findData(field.value_text)
        if index >= 0:
            editor.setCurrentIndex(index)
        editor.setEnabled(not field.read_only)
        editor.currentIndexChanged.connect(lambda _index=None: self.update_branching_visibility())
        self.editor_widgets[field.field_name] = editor
        return editor

    def build_radio_group(self, field: FormFieldModel) -> Any:
        from PySide6.QtWidgets import QButtonGroup, QFrame, QRadioButton, QVBoxLayout

        frame = QFrame()
        frame.setObjectName("DataEntryChoiceGroup")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        group = QButtonGroup(frame)
        group.setExclusive(True)
        for choice in field.choices:
            button = QRadioButton(choice.label)
            button.setProperty("choice_code", choice.code)
            button.setChecked(choice.code == field.value_text)
            button.setEnabled(not field.read_only)
            button.toggled.connect(lambda _checked=False: self.update_branching_visibility())
            group.addButton(button)
            layout.addWidget(button)
        frame._data_entry_button_group = group
        self.editor_widgets[field.field_name] = group
        return frame

    def build_checkbox_group(self, field: FormFieldModel) -> Any:
        from PySide6.QtWidgets import QCheckBox, QFrame, QVBoxLayout

        selected = set(field.value if isinstance(field.value, list) else [])
        frame = QFrame()
        frame.setObjectName("DataEntryChoiceGroup")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        boxes = []
        for choice in field.choices:
            checkbox = QCheckBox(choice.label)
            checkbox.setProperty("choice_code", choice.code)
            checkbox.setChecked(choice.code in selected)
            checkbox.setEnabled(not field.read_only)
            checkbox.toggled.connect(lambda _checked=False: self.update_branching_visibility())
            boxes.append(checkbox)
            layout.addWidget(checkbox)
        self.editor_widgets[field.field_name] = boxes
        return frame

    def build_readonly(self, field: FormFieldModel) -> Any:
        from PySide6.QtWidgets import QLabel

        value = field.value_text or "-"
        label = QLabel(value)
        label.setObjectName("DataEntryReadonlyValue")
        label.setWordWrap(True)
        self.editor_widgets[field.field_name] = label
        return label

    def collect_values(self, *, include_hidden: bool = False) -> dict[str, Any]:
        if self.model is None:
            return {}
        values: dict[str, Any] = {}
        for field in self.model.fields:
            widget = self.editor_widgets.get(field.field_name)
            row = self.field_rows.get(field.field_name)
            if not include_hidden and row is not None and row.isHidden():
                continue
            if widget is None or field.read_only or field.editor == DESCRIPTION_EDITOR:
                continue
            if field.editor == TEXT_AREA_EDITOR:
                values[field.field_name] = widget.toPlainText()
            elif field.editor == TEXT_EDITOR:
                values[field.field_name] = widget.text()
            elif field.editor in {DROPDOWN_EDITOR, DYNAMIC_DROPDOWN_EDITOR}:
                values[field.field_name] = widget.currentData()
            elif field.editor == RADIO_EDITOR:
                checked = widget.checkedButton()
                values[field.field_name] = checked.property("choice_code") if checked is not None else ""
            elif field.editor == CHECKBOX_EDITOR:
                for checkbox in widget:
                    choice_code = checkbox.property("choice_code")
                    values[f"{field.field_name}___{choice_code}"] = "1" if checkbox.isChecked() else "0"
        return values

    def collect_change_set(self):
        from data_entry_form_changes import build_form_change_set

        if self.model is None:
            return None
        return build_form_change_set(self.model, self.collect_values())

    def update_branching_visibility(self) -> None:
        if self.model is None:
            return
        values = self.collect_values(include_hidden=True)
        for field in self.model.fields:
            row = self.field_rows.get(field.field_name)
            if row is None or not field.branching_logic:
                continue
            row.setVisible(evaluate_branching_logic(field.branching_logic, values))


def clear_layout(layout: Any) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            clear_layout(child_layout)


def configure_line_edit_validation(editor: Any, field: FormFieldModel) -> None:
    from PySide6.QtGui import QDoubleValidator, QIntValidator

    validation = str(field.validation or "").strip().lower()
    if validation == "integer":
        validator = QIntValidator(editor)
        if field.validation_min not in {None, ""}:
            validator.setBottom(int(float(str(field.validation_min))))
        if field.validation_max not in {None, ""}:
            validator.setTop(int(float(str(field.validation_max))))
        editor.setValidator(validator)
        return
    if validation in {"number", "float"}:
        validator = QDoubleValidator(editor)
        if field.validation_min not in {None, ""}:
            validator.setBottom(float(str(field.validation_min)))
        if field.validation_max not in {None, ""}:
            validator.setTop(float(str(field.validation_max)))
        editor.setValidator(validator)
        return
    if validation.startswith("date"):
        editor.setPlaceholderText("YYYY-MM-DD")


def evaluate_branching_logic(logic: str, values: dict[str, Any]) -> bool:
    text = str(logic or "").strip()
    if not text:
        return True
    or_parts = re.split(r"\s+(?:or|OR)\s+", text)
    return any(evaluate_branching_and_group(part, values) for part in or_parts if part.strip())


def evaluate_branching_and_group(text: str, values: dict[str, Any]) -> bool:
    parts = re.split(r"\s+(?:and|AND)\s+", text)
    results = [evaluate_branching_clause(part, values) for part in parts if part.strip()]
    return all(results) if results else True


def evaluate_branching_clause(clause: str, values: dict[str, Any]) -> bool:
    cleaned = clause.strip().strip("() ")
    match = re.fullmatch(
        r"\[([A-Za-z0-9_]+)(?:\(([^)]+)\))?\]\s*(=|<>|!=|>=|<=|>|<)\s*(?:'([^']*)'|\"([^\"]*)\"|([^\s]+))",
        cleaned,
    )
    if not match:
        return True
    field_name, checkbox_code, operator, quoted_single, quoted_double, bare_value = match.groups()
    expected = quoted_single if quoted_single is not None else quoted_double if quoted_double is not None else bare_value
    key = f"{field_name}___{checkbox_code}" if checkbox_code else field_name
    actual = values.get(key, "")
    return compare_branching_values(str(actual or ""), operator, str(expected or ""))


def compare_branching_values(actual: str, operator: str, expected: str) -> bool:
    if operator in {"=", "=="}:
        return actual == expected
    if operator in {"<>", "!="}:
        return actual != expected
    actual_number = parse_float(actual)
    expected_number = parse_float(expected)
    if actual_number is None or expected_number is None:
        return True
    if operator == ">":
        return actual_number > expected_number
    if operator == ">=":
        return actual_number >= expected_number
    if operator == "<":
        return actual_number < expected_number
    if operator == "<=":
        return actual_number <= expected_number
    return True


def parse_float(value: str) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None
