from __future__ import annotations

import re
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

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
from redcap_calc import evaluate_redcap_calc
from redcap_numeric import (
    is_redcap_number_validation,
    is_redcap_numeric_validation,
    normalize_redcap_numeric_text,
)


class DataEntryNavButton(QFrame):
    clicked = Signal()

    def __init__(self, text: str, *, parent: Any | None = None) -> None:
        super().__init__(parent)
        self._checked = False
        self._text = str(text or "")
        self.setObjectName("DataEntryFormNavButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(0)
        self.label = QLabel(self._text)
        self.label.setObjectName("DataEntryFormNavButtonLabel")
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

    def text(self) -> str:
        return self._text

    def setCheckable(self, _checkable: bool) -> None:
        return

    def setChecked(self, checked: bool) -> None:
        self._checked = bool(checked)
        self.setProperty("active", self._checked)
        repolish(self)
        repolish(self.label)

    def isChecked(self) -> bool:
        return self._checked

    def click(self) -> None:
        self.clicked.emit()

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space}:
            self.clicked.emit()
            return
        super().keyPressEvent(event)


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
        self.nav_buttons: dict[int, Any] = {}
        self.repeat_actions: list[dict[str, Any]] = []
        self.repeat_action_handler: Callable[[dict[str, Any]], None] | None = None
        self._current_section_index = 0
        self._rendered_sections: set[int] = set()
        self._updating_calculations = False
        self.model: FormRenderModel | None = None
        if model is not None:
            self.set_model(model)

    def set_model(
        self,
        model: FormRenderModel,
        *,
        repeat_actions: list[dict[str, Any]] | None = None,
        repeat_action_handler: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QFrame,
            QHBoxLayout,
            QLabel,
            QScrollArea,
            QSizePolicy,
            QStackedWidget,
            QVBoxLayout,
            QWidget,
        )

        clear_layout(self.layout)
        self.editor_widgets = {}
        self.field_rows = {}
        self.field_models = {}
        self.field_state_labels = {}
        self.form_nav = None
        self.form_stack = None
        self.nav_buttons = {}
        self.repeat_actions = list(repeat_actions or [])
        self.repeat_action_handler = repeat_action_handler
        self._current_section_index = 0
        self._rendered_sections = set()
        self._updating_calculations = False
        self.model = model

        header = QLabel(model.title)
        header.setObjectName("DataEntryRecordTitle")
        header.setWordWrap(True)
        self.layout.addWidget(header)
        if len(model.sections) > 1 or self.repeat_actions:
            shell = QFrame()
            shell.setObjectName("DataEntryFormShell")
            shell_layout = QHBoxLayout(shell)
            shell_layout.setContentsMargins(0, 0, 0, 0)
            shell_layout.setSpacing(14)

            form_nav = QScrollArea()
            form_nav.setObjectName("DataEntryFormNavScroll")
            form_nav.setWidgetResizable(True)
            form_nav.setMinimumWidth(320)
            form_nav.setMaximumWidth(420)
            form_nav.setFrameShape(QFrame.Shape.NoFrame)
            form_nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

            nav_body = QWidget()
            nav_body.setObjectName("DataEntryFormNav")
            nav_body.setMinimumWidth(0)
            nav_body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            nav_layout = QVBoxLayout(nav_body)
            nav_layout.setContentsMargins(8, 8, 8, 8)
            nav_layout.setSpacing(6)
            form_nav.setWidget(nav_body)

            form_stack = QStackedWidget()
            form_stack.setObjectName("DataEntryFormStack")
            has_event_groups = any(str(getattr(section, "event_label", "") or "") for section in model.sections)
            event_items: set[tuple[str, str]] = set()
            for section_index, section in enumerate(model.sections):
                event_instance = "" if getattr(section, "repeat_instrument", "") else getattr(section, "instance", "")
                event_key = (getattr(section, "event_id", ""), event_instance)
                if has_event_groups and event_key not in event_items:
                    event_action = self.repeat_action_for_event_header(
                        getattr(section, "event_id", ""),
                        event_instance,
                    )
                    nav_layout.addWidget(
                        self.build_event_header(
                            section.event_label or tr("data_entry_event_unspecified", self.language),
                            event_action,
                        )
                    )
                    event_items.add(event_key)
                inline_action = self.repeat_action_for_section(section)
                nav_wrap_width = 20 if inline_action is not None else 30
                button = DataEntryNavButton(
                    wrap_nav_title(
                        nav_title_for_section(section, include_event=not has_event_groups),
                        width=nav_wrap_width,
                    )
                )
                button.setObjectName("DataEntryFormNavButton")
                button.setToolTip(section_tooltip(section))
                button.setCheckable(True)
                button.setProperty("section_index", section_index)
                button.setMinimumHeight(nav_button_height(button.text()))
                button.setMinimumWidth(0)
                button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
                button.clicked.connect(lambda _checked=False, index=section_index: self.select_section(index))
                if inline_action is None:
                    nav_layout.addWidget(button)
                else:
                    nav_layout.addWidget(self.build_nav_button_row(button, inline_action))
                self.nav_buttons[section_index] = button
                placeholder = QWidget()
                placeholder.setObjectName("DataEntrySectionPlaceholder")
                placeholder_layout = QVBoxLayout(placeholder)
                placeholder_layout.setContentsMargins(0, 0, 0, 0)
                placeholder_layout.setSpacing(0)
                form_stack.addWidget(placeholder)
            nav_layout.addStretch(1)
            first_index = first_section_with_values(model.sections)
            self.form_nav = form_nav
            self.form_stack = form_stack
            shell_layout.addWidget(form_nav, 0)
            shell_layout.addWidget(form_stack, 1)
            self.layout.addWidget(shell, 1)
            self.select_section(first_index)
        else:
            for section in model.sections:
                self.layout.addWidget(self.build_section_scroll(section), 1)
        self.update_branching_visibility()
        self.update_calculated_fields()

    def build_event_header(self, label_text: str, action: dict[str, Any] | None = None) -> Any:
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton

        row = QFrame()
        row.setObjectName("DataEntryFormNavEventRow")
        row.setMinimumWidth(0)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        event_label = QLabel(label_text)
        event_label.setObjectName("DataEntryFormNavEvent")
        event_label.setWordWrap(True)
        event_label.setMinimumWidth(0)
        layout.addWidget(event_label, 1)
        if action is not None:
            add_button = QToolButton()
            add_button.setText("+")
            add_button.setObjectName("DataEntryFormNavEventAdd")
            add_button.setToolTip(str(action.get("label") or tr("data_entry_add_repeat", self.language)))
            add_button.setFixedSize(QSize(28, 28))
            add_button.clicked.connect(lambda _checked=False, option=action: self.trigger_repeat_action(option))
            layout.addWidget(add_button, 0)
        return row

    def build_nav_button_row(self, button: Any, action: dict[str, Any]) -> Any:
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QToolButton

        row = QFrame()
        row.setObjectName("DataEntryFormNavButtonRow")
        row.setMinimumWidth(0)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(button, 1)
        add_button = QToolButton()
        add_button.setText("+")
        add_button.setObjectName("DataEntryFormNavInlineAdd")
        add_button.setToolTip(str(action.get("label") or tr("data_entry_add_repeat", self.language)))
        add_button.setFixedSize(QSize(28, 28))
        add_button.clicked.connect(lambda _checked=False, option=action: self.trigger_repeat_action(option))
        layout.addWidget(add_button, 0)
        return row

    def repeat_action_for_section(self, section: Any) -> dict[str, Any] | None:
        if section_filled_count(section) == 0:
            return None
        for action in self.repeat_actions:
            if str(action.get("kind") or "") != "form":
                continue
            if str(action.get("form_name") or "") != str(getattr(section, "form_name", "") or ""):
                continue
            if str(action.get("event_id") or "") != str(getattr(section, "event_id", "") or ""):
                continue
            if not self.section_is_latest_repeat_form_instance(section):
                continue
            return action
        return None

    def repeat_action_for_event_header(self, event_id: str, event_instance: str) -> dict[str, Any] | None:
        if not self.event_instance_has_values(event_id, event_instance):
            return None
        for action in self.repeat_actions:
            if str(action.get("kind") or "") != "event":
                continue
            if str(action.get("event_id") or "") != str(event_id or ""):
                continue
            latest_instance = self.latest_event_instance(event_id)
            if latest_instance <= 0 and not str(event_instance or ""):
                return action
            if latest_instance > 0 and numeric_instance_value(event_instance) == latest_instance:
                return action
        return None

    def section_is_latest_repeat_form_instance(self, section: Any) -> bool:
        form_name = str(getattr(section, "form_name", "") or "")
        event_id = str(getattr(section, "event_id", "") or "")
        repeat_instrument = str(getattr(section, "repeat_instrument", "") or "")
        instance = numeric_instance_value(getattr(section, "instance", ""))
        if not form_name or repeat_instrument != form_name or instance <= 0:
            return False
        latest = 0
        for candidate in getattr(self.model, "sections", []) if self.model is not None else []:
            if str(getattr(candidate, "form_name", "") or "") != form_name:
                continue
            if str(getattr(candidate, "event_id", "") or "") != event_id:
                continue
            if str(getattr(candidate, "repeat_instrument", "") or "") != form_name:
                continue
            latest = max(latest, numeric_instance_value(getattr(candidate, "instance", "")))
        return instance == latest

    def latest_event_instance(self, event_id: str) -> int:
        latest = 0
        for section in getattr(self.model, "sections", []) if self.model is not None else []:
            if str(getattr(section, "event_id", "") or "") != str(event_id or ""):
                continue
            if str(getattr(section, "repeat_instrument", "") or ""):
                continue
            latest = max(latest, numeric_instance_value(getattr(section, "instance", "")))
        return latest

    def event_instance_has_values(self, event_id: str, event_instance: str) -> bool:
        instance_key = str(event_instance or "")
        for section in getattr(self.model, "sections", []) if self.model is not None else []:
            if str(getattr(section, "event_id", "") or "") != str(event_id or ""):
                continue
            if str(getattr(section, "repeat_instrument", "") or ""):
                continue
            if str(getattr(section, "instance", "") or "") != instance_key:
                continue
            if section_filled_count(section) > 0:
                return True
        return False

    def navigation_scroll_value(self) -> int:
        if self.form_nav is None:
            return 0
        return int(self.form_nav.verticalScrollBar().value())

    def set_navigation_scroll_value(self, value: int) -> None:
        if self.form_nav is None:
            return
        self.form_nav.verticalScrollBar().setValue(max(0, int(value or 0)))

    def trigger_repeat_action(self, option: dict[str, Any]) -> None:
        if self.repeat_action_handler is not None:
            self.repeat_action_handler(option)

    def build_section_scroll(self, section: Any, *, show_title: bool = True) -> Any:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QFrame, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

        scroll = QScrollArea()
        scroll.setObjectName("DataEntrySectionScroll")
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        container.setObjectName("DataEntrySectionScrollBody")
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.build_section_widget(section, show_title=show_title), 0, Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(container)
        return scroll

    def select_section(self, section_index: int) -> None:
        if self.form_stack is None or self.model is None:
            return
        if section_index < 0 or section_index >= len(self.model.sections):
            return
        self.render_section_at(section_index)
        self.form_stack.setCurrentIndex(section_index)
        self._current_section_index = section_index
        for index, button in self.nav_buttons.items():
            button.setChecked(index == section_index)
            button.setProperty("active", index == section_index)
            repolish(button)
        self.update_calculated_fields()
        self.update_branching_visibility()

    def render_section_at(self, section_index: int) -> None:
        if self.model is None or self.form_stack is None:
            return
        if section_index < 0 or section_index >= len(self.model.sections):
            return
        if section_index in self._rendered_sections:
            return
        placeholder = self.form_stack.widget(section_index)
        if placeholder is None:
            return
        layout = placeholder.layout()
        if layout is None:
            return
        layout.addWidget(self.build_section_scroll(self.model.sections[section_index], show_title=True))
        self._rendered_sections.add(section_index)

    def build_section_widget(self, section: Any, *, show_title: bool = True) -> Any:
        from PySide6.QtWidgets import QFrame, QLabel, QLayout, QSizePolicy, QVBoxLayout

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
            title = QLabel(section_display_title(section))
            title.setObjectName("SectionTitle")
            title.setWordWrap(True)
            layout.addWidget(title)
        if any(field.section_header for field in section.fields):
            current_header: str | None = None
            current_fields: list[FormFieldModel] = []

            def flush_group() -> None:
                nonlocal current_fields
                if not current_fields:
                    return
                if current_header:
                    layout.addWidget(self.build_field_group_widget(current_header, current_fields))
                else:
                    layout.addLayout(self.build_fields_grid(current_fields))
                current_fields = []

            for field in section.fields:
                if field.section_header:
                    flush_group()
                    current_header = str(field.section_header).strip()
                current_fields.append(field)
            flush_group()
            return frame

        layout.addLayout(self.build_fields_grid(section.fields))
        return frame

    def build_fields_grid(self, fields: list[FormFieldModel]) -> Any:
        from PySide6.QtWidgets import QGridLayout, QLayout

        field_grid = QGridLayout()
        field_grid.setContentsMargins(0, 0, 0, 0)
        field_grid.setHorizontalSpacing(14)
        field_grid.setVerticalSpacing(10)
        field_grid.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        row_index = 0
        column_index = 0
        for field in fields:
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
        return field_grid

    def build_field_group_widget(self, title: str, fields: list[FormFieldModel]) -> Any:
        from PySide6.QtWidgets import QFrame, QLabel, QLayout, QSizePolicy, QVBoxLayout

        group = QFrame()
        group.setObjectName("DataEntryFormSubsectionBlock")
        group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        header = QLabel(str(title or "").strip())
        header.setObjectName("DataEntryFormSubsectionTitle")
        header.setWordWrap(True)
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout.addWidget(header)
        layout.addLayout(self.build_fields_grid(fields))
        return group

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
        editor = QLineEdit(normalize_text_editor_value(field, field.value_text))
        editor.setObjectName("DataEntryLineEdit")
        editor.setProperty("field_name", field.field_name)
        editor.setProperty("field_key", field_key)
        editor.setReadOnly(field.read_only)
        editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        configure_line_edit_validation(editor, field)
        editor.textChanged.connect(lambda _text=None, key=field_key: self.handle_field_changed(key))
        if is_redcap_numeric_validation(field.validation):
            editor.editingFinished.connect(lambda key=field_key: self.normalize_numeric_editor(key))
        self.editor_widgets[field_key] = editor
        return editor

    def build_date_edit(self, field: FormFieldModel) -> Any:
        from PySide6.QtCore import QDate, QEvent, QObject, QTimer
        from PySide6.QtWidgets import (
            QCalendarWidget,
            QFrame,
            QHBoxLayout,
            QLineEdit,
            QMenu,
            QSizePolicy,
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

        menu = QMenu(line_edit)
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
            menu.close()

        def show_calendar() -> None:
            if line_edit.isReadOnly() or menu.isVisible():
                return
            current_date = parse_redcap_date_text(line_edit.text())
            if current_date.isValid():
                calendar.setSelectedDate(current_date)
            menu.popup(line_edit.mapToGlobal(line_edit.rect().bottomLeft()))

        class DatePopupFilter(QObject):
            def eventFilter(self, watched: Any, event: Any) -> bool:
                if event.type() == QEvent.Type.MouseButtonPress:
                    QTimer.singleShot(0, show_calendar)
                return False

        calendar.clicked.connect(choose_date)
        calendar.activated.connect(choose_date)
        line_edit.textChanged.connect(lambda _text=None, key=field_key: self.handle_field_changed(key))
        popup_filter = DatePopupFilter(line_edit)
        line_edit.installEventFilter(popup_filter)
        frame._data_entry_date_line_edit = line_edit
        frame._data_entry_date_calendar = calendar
        frame._data_entry_date_menu = menu
        frame._data_entry_date_popup_filter = popup_filter
        layout.addWidget(line_edit, 1)
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
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QComboBox, QSizePolicy

        field_key = field_widget_key(field)
        editor = QComboBox()
        editor.setObjectName("DataEntryCombo")
        editor.setProperty("field_name", field.field_name)
        editor.setProperty("field_key", field_key)
        editor.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        editor.setMinimumContentsLength(14)
        editor.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        editor.view().setTextElideMode(Qt.TextElideMode.ElideRight)
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
        from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QRadioButton, QToolButton, QVBoxLayout

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
        clear_row = QHBoxLayout()
        clear_row.setContentsMargins(0, 2, 0, 0)
        clear_row.addStretch(1)
        clear_button = QToolButton()
        clear_button.setObjectName("DataEntryClearRadioButton")
        clear_button.setText(tr("data_entry_clear_radio", self.language))
        clear_button.setEnabled(not field.read_only and group.checkedButton() is not None)
        clear_button.clicked.connect(lambda _checked=False, key=field_key: self.clear_radio_selection(key))
        clear_row.addWidget(clear_button, 0)
        layout.addLayout(clear_row)
        frame._data_entry_button_group = group
        frame._data_entry_clear_button = clear_button
        frame._data_entry_radio_read_only = field.read_only
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
        label.setProperty("field_name", field.field_name)
        label.setProperty("field_key", field_key)
        if field.field_type == "calc":
            label.setProperty("calculated", True)
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
                values[field_key] = normalize_text_editor_value(field, widget.text())
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
        if self.form_nav is None:
            return 0
        return self._current_section_index

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
            widget.setText(normalize_text_editor_value(field, value))
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
            if str(value or "") == "":
                clear_radio_group(widget)
                self.update_radio_clear_button(field_widget_key(field))
                return True
            for button in widget.buttons():
                if str(button.property("choice_code")) == str(value):
                    button.setChecked(True)
                    self.update_radio_clear_button(field_widget_key(field))
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
        self.update_radio_clear_button(field_key)
        self.update_field_row_state(field_key)
        self.update_calculated_fields()
        self.update_branching_visibility()

    def normalize_numeric_editor(self, field_key: str) -> None:
        field = self.field_models.get(field_key)
        editor = self.editor_widgets.get(field_key)
        if field is None or editor is None or not hasattr(editor, "text") or not hasattr(editor, "setText"):
            return
        if not is_redcap_numeric_validation(field.validation):
            return
        normalized = normalize_redcap_numeric_text(editor.text(), field.validation)
        if normalized != editor.text():
            editor.setText(normalized)
        self.handle_field_changed(field_key)

    def clear_radio_selection(self, field_key: str) -> None:
        group = self.editor_widgets.get(field_key)
        if group is None:
            return
        clear_radio_group(group)
        self.handle_field_changed(field_key)

    def update_radio_clear_button(self, field_key: str) -> None:
        group = self.editor_widgets.get(field_key)
        if group is None or not hasattr(group, "parent"):
            return
        parent = group.parent()
        clear_button = getattr(parent, "_data_entry_clear_button", None)
        if clear_button is None:
            return
        clear_button.setEnabled(
            group.checkedButton() is not None
            and not bool(getattr(parent, "_data_entry_radio_read_only", False))
        )

    def update_calculated_fields(self) -> None:
        if self.model is None or self._updating_calculations:
            return
        self._updating_calculations = True
        try:
            for field in self.model.fields:
                if field.field_type != "calc" or not field.calc_expression:
                    continue
                field_key = field_widget_key(field)
                widget = self.editor_widgets.get(field_key)
                if widget is None or not hasattr(widget, "setText"):
                    continue
                calculated = evaluate_redcap_calc(
                    field.calc_expression,
                    self.values_for_context(field, include_calculated=False),
                )
                widget.setText(calculated or "-")
                self.update_field_row_state(field_key)
        finally:
            self._updating_calculations = False

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
        if field.editor == READONLY_EDITOR:
            if hasattr(widget, "text"):
                text = str(widget.text() or "")
                return "" if text == "-" else text
            return field.value
        if field.editor == TEXT_AREA_EDITOR:
            return widget.toPlainText()
        if field.editor == DATE_EDITOR:
            return date_edit_value(widget)
        if field.editor == TEXT_EDITOR:
            return normalize_text_editor_value(field, widget.text())
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
        return self.values_for_context(target_field, include_calculated=True)

    def values_for_context(self, target_field: FormFieldModel, *, include_calculated: bool) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for field in self.model.fields if self.model is not None else []:
            if (
                field.event_id != target_field.event_id
                or field.repeat_instrument != target_field.repeat_instrument
                or field.instance != target_field.instance
            ):
                continue
            if not include_calculated and field.field_type == "calc":
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


def clear_radio_group(group: Any) -> None:
    checked = group.checkedButton() if hasattr(group, "checkedButton") else None
    if checked is None:
        return
    group.setExclusive(False)
    checked.setChecked(False)
    group.setExclusive(True)


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
    title = section_display_title(section)
    if include_event and getattr(section, "event_label", ""):
        title = f"{section.event_label} - {title}"
    if filled:
        return f"{title}\n{filled}/{total} alan dolu"
    return title


def wrap_nav_title(title: str, *, width: int = 30) -> str:
    lines: list[str] = []
    for raw_line in str(title or "").splitlines():
        words = raw_line.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            if len(current) + 1 + len(word) <= width:
                current = f"{current} {word}"
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return "\n".join(lines)


def nav_button_height(text: str) -> int:
    line_count = max(1, len(str(text or "").splitlines()))
    return max(48, 30 + (line_count * 22))


def section_tooltip(section: Any) -> str:
    if getattr(section, "event_label", ""):
        return f"{section.event_label}\n{section_display_title(section)}"
    return section_display_title(section)


def section_display_title(section: Any) -> str:
    title = str(getattr(section, "title", "") or "")
    if getattr(section, "repeat_instrument", "") and getattr(section, "instance", ""):
        return f"{title} #{section.instance}"
    return title


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


def numeric_instance_value(value: Any) -> int:
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0


def normalize_text_editor_value(field: FormFieldModel, value: Any) -> str:
    text = "" if value is None else str(value)
    if is_redcap_numeric_validation(field.validation):
        return normalize_redcap_numeric_text(text, field.validation)
    return text


def configure_line_edit_validation(editor: Any, field: FormFieldModel) -> None:
    from PySide6.QtCore import QRegularExpression
    from PySide6.QtGui import QRegularExpressionValidator

    validation = str(field.validation or "").strip().lower()
    if validation == "integer":
        editor.setValidator(QRegularExpressionValidator(QRegularExpression(r"[+-]?\d*"), editor))
        return
    if is_redcap_number_validation(validation):
        validator = QRegularExpressionValidator(
            QRegularExpression(r"[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d*)?(?:[eE][+-]?\d*)?"),
            editor,
        )
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
