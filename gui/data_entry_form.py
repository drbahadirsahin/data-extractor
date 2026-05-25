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
        self.form_nav: Any | None = None
        self.form_selector: Any | None = None
        self.form_stack: Any | None = None
        self.model: FormRenderModel | None = None
        if model is not None:
            self.set_model(model)

    def set_model(self, model: FormRenderModel) -> None:
        from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout

        clear_layout(self.layout)
        self.editor_widgets = {}
        self.field_rows = {}
        self.form_nav = None
        self.form_selector = None
        self.form_stack = None
        self.model = model

        header = QLabel(model.title)
        header.setObjectName("DataEntryRecordTitle")
        header.setWordWrap(True)
        self.layout.addWidget(header)
        if len(model.sections) > 1:
            shell = QFrame()
            shell.setObjectName("DataEntryFormShell")
            shell_layout = QVBoxLayout(shell)
            shell_layout.setContentsMargins(0, 0, 0, 0)
            shell_layout.setSpacing(10)

            selector_bar = QFrame()
            selector_bar.setObjectName("DataEntryFormSelectorBar")
            selector_layout = QHBoxLayout(selector_bar)
            selector_layout.setContentsMargins(12, 10, 12, 10)
            selector_layout.setSpacing(10)
            selector_label = QLabel("Form")
            selector_label.setObjectName("DataEntrySelectorLabel")
            form_selector = QComboBox()
            form_selector.setObjectName("DataEntryFormSelector")
            form_selector.setMinimumWidth(360)
            form_selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            form_stack = QStackedWidget()
            form_stack.setObjectName("DataEntryFormStack")
            for section in model.sections:
                form_selector.addItem(section.title)
                form_stack.addWidget(self.build_section_page(section, show_title=True))
            form_selector.currentIndexChanged.connect(form_stack.setCurrentIndex)
            form_selector.setCurrentIndex(0)
            self.form_selector = form_selector
            self.form_stack = form_stack
            selector_layout.addWidget(selector_label, 0)
            selector_layout.addWidget(form_selector, 1)
            shell_layout.addWidget(selector_bar, 0)
            shell_layout.addWidget(form_stack, 0)
            self.layout.addWidget(shell, 0)
        else:
            for section in model.sections:
                self.layout.addWidget(self.build_section_widget(section), 0)
        self.update_branching_visibility()

    def build_section_page(self, section: Any, *, show_title: bool = True) -> Any:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QVBoxLayout, QWidget

        page = QWidget()
        page.setObjectName("DataEntryFormPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.build_section_widget(section, show_title=show_title), 0, Qt.AlignmentFlag.AlignTop)
        layout.addStretch(1)
        return page

    def build_section_widget(self, section: Any, *, show_title: bool = True) -> Any:
        from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QLayout, QSizePolicy, QVBoxLayout

        frame = QFrame()
        frame.setObjectName("DataEntryFormSection")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        if show_title:
            title = QLabel(section.title)
            title.setObjectName("SectionTitle")
            title.setWordWrap(True)
            layout.addWidget(title)
        field_grid = QGridLayout()
        field_grid.setContentsMargins(0, 0, 0, 0)
        field_grid.setHorizontalSpacing(14)
        field_grid.setVerticalSpacing(10)
        field_grid.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        row_index = 0
        column_index = 0
        for field in section.fields:
            row_widget = self.build_field_row(field)
            if field_uses_full_width(field):
                if column_index != 0:
                    row_index += 1
                    column_index = 0
                field_grid.addWidget(row_widget, row_index, 0, 1, 2)
                row_index += 1
                column_index = 0
                continue
            field_grid.addWidget(row_widget, row_index, column_index)
            column_index += 1
            if column_index >= 2:
                row_index += 1
                column_index = 0
        field_grid.setColumnStretch(0, 1)
        field_grid.setColumnStretch(1, 1)
        layout.addLayout(field_grid)
        return frame

    def build_field_row(self, field: FormFieldModel) -> Any:
        from PySide6.QtWidgets import QFrame, QLabel, QLayout, QSizePolicy, QVBoxLayout

        row = QFrame()
        row.setObjectName("DataEntryFieldRow")
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

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
        from PySide6.QtWidgets import QLineEdit, QSizePolicy

        editor = QLineEdit(field.value_text)
        editor.setObjectName("DataEntryLineEdit")
        editor.setProperty("field_name", field.field_name)
        editor.setReadOnly(field.read_only)
        editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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
        from PySide6.QtWidgets import QComboBox, QSizePolicy

        editor = QComboBox()
        editor.setObjectName("DataEntryCombo")
        editor.setProperty("field_name", field.field_name)
        editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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

    def current_section(self) -> Any | None:
        if self.model is None or not self.model.sections:
            return None
        if self.form_selector is None:
            return self.model.sections[0]
        index = self.form_selector.currentIndex()
        if index < 0 or index >= len(self.model.sections):
            return None
        return self.model.sections[index]

    def apply_values(self, values: dict[str, Any], *, field_names: set[str] | None = None) -> int:
        applied = 0
        for field in (self.model.fields if self.model is not None else []):
            if field_names is not None and field.field_name not in field_names:
                continue
            if field.field_name not in values:
                continue
            if self.apply_field_value(field, values[field.field_name]):
                applied += 1
        self.update_branching_visibility()
        return applied

    def apply_field_value(self, field: FormFieldModel, value: Any) -> bool:
        widget = self.editor_widgets.get(field.field_name)
        if widget is None or field.read_only or field.editor == DESCRIPTION_EDITOR:
            return False
        if field.editor == TEXT_AREA_EDITOR:
            widget.setPlainText(str(value or ""))
            return True
        if field.editor == TEXT_EDITOR:
            widget.setText(str(value or ""))
            return True
        if field.editor in {DROPDOWN_EDITOR, DYNAMIC_DROPDOWN_EDITOR}:
            index = widget.findData(str(value or ""))
            if index < 0:
                index = widget.findText(str(value or ""))
            if index >= 0:
                widget.setCurrentIndex(index)
                return True
            return False
        if field.editor == RADIO_EDITOR:
            for button in widget.buttons():
                if str(button.property("choice_code")) == str(value):
                    button.setChecked(True)
                    return True
            return False
        if field.editor == CHECKBOX_EDITOR:
            selected = {str(item) for item in value} if isinstance(value, list) else {str(value)}
            for checkbox in widget:
                checkbox.setChecked(str(checkbox.property("choice_code")) in selected)
            return True
        return False

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


def field_uses_full_width(field: FormFieldModel) -> bool:
    return bool(
        field.editor in {TEXT_AREA_EDITOR, RADIO_EDITOR, CHECKBOX_EDITOR, DESCRIPTION_EDITOR}
        or field.branching_logic
        or len(str(field.label or "")) > 64
    )


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
