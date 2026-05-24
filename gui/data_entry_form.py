from __future__ import annotations

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
        self.model: FormRenderModel | None = None
        if model is not None:
            self.set_model(model)

    def set_model(self, model: FormRenderModel) -> None:
        from PySide6.QtWidgets import QLabel

        clear_layout(self.layout)
        self.editor_widgets = {}
        self.model = model

        header = QLabel(model.title)
        header.setObjectName("DataEntryRecordTitle")
        header.setWordWrap(True)
        self.layout.addWidget(header)
        for section in model.sections:
            self.layout.addWidget(self.build_section_widget(section), 0)
        self.layout.addStretch(1)

    def build_section_widget(self, section: Any) -> Any:
        from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

        frame = QFrame()
        frame.setObjectName("DataEntryFormSection")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        title = QLabel(section.title)
        title.setObjectName("SectionTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        for field in section.fields:
            layout.addWidget(self.build_field_row(field), 0)
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
        self.editor_widgets[field.field_name] = editor
        return editor

    def build_text_area(self, field: FormFieldModel) -> Any:
        from PySide6.QtWidgets import QPlainTextEdit

        editor = QPlainTextEdit(field.value_text)
        editor.setObjectName("DataEntryTextArea")
        editor.setProperty("field_name", field.field_name)
        editor.setMinimumHeight(96)
        editor.setReadOnly(field.read_only)
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

    def collect_values(self) -> dict[str, Any]:
        if self.model is None:
            return {}
        values: dict[str, Any] = {}
        for field in self.model.fields:
            widget = self.editor_widgets.get(field.field_name)
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


def clear_layout(layout: Any) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            clear_layout(child_layout)
