from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Mapping

from PySide6.QtCore import QEvent, QObject, QTimer, Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QLineEdit, QVBoxLayout

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


def data_entry_asset_path(filename: str) -> str:
    return str(Path(__file__).with_name("assets") / filename)


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


class DataEntryDateLineEdit(QLineEdit):
    """Date input that requests its calendar from direct user navigation."""

    calendarRequested = Signal()

    def __init__(self, text: str = "", *, parent: Any | None = None) -> None:
        super().__init__(text, parent)
        self._calendar_request_pending = False

    def mousePressEvent(self, event: Any) -> None:
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._queue_calendar_request()

    def focusInEvent(self, event: Any) -> None:
        super().focusInEvent(event)
        if event.reason() in {
            Qt.FocusReason.TabFocusReason,
            Qt.FocusReason.BacktabFocusReason,
            Qt.FocusReason.ShortcutFocusReason,
            Qt.FocusReason.OtherFocusReason,
        }:
            self._queue_calendar_request()

    def _queue_calendar_request(self) -> None:
        if self.isReadOnly() or not self.isEnabled() or self._calendar_request_pending:
            return
        self._calendar_request_pending = True
        QTimer.singleShot(0, self._emit_calendar_request)

    def _emit_calendar_request(self) -> None:
        self._calendar_request_pending = False
        if not self.isReadOnly() and self.isEnabled():
            self.calendarRequested.emit()


class DataEntryCalendarYearControls(QObject):
    """Stable year step buttons for platforms whose native spin arrows disappear."""

    def __init__(self, spin_box: Any) -> None:
        from PySide6.QtWidgets import QAbstractSpinBox, QToolButton

        super().__init__(spin_box)
        self.spin_box = spin_box
        spin_box.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        spin_box.setMinimumWidth(96)

        self.up_button = QToolButton(spin_box)
        self.up_button.setObjectName("DataEntryCalendarYearUp")
        self.up_button.setText("▲")
        self.up_button.setAccessibleName("Increase year")
        self.up_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.up_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.up_button.setAutoRepeat(True)
        self.up_button.clicked.connect(spin_box.stepUp)

        self.down_button = QToolButton(spin_box)
        self.down_button.setObjectName("DataEntryCalendarYearDown")
        self.down_button.setText("▼")
        self.down_button.setAccessibleName("Decrease year")
        self.down_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.down_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.down_button.setAutoRepeat(True)
        self.down_button.clicked.connect(spin_box.stepDown)

        spin_box.installEventFilter(self)
        self.position_buttons()
        self.up_button.show()
        self.down_button.show()

    def eventFilter(self, watched: Any, event: Any) -> bool:
        if watched is self.spin_box and event.type() in {
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.Polish,
            QEvent.Type.StyleChange,
        }:
            QTimer.singleShot(0, self.position_buttons)
        return super().eventFilter(watched, event)

    def position_buttons(self) -> None:
        button_width = 23
        inset = 1
        available_height = max(24, self.spin_box.height() - (inset * 2))
        upper_height = available_height // 2
        x = max(inset, self.spin_box.width() - button_width - inset)
        self.up_button.setGeometry(x, inset, button_width, upper_height)
        self.down_button.setGeometry(
            x,
            inset + upper_height,
            button_width,
            available_height - upper_height,
        )
        self.up_button.raise_()
        self.down_button.raise_()


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
        self.field_progress_labels: dict[str, Any] = {}
        self.form_nav: Any | None = None
        self.form_stack: Any | None = None
        self.event_nav: Any | None = None
        self.record_home_stack: Any | None = None
        self.record_matrix: Any | None = None
        self.record_home_context_label: Any | None = None
        self.nav_buttons: dict[int, Any] = {}
        self.repeat_actions: list[dict[str, Any]] = []
        self.repeat_action_handler: Callable[[dict[str, Any]], None] | None = None
        self.section_change_handler: Callable[[Any | None], None] | None = None
        self.field_change_handler: Callable[[str], None] | None = None
        self.event_order: list[str] = []
        self.form_order: list[str] = []
        self._current_section_index = 0
        self._rendered_sections: set[int] = set()
        self._updating_calculations = False
        self.model: FormRenderModel | None = None
        if model is not None:
            self.set_model(model)
        else:
            self.show_empty_state()

    def show_empty_state(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

        empty = QFrame()
        empty.setObjectName("DataEntryFormEmpty")
        empty_layout = QVBoxLayout(empty)
        empty_layout.setContentsMargins(24, 24, 24, 24)
        empty_layout.setSpacing(7)
        title = QLabel(tr("data_entry_form_empty_title", self.language))
        title.setObjectName("DataEntryFormEmptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body = QLabel(tr("data_entry_form_empty_body", self.language))
        body.setObjectName("MutedLabel")
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setWordWrap(True)
        empty_layout.addStretch(1)
        empty_layout.addWidget(title)
        empty_layout.addWidget(body)
        empty_layout.addStretch(1)
        self.layout.addWidget(empty, 1)

    def clear_model(self) -> None:
        """Remove the rendered record and restore the initial empty state."""
        clear_layout(self.layout)
        self.editor_widgets = {}
        self.field_rows = {}
        self.field_models = {}
        self.field_state_labels = {}
        self.field_progress_labels = {}
        self.form_nav = None
        self.form_stack = None
        self.event_nav = None
        self.record_home_stack = None
        self.record_matrix = None
        self.record_home_context_label = None
        self.nav_buttons = {}
        self.repeat_actions = []
        self.repeat_action_handler = None
        self.event_order = []
        self.form_order = []
        self._current_section_index = -1
        self._rendered_sections = set()
        self._updating_calculations = False
        self.model = None
        self.show_empty_state()
        self.notify_section_changed()

    def set_model(
        self,
        model: FormRenderModel,
        *,
        repeat_actions: list[dict[str, Any]] | None = None,
        repeat_action_handler: Callable[[dict[str, Any]], None] | None = None,
        event_order: list[str] | None = None,
        form_order: list[str] | None = None,
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
        self.field_progress_labels = {}
        self.form_nav = None
        self.form_stack = None
        self.event_nav = None
        self.record_home_stack = None
        self.record_matrix = None
        self.record_home_context_label = None
        self.nav_buttons = {}
        self.repeat_actions = list(repeat_actions or [])
        self.repeat_action_handler = repeat_action_handler
        self.event_order = [str(item) for item in (event_order or [])]
        self.form_order = [str(item) for item in (form_order or [])]
        self._current_section_index = 0
        self._rendered_sections = set()
        self._updating_calculations = False
        self.model = model

        header_frame = QFrame()
        header_frame.setObjectName("DataEntryFormHeader")
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(2)
        header = QLabel(model.title)
        header.setObjectName("DataEntryRecordTitle")
        header.setWordWrap(True)
        header_layout.addWidget(header)
        self.layout.addWidget(header_frame)
        use_event_navigation = bool(self.repeat_actions) or any(
            str(getattr(section, "event_id", "") or "")
            for section in model.sections
        )
        if use_event_navigation:
            self.build_event_form_shell(model)
        elif len(model.sections) > 1:
            shell = QFrame()
            shell.setObjectName("DataEntryFormShell")
            shell_layout = QHBoxLayout(shell)
            shell_layout.setContentsMargins(0, 0, 0, 0)
            shell_layout.setSpacing(12)

            form_nav = QScrollArea()
            form_nav.setObjectName("DataEntryFormNavScroll")
            form_nav.setWidgetResizable(True)
            form_nav.setMinimumWidth(205)
            form_nav.setMaximumWidth(270)
            form_nav.setFrameShape(QFrame.Shape.NoFrame)
            form_nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

            nav_body = QWidget()
            nav_body.setObjectName("DataEntryFormNav")
            nav_body.setMinimumWidth(0)
            nav_body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            nav_layout = QVBoxLayout(nav_body)
            nav_layout.setContentsMargins(10, 10, 10, 10)
            nav_layout.setSpacing(7)
            form_nav.setWidget(nav_body)

            form_stack = QStackedWidget()
            form_stack.setObjectName("DataEntryFormStack")
            has_event_groups = any(str(getattr(section, "event_label", "") or "") for section in model.sections)
            event_items: set[tuple[str, str]] = set()
            for section_index, section in enumerate(model.sections):
                event_instance = "" if getattr(section, "repeat_instrument", "") else getattr(section, "instance", "")
                event_key = (getattr(section, "event_id", ""), event_instance)
                if has_event_groups and event_key not in event_items:
                    nav_layout.addWidget(
                        self.build_event_header(
                            section.event_label or tr("data_entry_event_unspecified", self.language),
                        )
                    )
                    event_items.add(event_key)
                button = DataEntryNavButton(
                    wrap_nav_title(
                        nav_title_for_section(section, include_event=not has_event_groups),
                        width=30,
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
                nav_layout.addWidget(button)
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
            self._current_section_index = 0 if model.sections else -1
            self.notify_section_changed()
        self.update_branching_visibility()
        self.update_calculated_fields()

    def build_event_form_shell(self, model: FormRenderModel) -> None:
        """Show REDCap events as a persistent accordion beside the active form."""

        from PySide6.QtWidgets import (
            QFrame,
            QHBoxLayout,
            QSizePolicy,
            QStackedWidget,
            QVBoxLayout,
            QWidget,
        )

        from gui.data_entry_event_nav import DataEntryEventNav

        shell = QFrame()
        shell.setObjectName("DataEntryFormShell")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(10)

        nav_panel = QFrame()
        nav_panel.setObjectName("DataEntryEventNavPanel")
        nav_panel.setMinimumWidth(220)
        nav_panel.setMaximumWidth(300)
        nav_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        nav_panel_layout = QVBoxLayout(nav_panel)
        nav_panel_layout.setContentsMargins(8, 8, 8, 8)
        nav_panel_layout.setSpacing(0)

        event_nav = DataEntryEventNav(language=self.language)
        event_nav.targetActivated.connect(self.select_section)
        event_nav.repeatActionRequested.connect(self.trigger_repeat_action)
        event_nav.set_record_model(
            model,
            repeat_actions=self.repeat_actions,
            event_order=self.event_order,
            form_order=self.form_order,
        )
        nav_panel_layout.addWidget(event_nav, 1)

        form_stack = QStackedWidget()
        form_stack.setObjectName("DataEntryFormStack")
        for _section in model.sections:
            placeholder = QWidget()
            placeholder.setObjectName("DataEntrySectionPlaceholder")
            placeholder_layout = QVBoxLayout(placeholder)
            placeholder_layout.setContentsMargins(0, 0, 0, 0)
            placeholder_layout.setSpacing(0)
            form_stack.addWidget(placeholder)

        shell_layout.addWidget(nav_panel, 0)
        shell_layout.addWidget(form_stack, 1)
        self.layout.addWidget(shell, 1)

        self.event_nav = event_nav
        self.form_nav = event_nav.scroll
        self.form_stack = form_stack
        if model.sections:
            first_index = first_section_with_values(model.sections)
            event_nav.set_expanded_keys(())
            self.select_section(first_index)
        else:
            self._current_section_index = -1
            self.notify_section_changed()

    def build_record_home(self, model: FormRenderModel) -> None:
        from PySide6.QtWidgets import (
            QFrame,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QStackedWidget,
            QVBoxLayout,
            QWidget,
        )

        from gui.data_entry_record_matrix import DataEntryRecordMatrix, matrix_text

        root_stack = QStackedWidget()
        root_stack.setObjectName("DataEntryRecordHomeStack")

        overview = QWidget()
        overview.setObjectName("DataEntryRecordHomePage")
        overview_layout = QVBoxLayout(overview)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.setSpacing(10)

        intro = QFrame()
        intro.setObjectName("DataEntryRecordHomeIntro")
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(14, 11, 14, 11)
        intro_layout.setSpacing(3)
        intro_title = QLabel(tr("data_entry_record_home_title", self.language))
        intro_title.setObjectName("DataEntryRecordHomeTitle")
        intro_body = QLabel(tr("data_entry_record_home_body", self.language))
        intro_body.setObjectName("DataEntryRecordHomeBody")
        intro_body.setWordWrap(True)
        intro_layout.addWidget(intro_title)
        intro_layout.addWidget(intro_body)
        legend = QHBoxLayout()
        legend.setContentsMargins(0, 4, 0, 0)
        legend.setSpacing(12)
        for status in ("empty", "incomplete", "unverified", "filled"):
            item = QLabel(f"● {matrix_text(status, self.language)}")
            item.setObjectName("DataEntryRecordHomeLegend")
            item.setProperty("matrix_status", status)
            legend.addWidget(item)
        legend.addStretch(1)
        intro_layout.addLayout(legend)
        overview_layout.addWidget(intro)

        matrix = DataEntryRecordMatrix(language=self.language)
        matrix.targetActivated.connect(self.select_section)
        matrix.repeatActionRequested.connect(self.trigger_repeat_action)
        matrix.set_record_model(
            model,
            repeat_actions=self.repeat_actions,
            event_order=self.event_order,
            form_order=self.form_order,
        )
        overview_layout.addWidget(matrix, 1)
        root_stack.addWidget(overview)

        editor_page = QWidget()
        editor_page.setObjectName("DataEntryRecordEditorPage")
        editor_layout = QVBoxLayout(editor_page)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)
        editor_toolbar = QFrame()
        editor_toolbar.setObjectName("DataEntryRecordEditorToolbar")
        editor_toolbar_layout = QHBoxLayout(editor_toolbar)
        editor_toolbar_layout.setContentsMargins(10, 8, 10, 8)
        editor_toolbar_layout.setSpacing(9)
        back_button = QPushButton(tr("data_entry_record_home_back", self.language))
        back_button.setObjectName("DataEntryRecordHomeBack")
        back_button.setProperty("secondary", True)
        back_button.setProperty("compact", True)
        back_button.clicked.connect(self.show_record_overview)
        editor_toolbar_layout.addWidget(back_button)
        context_label = QLabel("")
        context_label.setObjectName("DataEntryRecordEditorContext")
        context_label.setWordWrap(True)
        editor_toolbar_layout.addWidget(context_label, 1)
        editor_layout.addWidget(editor_toolbar)

        form_stack = QStackedWidget()
        form_stack.setObjectName("DataEntryFormStack")
        for _section in model.sections:
            placeholder = QWidget()
            placeholder.setObjectName("DataEntrySectionPlaceholder")
            placeholder_layout = QVBoxLayout(placeholder)
            placeholder_layout.setContentsMargins(0, 0, 0, 0)
            placeholder_layout.setSpacing(0)
            form_stack.addWidget(placeholder)
        editor_layout.addWidget(form_stack, 1)
        root_stack.addWidget(editor_page)

        self.form_stack = form_stack
        self.record_home_stack = root_stack
        self.record_matrix = matrix
        self.record_home_context_label = context_label
        self._current_section_index = -1
        self.layout.addWidget(root_stack, 1)
        self.show_record_overview()

    def show_record_overview(self) -> None:
        if self.record_home_stack is None:
            return
        self.record_home_stack.setCurrentIndex(0)
        self._current_section_index = -1
        if self.record_matrix is not None:
            self.record_matrix.set_selected_section(-1)
        self.notify_section_changed()

    def notify_section_changed(self) -> None:
        if self.section_change_handler is not None:
            self.section_change_handler(self.current_section())

    def build_event_header(self, label_text: str) -> Any:
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

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
        return row

    def section_currently_has_values(self, section: Any) -> bool:
        for field in getattr(section, "fields", []) or []:
            if field.editor == DESCRIPTION_EDITOR:
                continue
            if field_value_is_filled(self.current_field_value(field)):
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

    def navigation_state(self) -> dict[str, Any]:
        if self.event_nav is not None:
            return self.event_nav.navigation_state()
        return {"scroll": {"vertical": self.navigation_scroll_value(), "horizontal": 0}}

    def restore_navigation_state(self, state: Mapping[str, Any]) -> None:
        if self.event_nav is not None:
            self.event_nav.restore_navigation_state(state)
            return
        scroll = state.get("scroll", {})
        if isinstance(scroll, Mapping):
            self.set_navigation_scroll_value(int(scroll.get("vertical", 0)))
        elif isinstance(scroll, int):
            self.set_navigation_scroll_value(scroll)

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
        if self.record_home_stack is not None:
            self.record_home_stack.setCurrentIndex(1)
        if self.record_matrix is not None:
            self.record_matrix.set_selected_section(section_index)
        if self.event_nav is not None:
            self.event_nav.set_selected_section(section_index)
        if self.record_home_context_label is not None:
            section = self.model.sections[section_index]
            self.record_home_context_label.setText(section_tooltip(section))
        for index, button in self.nav_buttons.items():
            button.setChecked(index == section_index)
            button.setProperty("active", index == section_index)
            repolish(button)
        self.update_calculated_fields()
        self.update_branching_visibility()
        self.refresh_current_navigation_status(dirty=False)
        self.notify_section_changed()

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
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLayout, QSizePolicy, QVBoxLayout

        frame = QFrame()
        frame.setObjectName("DataEntryFormSection")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 20)
        layout.setSpacing(12)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        if show_title:
            heading = QFrame()
            heading.setObjectName("DataEntryFormHeading")
            heading_layout = QHBoxLayout(heading)
            heading_layout.setContentsMargins(0, 0, 0, 10)
            heading_layout.setSpacing(12)
            heading_text = QVBoxLayout()
            heading_text.setContentsMargins(0, 0, 0, 0)
            heading_text.setSpacing(4)
            event_label = str(getattr(section, "event_label", "") or "").strip()
            form_title = section_display_title(section)
            if event_label and not section_headings_equivalent(event_label, form_title):
                event_title = QLabel(event_label)
                event_title.setObjectName("SectionEventTitle")
                event_title.setWordWrap(True)
                heading_text.addWidget(event_title)
            title = QLabel(form_title)
            title.setObjectName("SectionTitle")
            title.setWordWrap(True)
            heading_text.addWidget(title)
            heading_layout.addLayout(heading_text, 1)

            visible_fields = [
                field for field in section.fields if field.editor != DESCRIPTION_EDITOR
            ]
            required_fields = [field for field in visible_fields if field.required]
            filled_required = sum(
                1 for field in required_fields if field_value_is_filled(field.value)
            )
            progress = QLabel(
                tr(
                    "data_entry_required_progress",
                    self.language,
                    filled=filled_required,
                    total=len(required_fields),
                )
                if required_fields
                else tr("data_entry_required_progress_none", self.language)
            )
            progress.setObjectName("DataEntryFormProgress")
            progress.setProperty("section_context", str(getattr(section, "context_key", "") or ""))
            progress.setProperty(
                "complete",
                bool(required_fields) and filled_required == len(required_fields),
            )
            heading_layout.addWidget(progress, 0, Qt.AlignmentFlag.AlignTop)
            section_key = str(getattr(section, "context_key", "") or section.form_name)
            self.field_progress_labels[section_key] = progress
            layout.addWidget(heading)
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
        field_grid.setHorizontalSpacing(12)
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
        layout.setContentsMargins(14, 12, 14, 13)
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
        row.setProperty("editor_kind", field.editor)
        row.setProperty("required", bool(field.required))
        row.setProperty("conditional", bool(field.branching_logic))
        row.setProperty("calculated", field.field_type == "calc")
        row.setProperty("read_only", bool(field.read_only))
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(row)
        layout.setContentsMargins(8, 5, 8, 6)
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
            branching = QLabel(tr("data_entry_conditional_field", self.language))
            branching.setObjectName("DataEntryBranchingLogic")
            branching.setToolTip(field.branching_logic)
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
        from PySide6.QtCore import QDate, QLocale, QSize
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import (
            QCalendarWidget,
            QFrame,
            QHBoxLayout,
            QMenu,
            QSpinBox,
            QSizePolicy,
            QToolButton,
            QWidgetAction,
        )

        from gui.clinical_styles import CLINICAL_CALENDAR_MENU_STYLE, CLINICAL_CALENDAR_STYLE

        field_key = field_widget_key(field)
        frame = QFrame()
        frame.setObjectName("DataEntryDateEdit")
        frame.setProperty("field_name", field.field_name)
        frame.setProperty("field_key", field_key)
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        line_edit = DataEntryDateLineEdit(normalize_redcap_date_text(field.value_text))
        line_edit.setObjectName("DataEntryDateLineEdit")
        line_edit.setPlaceholderText("YYYY-MM-DD")
        line_edit.setReadOnly(field.read_only)
        line_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        button = QToolButton()
        button.setObjectName("DataEntryDateButton")
        button.setIcon(QIcon(data_entry_asset_path("calendar.svg")))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tr("data_entry_date_picker_tooltip", self.language))
        button.setAccessibleName(tr("data_entry_date_picker_tooltip", self.language))
        button.setEnabled(not field.read_only)
        button.setCursor(Qt.CursorShape.PointingHandCursor)

        clear_button = QToolButton()
        clear_button.setObjectName("DataEntryDateClearButton")
        clear_button.setIcon(QIcon(data_entry_asset_path("date_clear.svg")))
        clear_button.setIconSize(QSize(18, 18))
        clear_button.setToolTip(tr("data_entry_date_clear_tooltip", self.language))
        clear_button.setAccessibleName(tr("data_entry_date_clear_tooltip", self.language))
        clear_button.setEnabled(not field.read_only)
        clear_button.setCursor(Qt.CursorShape.PointingHandCursor)

        menu = QMenu(line_edit)
        menu.setObjectName("DataEntryDateMenu")
        menu.setStyleSheet(CLINICAL_CALENDAR_MENU_STYLE)
        calendar = QCalendarWidget()
        calendar.setObjectName("DataEntryCalendar")
        calendar.setStyleSheet(CLINICAL_CALENDAR_STYLE)
        calendar.setLocale(
            QLocale(QLocale.Language.Turkish, QLocale.Country.Turkey)
            if self.language == "tr"
            else QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
        )
        calendar.setNavigationBarVisible(True)
        calendar.setGridVisible(True)
        calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        calendar.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        calendar.setMinimumSize(336, 286)
        parsed = parse_redcap_date_text(line_edit.text())
        if parsed.isValid():
            calendar.setSelectedDate(parsed)
        year_spin_box = calendar.findChild(QSpinBox, "qt_calendar_yearedit")
        year_controls = DataEntryCalendarYearControls(year_spin_box) if year_spin_box is not None else None
        action = QWidgetAction(menu)
        action.setDefaultWidget(calendar)
        menu.addAction(action)

        def choose_date(date: QDate) -> None:
            line_edit.setText(date.toString("yyyy-MM-dd"))
            menu.close()

        def normalize_typed_date() -> None:
            normalized = normalize_redcap_date_text(line_edit.text())
            parsed_date = parse_redcap_date_text(normalized)
            if not parsed_date.isValid():
                return
            line_edit.setText(parsed_date.toString("yyyy-MM-dd"))
            calendar.setSelectedDate(parsed_date)

        def update_clear_button(text: str = "") -> None:
            clear_button.setVisible(not field.read_only and bool(str(text or "").strip()))

        def clear_date() -> None:
            if field.read_only:
                return
            line_edit.clear()
            calendar.setSelectedDate(QDate.currentDate())
            line_edit.setFocus(Qt.FocusReason.MouseFocusReason)

        def show_calendar() -> None:
            if line_edit.isReadOnly() or menu.isVisible():
                return
            current_date = parse_redcap_date_text(line_edit.text())
            if current_date.isValid():
                calendar.setSelectedDate(current_date)
            menu.popup(line_edit.mapToGlobal(line_edit.rect().bottomLeft()))

        calendar.clicked.connect(choose_date)
        calendar.activated.connect(choose_date)
        line_edit.textChanged.connect(lambda _text=None, key=field_key: self.handle_field_changed(key))
        line_edit.textChanged.connect(update_clear_button)
        line_edit.editingFinished.connect(normalize_typed_date)
        line_edit.calendarRequested.connect(show_calendar)
        button.clicked.connect(lambda _checked=False: show_calendar())
        clear_button.clicked.connect(lambda _checked=False: clear_date())
        frame._data_entry_date_line_edit = line_edit
        frame._data_entry_date_calendar = calendar
        frame._data_entry_date_menu = menu
        frame._data_entry_date_button = button
        frame._data_entry_date_clear_button = clear_button
        frame._data_entry_date_year_controls = year_controls
        layout.addWidget(line_edit, 1)
        layout.addWidget(clear_button, 0)
        layout.addWidget(button, 0)
        update_clear_button(line_edit.text())
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
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

        field_key = field_widget_key(field)
        value = field.value_text or "-"
        if field.field_type == "calc":
            container = QFrame()
            container.setObjectName("DataEntryCalculatedValue")
            container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            container_layout = QHBoxLayout(container)
            container_layout.setContentsMargins(12, 9, 12, 9)
            container_layout.setSpacing(10)
            icon = QLabel("")
            icon.setObjectName("DataEntryCalculatedIcon")
            icon.setPixmap(QIcon(data_entry_asset_path("calculator_lock.svg")).pixmap(QSize(20, 20)))
            container_layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
            text_layout = QVBoxLayout()
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(2)
            label = QLabel(value)
            label.setObjectName("DataEntryReadonlyValue")
            label.setProperty("calculated", True)
            hint = QLabel(tr("data_entry_calculated_hint", self.language))
            hint.setObjectName("DataEntryCalculatedHint")
            text_layout.addWidget(label)
            text_layout.addWidget(hint)
            container_layout.addLayout(text_layout, 1)
            label.setProperty("field_name", field.field_name)
            label.setProperty("field_key", field_key)
            label.setWordWrap(True)
            container._data_entry_value_label = label
            self.editor_widgets[field_key] = label
            return container

        label = QLabel(value)
        label.setObjectName("DataEntryReadonlyValue")
        label.setProperty("field_name", field.field_name)
        label.setProperty("field_key", field_key)
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
        if self.record_home_stack is not None:
            index = self.current_section_index()
            if index < 0 or index >= len(self.model.sections):
                return None
            return self.model.sections[index]
        if self.form_nav is None:
            return self.model.sections[0]
        index = self.current_section_index()
        if index < 0 or index >= len(self.model.sections):
            return None
        return self.model.sections[index]

    def current_section_index(self) -> int:
        if self.record_home_stack is not None:
            return self._current_section_index
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
        self.refresh_current_navigation_status(dirty=True)
        if self.field_change_handler is not None:
            self.field_change_handler(field_key)

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
        self.refresh_section_progress()

    def refresh_section_progress(self) -> None:
        if self.model is None:
            return
        for section in self.model.sections:
            section_key = str(getattr(section, "context_key", "") or section.form_name)
            progress = self.field_progress_labels.get(section_key)
            if progress is None:
                continue
            required_fields = [
                field
                for field in section.fields
                if field.required and field.editor != DESCRIPTION_EDITOR
            ]
            filled_required = sum(
                1
                for field in required_fields
                if field_value_is_filled(self.current_field_value(field))
            )
            progress.setText(
                tr(
                    "data_entry_required_progress",
                    self.language,
                    filled=filled_required,
                    total=len(required_fields),
                )
                if required_fields
                else tr("data_entry_required_progress_none", self.language)
            )
            progress.setProperty(
                "complete",
                bool(required_fields) and filled_required == len(required_fields),
            )
            repolish(progress)

    def refresh_current_navigation_status(self, *, dirty: bool = False) -> None:
        if self.event_nav is None:
            return
        section_index = self.current_section_index()
        section = self.current_section()
        if section is None or section_index < 0:
            return
        fields = [
            field
            for field in (getattr(section, "fields", []) or [])
            if field.editor != DESCRIPTION_EDITOR
        ]
        missing_required = any(
            bool(field.required) and not field_value_is_filled(self.current_field_value(field))
            for field in fields
        )
        has_value = any(field_value_is_filled(self.current_field_value(field)) for field in fields)
        status = "partial" if missing_required else "filled" if has_value else "empty"
        self.event_nav.set_section_status(section_index, status, dirty=dirty)

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
        state_label.setVisible(state in {"required_missing", "info"})
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
            widget.hide()
            widget.setParent(None)
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


def section_headings_equivalent(event_label: str, form_title: str) -> bool:
    def normalized(value: str) -> str:
        without_instance = re.sub(r"\s*#\s*\d+\s*$", "", str(value or "")).strip()
        return re.sub(r"\s+", " ", without_instance).casefold()

    return bool(normalized(event_label)) and normalized(event_label) == normalized(form_title)


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
