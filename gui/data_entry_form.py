from __future__ import annotations

import re
from typing import Any

from data_entry_form_model import (
    CHECKBOX_EDITOR,
    DATE_EDITOR,
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
from gui.i18n import tr


class DataEntryFormWidget:
    def __init__(self, model: FormRenderModel | None = None, *, language: str = "tr") -> None:
        from PySide6.QtWidgets import QVBoxLayout, QWidget

        self.language = language
        self.widget = QWidget()
        self.widget.setObjectName("DataEntryForm")
        self.layout = QVBoxLayout(self.widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(14)
        self.editor_widgets: dict[str, Any] = {}
        self.field_rows: dict[str, Any] = {}
        self.field_models: dict[str, FormFieldModel] = {}
        self.field_state_labels: dict[str, Any] = {}
        self.form_nav: Any | None = None
        self.form_stack: Any | None = None
        self._nav_section_role: Any | None = None
        self.model: FormRenderModel | None = None
        if model is not None:
            self.set_model(model)

    def set_model(self, model: FormRenderModel) -> None:
        from PySide6.QtCore import QSize, Qt
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QStackedWidget

        clear_layout(self.layout)
        self.editor_widgets = {}
        self.field_rows = {}
        self.field_models = {}
        self.field_state_labels = {}
        self.form_nav = None
        self.form_stack = None
        self._nav_section_role = None
        self.model = model

        header = QLabel(model.title)
        header.setObjectName("DataEntryRecordTitle")
        header.setWordWrap(True)
        self.layout.addWidget(header)
        if len(model.sections) > 1:
            shell = QFrame()
            shell.setObjectName("DataEntryFormShell")
            shell_layout = QHBoxLayout(shell)
            shell_layout.setContentsMargins(0, 0, 0, 0)
            shell_layout.setSpacing(14)

            form_nav = QListWidget()
            form_nav.setObjectName("DataEntryFormNav")
            form_nav.setMinimumWidth(280)
            form_nav.setMaximumWidth(360)
            form_nav.setWordWrap(True)
            form_nav.setUniformItemSizes(False)
            form_nav.setTextElideMode(Qt.TextElideMode.ElideNone)

            form_stack = QStackedWidget()
            form_stack.setObjectName("DataEntryFormStack")
            section_role = Qt.ItemDataRole.UserRole
            self._nav_section_role = section_role
            previous_event_key = object()
            has_event_groups = any(str(getattr(section, "event_label", "") or "") for section in model.sections)
            for section_index, section in enumerate(model.sections):
                event_key = (getattr(section, "event_id", ""), getattr(section, "instance", ""))
                if has_event_groups and event_key != previous_event_key:
                    event_item = QListWidgetItem(section.event_label or tr("data_entry_event_unspecified", self.language))
                    event_item.setFlags(Qt.ItemFlag.NoItemFlags)
                    event_item.setData(section_role, -1)
                    event_item.setSizeHint(QSize(260, 34))
                    form_nav.addItem(event_item)
                    previous_event_key = event_key
                item = QListWidgetItem(nav_title_for_section(section, include_event=not has_event_groups))
                item.setToolTip(section_tooltip(section))
                item.setData(section_role, section_index)
                item.setSizeHint(QSize(260, 56 if section_filled_count(section) else 46))
                form_nav.addItem(item)
                form_stack.addWidget(self.build_section_scroll(section, show_title=True))
            form_nav.currentRowChanged.connect(lambda row: self.handle_nav_row_changed(row))
            first_index = first_section_with_values(model.sections)
            self.form_nav = form_nav
            self.form_stack = form_stack
            select_nav_row_for_section(form_nav, first_index, section_role)
            shell_layout.addWidget(form_nav, 0)
            shell_layout.addWidget(form_stack, 1)
            self.layout.addWidget(shell, 1)
        else:
            for section in model.sections:
                self.layout.addWidget(self.build_section_scroll(section), 1)
        self.update_branching_visibility()

    def build_section_scroll(self, section: Any, *, show_title: bool = True) -> Any:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

        scroll = QScrollArea()
        scroll.setObjectName("DataEntrySectionScroll")
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        container.setObjectName("DataEntrySectionScrollBody")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.build_section_widget(section, show_title=show_title), 0, Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(container)
        return scroll

    def handle_nav_row_changed(self, row: int) -> None:
        if self.form_nav is None or self.form_stack is None or self._nav_section_role is None:
            return
        item = self.form_nav.item(row)
        if item is None:
            return
        section_index = item.data(self._nav_section_role)
        if section_index is None or int(section_index) < 0:
            return
        self.form_stack.setCurrentIndex(int(section_index))

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
            if getattr(section, "event_label", ""):
                event_title = QLabel(section.event_label)
                event_title.setObjectName("SectionEventTitle")
                event_title.setWordWrap(True)
                layout.addWidget(event_title)
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
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLayout, QSizePolicy, QVBoxLayout

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
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        label = QLabel(label_text)
        label.setObjectName("DataEntryFieldLabel")
        label.setWordWrap(True)
        header.addWidget(label, 1)

        state_label = QLabel("")
        state_label.setObjectName("DataEntryFieldState")
        state_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        header.addWidget(state_label, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

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
        field_key = field_widget_key(field)
        self.field_rows[field_key] = row
        self.field_models[field_key] = field
        self.field_state_labels[field_key] = state_label
        self.update_field_row_state(field_key)
        return row

    def build_editor(self, field: FormFieldModel) -> Any:
        if field.editor == DATE_EDITOR:
            return self.build_date_edit(field)
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

        field_key = field_widget_key(field)
        editor = QLineEdit(field.value_text)
        editor.setObjectName("DataEntryLineEdit")
        editor.setProperty("field_name", field.field_name)
        editor.setProperty("field_key", field_key)
        editor.setReadOnly(field.read_only)
        editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        configure_line_edit_validation(editor, field)
        editor.textChanged.connect(lambda _text=None, key=field_key: self.handle_field_changed(key))
        self.editor_widgets[field_key] = editor
        return editor

    def build_date_edit(self, field: FormFieldModel) -> Any:
        from PySide6.QtCore import QDate
        from PySide6.QtWidgets import (
            QCalendarWidget,
            QFrame,
            QHBoxLayout,
            QLineEdit,
            QMenu,
            QSizePolicy,
            QToolButton,
            QWidgetAction,
        )

        field_key = field_widget_key(field)
        frame = QFrame()
        frame.setObjectName("DataEntryDateEdit")
        frame.setProperty("field_name", field.field_name)
        frame.setProperty("field_key", field_key)
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        line_edit = QLineEdit(normalize_redcap_date_text(field.value_text))
        line_edit.setObjectName("DataEntryDateLineEdit")
        line_edit.setPlaceholderText("YYYY-MM-DD")
        line_edit.setReadOnly(field.read_only)
        line_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        button = QToolButton()
        button.setObjectName("DataEntryDateButton")
        button.setText("...")
        button.setToolTip(tr("data_entry_date_picker_tooltip", self.language))
        button.setEnabled(not field.read_only)

        menu = QMenu(button)
        calendar = QCalendarWidget()
        calendar.setGridVisible(True)
        parsed = parse_redcap_date_text(line_edit.text())
        if parsed.isValid():
            calendar.setSelectedDate(parsed)
        action = QWidgetAction(menu)
        action.setDefaultWidget(calendar)
        menu.addAction(action)

        def choose_date(date: QDate) -> None:
            line_edit.setText(date.toString("yyyy-MM-dd"))
            menu.hide()

        calendar.clicked.connect(choose_date)
        button.clicked.connect(lambda _checked=False: menu.exec(button.mapToGlobal(button.rect().bottomLeft())))
        line_edit.textChanged.connect(lambda _text=None, key=field_key: self.handle_field_changed(key))
        frame._data_entry_date_line_edit = line_edit
        frame._data_entry_date_calendar = calendar
        layout.addWidget(line_edit, 1)
        layout.addWidget(button, 0)
        self.editor_widgets[field_key] = frame
        return frame

    def build_text_area(self, field: FormFieldModel) -> Any:
        from PySide6.QtWidgets import QPlainTextEdit

        field_key = field_widget_key(field)
        editor = QPlainTextEdit(field.value_text)
        editor.setObjectName("DataEntryTextArea")
        editor.setProperty("field_name", field.field_name)
        editor.setProperty("field_key", field_key)
        editor.setMinimumHeight(96)
        editor.setReadOnly(field.read_only)
        editor.textChanged.connect(lambda key=field_key: self.handle_field_changed(key))
        self.editor_widgets[field_key] = editor
        return editor

    def build_combo(self, field: FormFieldModel) -> Any:
        from PySide6.QtWidgets import QComboBox, QSizePolicy

        field_key = field_widget_key(field)
        editor = QComboBox()
        editor.setObjectName("DataEntryCombo")
        editor.setProperty("field_name", field.field_name)
        editor.setProperty("field_key", field_key)
        editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        editor.addItem("", "")
        for choice in field.choices:
            editor.addItem(choice.label, choice.code)
        if field.editor == DYNAMIC_DROPDOWN_EDITOR and not field.choices:
            if field.value_text:
                editor.addItem(field.value_text, field.value_text)
            else:
                editor.addItem(tr("data_entry_dynamic_sql_unresolved", self.language), "")
        index = editor.findData(field.value_text)
        if index >= 0:
            editor.setCurrentIndex(index)
        editor.setEnabled(not field.read_only)
        editor.currentIndexChanged.connect(lambda _index=None, key=field_key: self.handle_field_changed(key))
        self.editor_widgets[field_key] = editor
        return editor

    def build_radio_group(self, field: FormFieldModel) -> Any:
        from PySide6.QtWidgets import QButtonGroup, QFrame, QRadioButton, QVBoxLayout

        field_key = field_widget_key(field)
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
            button.toggled.connect(lambda _checked=False, key=field_key: self.handle_field_changed(key))
            group.addButton(button)
            layout.addWidget(button)
        frame._data_entry_button_group = group
        self.editor_widgets[field_key] = group
        return frame

    def build_checkbox_group(self, field: FormFieldModel) -> Any:
        from PySide6.QtWidgets import QCheckBox, QFrame, QVBoxLayout

        field_key = field_widget_key(field)
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
            checkbox.toggled.connect(lambda _checked=False, key=field_key: self.handle_field_changed(key))
            boxes.append(checkbox)
            layout.addWidget(checkbox)
        self.editor_widgets[field_key] = boxes
        return frame

    def build_readonly(self, field: FormFieldModel) -> Any:
        from PySide6.QtWidgets import QLabel

        field_key = field_widget_key(field)
        value = field.value_text or "-"
        label = QLabel(value)
        label.setObjectName("DataEntryReadonlyValue")
        label.setWordWrap(True)
        self.editor_widgets[field_key] = label
        return label

    def collect_values(self, *, include_hidden: bool = False) -> dict[str, Any]:
        if self.model is None:
            return {}
        values: dict[str, Any] = {}
        for field in self.model.fields:
            field_key = field_widget_key(field)
            widget = self.editor_widgets.get(field_key)
            row = self.field_rows.get(field_key)
            if not include_hidden and row is not None and row.isHidden():
                continue
            if widget is None or field.read_only or field.editor == DESCRIPTION_EDITOR:
                continue
            if field.editor == TEXT_AREA_EDITOR:
                values[field_key] = widget.toPlainText()
            elif field.editor == DATE_EDITOR:
                values[field_key] = date_edit_value(widget)
            elif field.editor == TEXT_EDITOR:
                values[field_key] = widget.text()
            elif field.editor in {DROPDOWN_EDITOR, DYNAMIC_DROPDOWN_EDITOR}:
                values[field_key] = widget.currentData()
            elif field.editor == RADIO_EDITOR:
                checked = widget.checkedButton()
                values[field_key] = checked.property("choice_code") if checked is not None else ""
            elif field.editor == CHECKBOX_EDITOR:
                for checkbox in widget:
                    choice_code = checkbox.property("choice_code")
                    values[f"{field_key}___{choice_code}"] = "1" if checkbox.isChecked() else "0"
        return values

    def collect_change_set(self):
        from data_entry_form_changes import build_form_change_set

        if self.model is None:
            return None
        return build_form_change_set(self.model, self.collect_values())

    def current_section(self) -> Any | None:
        if self.model is None or not self.model.sections:
            return None
        if self.form_nav is None:
            return self.model.sections[0]
        index = self.current_section_index()
        if index < 0 or index >= len(self.model.sections):
            return None
        return self.model.sections[index]

    def current_section_index(self) -> int:
        if self.form_nav is None or self._nav_section_role is None:
            return 0
        item = self.form_nav.currentItem()
        if item is None:
            return -1
        section_index = item.data(self._nav_section_role)
        if section_index is None:
            return -1
        return int(section_index)

    def apply_values(self, values: dict[str, Any], *, field_names: set[str] | None = None) -> int:
        applied = 0
        for field in (self.model.fields if self.model is not None else []):
            field_key = field_widget_key(field)
            if field_names is not None and field.field_name not in field_names and field_key not in field_names:
                continue
            submitted_key = field_key if field_key in values else field.field_name
            if submitted_key not in values:
                continue
            if self.apply_field_value(field, values[submitted_key]):
                applied += 1
        self.update_branching_visibility()
        self.refresh_field_states()
        return applied

    def apply_field_value(self, field: FormFieldModel, value: Any) -> bool:
        widget = self.editor_widgets.get(field_widget_key(field))
        if widget is None or field.read_only or field.editor == DESCRIPTION_EDITOR:
            return False
        if field.editor == TEXT_AREA_EDITOR:
            widget.setPlainText(str(value or ""))
            return True
        if field.editor == DATE_EDITOR:
            set_date_picker_value(widget, value)
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
        for field in self.model.fields:
            row = self.field_rows.get(field_widget_key(field))
            if row is None or not field.branching_logic:
                continue
            values = self.branching_values_for_context(field)
            row.setVisible(evaluate_branching_logic(field.branching_logic, values))
        self.refresh_field_states()

    def handle_field_changed(self, field_key: str) -> None:
        self.update_field_row_state(field_key)
        self.update_branching_visibility()

    def refresh_field_states(self) -> None:
        for field_name in list(self.field_rows):
            self.update_field_row_state(field_name)

    def update_field_row_state(self, field_key: str) -> None:
        field = self.field_models.get(field_key)
        row = self.field_rows.get(field_key)
        state_label = self.field_state_labels.get(field_key)
        if field is None or row is None or state_label is None:
            return
        state = field_state(field, self.current_field_value(field))
        row.setProperty("field_state", state)
        state_label.setProperty("state", state)
        state_label.setText(field_state_label(state, self.language))
        repolish(row)
        repolish(state_label)

    def current_field_value(self, field: FormFieldModel) -> Any:
        widget = self.editor_widgets.get(field_widget_key(field))
        if widget is None:
            return field.value
        if field.editor == TEXT_AREA_EDITOR:
            return widget.toPlainText()
        if field.editor == DATE_EDITOR:
            return date_edit_value(widget)
        if field.editor == TEXT_EDITOR:
            return widget.text()
        if field.editor in {DROPDOWN_EDITOR, DYNAMIC_DROPDOWN_EDITOR}:
            return widget.currentData()
        if field.editor == RADIO_EDITOR:
            checked = widget.checkedButton()
            return checked.property("choice_code") if checked is not None else ""
        if field.editor == CHECKBOX_EDITOR:
            return [
                checkbox.property("choice_code")
                for checkbox in widget
                if checkbox.isChecked()
            ]
        return field.value

    def branching_values_for_context(self, target_field: FormFieldModel) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for field in self.model.fields if self.model is not None else []:
            if field.event_id != target_field.event_id or field.instance != target_field.instance:
                continue
            value = self.current_field_value(field)
            if field.editor == CHECKBOX_EDITOR:
                selected = {str(item) for item in value} if isinstance(value, list) else set()
                for choice in field.choices:
                    values[f"{field.field_name}___{choice.code}"] = "1" if choice.code in selected else "0"
                continue
            values[field.field_name] = value
        return values


def clear_layout(layout: Any) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            clear_layout(child_layout)


def field_widget_key(field: FormFieldModel) -> str:
    return field.context_key or field.field_name


def date_edit_value(editor: Any) -> str:
    line_edit = getattr(editor, "_data_entry_date_line_edit", None)
    if line_edit is None:
        return ""
    return normalize_redcap_date_text(line_edit.text())


def set_date_picker_value(editor: Any, value: Any) -> None:
    normalized = normalize_redcap_date_text(value)
    line_edit = getattr(editor, "_data_entry_date_line_edit", None)
    if line_edit is not None:
        line_edit.setText(normalized)
    calendar = getattr(editor, "_data_entry_date_calendar", None)
    parsed = parse_redcap_date_text(normalized)
    if calendar is not None and parsed.isValid():
        calendar.setSelectedDate(parsed)


def normalize_redcap_date_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = parse_redcap_date_text(text)
    if parsed.isValid():
        return parsed.toString("yyyy-MM-dd")
    return text


def parse_redcap_date_text(value: Any) -> Any:
    from PySide6.QtCore import QDate

    text = str(value or "").strip()
    if not text:
        return QDate()
    iso_match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text)
    if iso_match:
        return QDate(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
    slash_match = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", text)
    if slash_match:
        return QDate(int(slash_match.group(1)), int(slash_match.group(2)), int(slash_match.group(3)))
    european_match = re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", text)
    if european_match:
        return QDate(int(european_match.group(3)), int(european_match.group(2)), int(european_match.group(1)))
    return QDate()


def field_uses_full_width(field: FormFieldModel) -> bool:
    return bool(
        field.editor in {TEXT_AREA_EDITOR, RADIO_EDITOR, CHECKBOX_EDITOR, DESCRIPTION_EDITOR}
        or field.branching_logic
        or len(str(field.label or "")) > 64
    )


def field_state(field: FormFieldModel, value: Any) -> str:
    if field.editor == DESCRIPTION_EDITOR:
        return "info"
    if field_value_is_filled(value):
        return "filled"
    if field.required:
        return "required_missing"
    return "empty"


def field_state_label(state: str, language: str = "tr") -> str:
    if state == "filled":
        return tr("data_entry_field_state_filled", language)
    if state == "required_missing":
        return tr("data_entry_field_state_required_missing", language)
    if state == "info":
        return tr("data_entry_field_state_info", language)
    return tr("data_entry_field_state_empty", language)


def field_value_is_filled(value: Any) -> bool:
    if isinstance(value, list):
        return any(str(item or "").strip() for item in value)
    return str(value or "").strip() != ""


def repolish(widget: Any) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


def nav_title_for_section(section: Any, *, include_event: bool = True) -> str:
    filled = section_filled_count(section)
    total = len(getattr(section, "fields", []) or [])
    title = str(section.title)
    if include_event and getattr(section, "event_label", ""):
        title = f"{section.event_label} - {title}"
    if filled:
        return f"{title}\n{filled}/{total} alan dolu"
    return title


def section_tooltip(section: Any) -> str:
    if getattr(section, "event_label", ""):
        return f"{section.event_label}\n{section.title}"
    return str(section.title)


def select_nav_row_for_section(form_nav: Any, section_index: int, role: Any) -> None:
    for row in range(form_nav.count()):
        item = form_nav.item(row)
        if item is not None and item.data(role) == section_index:
            form_nav.setCurrentRow(row)
            return
    form_nav.setCurrentRow(0)


def first_section_with_values(sections: list[Any]) -> int:
    for index, section in enumerate(sections):
        if section_filled_count(section) > 0:
            return index
    return 0


def section_filled_count(section: Any) -> int:
    count = 0
    for field in getattr(section, "fields", []) or []:
        if field.editor == DESCRIPTION_EDITOR:
            continue
        if isinstance(field.value, list):
            if field.value:
                count += 1
            continue
        if str(field.value or "") != "":
            count += 1
    return count


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
