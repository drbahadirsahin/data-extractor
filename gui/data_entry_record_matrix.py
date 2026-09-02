from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gui.i18n import tr


MATRIX_STATUS_EMPTY = "empty"
MATRIX_STATUS_INCOMPLETE = "incomplete"
MATRIX_STATUS_UNVERIFIED = "unverified"
MATRIX_STATUS_PARTIAL = "partial"
MATRIX_STATUS_FILLED = "filled"


@dataclass(frozen=True)
class RecordMatrixTarget:
    section_index: int
    form_name: str
    form_title: str
    event_id: str
    event_label: str
    repeat_instrument: str
    instance: str
    status: str
    filled_fields: int
    total_fields: int
    missing_required_fields: int
    dirty: bool = False
    persisted: bool = False
    completion_status: str = ""

    @property
    def is_repeating_instrument(self) -> bool:
        return bool(self.repeat_instrument)


@dataclass
class RecordMatrixColumn:
    key: tuple[str, str]
    event_id: str
    event_instance: str
    label: str
    repeat_actions: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class RecordMatrixRow:
    form_name: str
    label: str


@dataclass
class RecordMatrixCell:
    form_name: str
    column_key: tuple[str, str]
    targets: list[RecordMatrixTarget] = field(default_factory=list)
    repeat_actions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RecordMatrixRepeatCard:
    form_name: str
    form_label: str
    event_id: str
    event_label: str
    targets: list[RecordMatrixTarget] = field(default_factory=list)
    repeat_actions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RecordMatrixModel:
    columns: list[RecordMatrixColumn]
    rows: list[RecordMatrixRow]
    cells: dict[tuple[str, tuple[str, str]], RecordMatrixCell]
    # Kept for callers that persisted the old matrix shape. Repeating
    # instruments now live entirely in their event/form cell, so this remains
    # empty and is no longer rendered as a second navigation area.
    repeat_cards: list[RecordMatrixRepeatCard] = field(default_factory=list)

    def cell(self, form_name: str, column_key: tuple[str, str]) -> RecordMatrixCell:
        return self.cells.setdefault(
            (form_name, column_key),
            RecordMatrixCell(form_name=form_name, column_key=column_key),
        )


def build_record_matrix(
    model: Any,
    repeat_actions: Iterable[dict[str, Any]] | None = None,
    *,
    language: str = "tr",
    event_order: Iterable[str] | None = None,
    form_order: Iterable[str] | None = None,
) -> RecordMatrixModel:
    """Build the REDCap-like event-column/instrument-row navigation model.

    A repeating event gets one column per event instance. A repeating instrument
    stays in its event column and exposes each instrument instance inside the
    corresponding cell. This mirrors REDCap's record home page instead of
    presenting all repeats as unrelated navigation entries.
    """

    actions = list(repeat_actions or [])
    sections = list(getattr(model, "sections", []) or [])
    section_targets = [target_for_section(section, index) for index, section in enumerate(sections)]

    columns: list[RecordMatrixColumn] = []
    columns_by_key: dict[tuple[str, str], RecordMatrixColumn] = {}
    rows: list[RecordMatrixRow] = []
    rows_by_name: dict[str, RecordMatrixRow] = {}
    cells: dict[tuple[str, tuple[str, str]], RecordMatrixCell] = {}

    for section_index, (section, target) in enumerate(zip(sections, section_targets)):
        form_name = str(getattr(section, "form_name", "") or "")
        if not form_name:
            continue
        form_title = str(getattr(section, "title", "") or form_name)
        if form_name not in rows_by_name:
            row = RecordMatrixRow(form_name=form_name, label=form_title)
            rows.append(row)
            rows_by_name[form_name] = row

        column_key = section_column_key(section)
        if column_key not in columns_by_key:
            column = RecordMatrixColumn(
                key=column_key,
                event_id=column_key[0],
                event_instance=column_key[1],
                label=section_column_label(
                    section,
                    language=language,
                ),
            )
            columns.append(column)
            columns_by_key[column_key] = column

        cell_key = (form_name, column_key)
        cell = cells.setdefault(
            cell_key,
            RecordMatrixCell(form_name=form_name, column_key=column_key),
        )
        # Repeat contexts are created only by an explicit user action. Keep an
        # empty draft visible so it can be reopened instead of silently
        # creating a second instance on the next + click.
        cell.targets.append(target)

    if not columns and rows:
        general_key = ("", "")
        columns.append(
            RecordMatrixColumn(
                key=general_key,
                event_id="",
                event_instance="",
                label=matrix_text("general", language),
            )
        )

    matrix = RecordMatrixModel(columns=columns, rows=rows, cells=cells)
    place_repeat_actions(matrix, actions)
    sort_matrix_axes(matrix, event_order=event_order, form_order=form_order)
    return matrix


def section_column_key(section: Any) -> tuple[str, str]:
    event_id = str(getattr(section, "event_id", "") or "")
    repeat_instrument = str(getattr(section, "repeat_instrument", "") or "")
    instance = str(getattr(section, "instance", "") or "")
    # REDCap repeat instrument instances live inside one event cell. Only an
    # event repetition creates another event column.
    return event_id, "" if repeat_instrument else instance


def section_column_label(section: Any, *, language: str = "tr", omit_instance: bool = False) -> str:
    label = str(getattr(section, "event_label", "") or "").strip()
    if label:
        return strip_instance_suffix(label) if omit_instance else label
    event_id = str(getattr(section, "event_id", "") or "").strip()
    if event_id:
        label = event_id.replace("_arm_", " arm ").replace("_", " ").strip().title()
        instance = section_column_key(section)[1]
        if omit_instance:
            return label
        return f"{label} #{instance}" if instance and f"#{instance}" not in label else label
    return matrix_text("general", language)


def strip_instance_suffix(label: str) -> str:
    return re.sub(r"\s*#\s*\d+\s*$", "", str(label or "")).strip()


def target_for_section(section: Any, section_index: int) -> RecordMatrixTarget:
    fields = [
        item
        for item in (getattr(section, "fields", []) or [])
        if str(getattr(item, "editor", "") or "") != "description"
    ]
    filled_fields = sum(1 for item in fields if matrix_value_is_filled(getattr(item, "value", "")))
    missing_required_fields = sum(
        1
        for item in fields
        if bool(getattr(item, "required", False)) and not matrix_value_is_filled(getattr(item, "value", ""))
    )
    completion_status = str(getattr(section, "completion_status", "") or "").strip()
    completion_present = bool(getattr(section, "completion_present", False))
    persisted = completion_present or any(
        bool(getattr(item, "present", False))
        or bool(getattr(item, "dirty", False))
        or matrix_value_is_filled(getattr(item, "value", ""))
        for item in fields
    )
    # The record map answers whether the form has the data the project marks
    # as mandatory. REDCap's optional ``<instrument>_complete`` field may be
    # stale or deliberately left at "Incomplete", so it must not override the
    # actual required-field state shown here.
    if missing_required_fields:
        status = MATRIX_STATUS_PARTIAL
    elif filled_fields == 0:
        status = MATRIX_STATUS_EMPTY
    else:
        status = MATRIX_STATUS_FILLED
    return RecordMatrixTarget(
        section_index=section_index,
        form_name=str(getattr(section, "form_name", "") or ""),
        form_title=str(getattr(section, "title", "") or getattr(section, "form_name", "") or ""),
        event_id=str(getattr(section, "event_id", "") or ""),
        event_label=str(getattr(section, "event_label", "") or ""),
        repeat_instrument=str(getattr(section, "repeat_instrument", "") or ""),
        instance=str(getattr(section, "instance", "") or ""),
        status=status,
        filled_fields=filled_fields,
        total_fields=len(fields),
        missing_required_fields=missing_required_fields,
        dirty=any(bool(getattr(item, "dirty", False)) for item in fields),
        persisted=persisted,
        completion_status=completion_status,
    )


def matrix_value_is_filled(value: Any) -> bool:
    if isinstance(value, (list, tuple, set)):
        return any(str(item or "").strip() for item in value)
    return bool(str(value or "").strip())


def place_repeat_actions(matrix: RecordMatrixModel, repeat_actions: Iterable[dict[str, Any]]) -> None:
    for action in repeat_actions:
        kind = str(action.get("kind") or "")
        event_id = str(action.get("event_id") or "")
        if kind == "event":
            form_labels = action.get("form_labels")
            if isinstance(form_labels, dict):
                for form_name, form_label in form_labels.items():
                    ensure_matrix_row(matrix, str(form_name), str(form_label or form_name))
            candidates = [column for column in matrix.columns if column.event_id == event_id]
            if not candidates:
                candidates = [
                    ensure_matrix_column(
                        matrix,
                        event_id,
                        "",
                        str(action.get("event_label") or humanize_event_id(event_id)),
                    )
                ]
            target_column = latest_column(candidates)
            target_column.repeat_actions.append(action)
            if isinstance(form_labels, dict):
                for form_name in form_labels:
                    matrix.cell(str(form_name), target_column.key)
            continue
        if kind != "form":
            continue
        form_name = str(action.get("form_name") or "")
        ensure_matrix_row(
            matrix,
            form_name,
            str(action.get("form_label") or form_name),
        )
        candidates = [
            column
            for column in matrix.columns
            if column.event_id == event_id
        ]
        if not candidates:
            candidates = [
                ensure_matrix_column(
                    matrix,
                    event_id,
                    "",
                    str(action.get("event_label") or humanize_event_id(event_id)),
                )
            ]
        matrix.cell(form_name, latest_column(candidates).key).repeat_actions.append(action)


def ensure_matrix_row(matrix: RecordMatrixModel, form_name: str, label: str) -> RecordMatrixRow:
    existing = next((row for row in matrix.rows if row.form_name == form_name), None)
    if existing is not None:
        return existing
    row = RecordMatrixRow(form_name=form_name, label=label or form_name)
    matrix.rows.append(row)
    return row


def ensure_matrix_column(
    matrix: RecordMatrixModel,
    event_id: str,
    event_instance: str,
    label: str,
) -> RecordMatrixColumn:
    key = (event_id, event_instance)
    existing = next((column for column in matrix.columns if column.key == key), None)
    if existing is not None:
        return existing
    column = RecordMatrixColumn(
        key=key,
        event_id=event_id,
        event_instance=event_instance,
        label=label or humanize_event_id(event_id),
    )
    matrix.columns.append(column)
    return column


def humanize_event_id(event_id: str) -> str:
    text = str(event_id or "").strip()
    if not text:
        return "Genel"
    return text.replace("_arm_", " arm ").replace("_", " ").strip().title()


def sort_matrix_axes(
    matrix: RecordMatrixModel,
    *,
    event_order: Iterable[str] | None = None,
    form_order: Iterable[str] | None = None,
) -> None:
    event_positions = {
        str(event_id): index
        for index, event_id in enumerate(event_order or ())
        if str(event_id)
    }
    if event_positions:
        original_columns = {id(column): index for index, column in enumerate(matrix.columns)}
        matrix.columns.sort(
            key=lambda column: (
                (0, event_positions[column.event_id], numeric_instance(column.event_instance), original_columns[id(column)])
                if column.event_id in event_positions
                else (1, original_columns[id(column)], 0, 0)
            )
        )

    form_positions = {
        str(form_name): index
        for index, form_name in enumerate(form_order or ())
        if str(form_name)
    }
    if form_positions:
        original_rows = {id(row): index for index, row in enumerate(matrix.rows)}
        matrix.rows.sort(
            key=lambda row: (
                form_positions.get(row.form_name, len(form_positions)),
                original_rows[id(row)],
            )
        )


def build_repeat_cards(matrix: RecordMatrixModel) -> list[RecordMatrixRepeatCard]:
    cards: list[RecordMatrixRepeatCard] = []
    rows_by_name = {row.form_name: row for row in matrix.rows}
    columns_by_key = {column.key: column for column in matrix.columns}
    for row in matrix.rows:
        for column in matrix.columns:
            cell = matrix.cells.get((row.form_name, column.key))
            if cell is None:
                continue
            targets = [target for target in cell.targets if target.is_repeating_instrument]
            actions = [
                action
                for action in cell.repeat_actions
                if str(action.get("kind") or "") == "form"
            ]
            if not targets and not actions:
                continue
            cards.append(
                RecordMatrixRepeatCard(
                    form_name=row.form_name,
                    form_label=rows_by_name[row.form_name].label,
                    event_id=column.event_id,
                    event_label=columns_by_key[column.key].label,
                    targets=targets,
                    repeat_actions=actions,
                )
            )
    return cards


def latest_column(columns: list[RecordMatrixColumn]) -> RecordMatrixColumn:
    return max(
        enumerate(columns),
        key=lambda item: (numeric_instance(item[1].event_instance), item[0]),
    )[1]


def numeric_instance(value: Any) -> int:
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0


def matrix_text(key: str, language: str) -> str:
    values = {
        "tr": {
            "corner": "Form / olay",
            "general": "Genel",
            "empty": "Veri yok",
            "incomplete": "Eksik",
            "unverified": "Doğrulanmamış",
            "partial": "Eksik zorunlu alan",
            "filled": "Veri girilmiş",
            "open": "Aç",
            "repeat_title": "Tekrarlayan formlar",
            "no_instances": "Henüz örnek yok",
        },
        "en": {
            "corner": "Form / event",
            "general": "General",
            "empty": "No data",
            "incomplete": "Incomplete",
            "unverified": "Unverified",
            "partial": "Required field missing",
            "filled": "Data entered",
            "open": "Open",
            "repeat_title": "Repeating instruments",
            "no_instances": "No instances yet",
        },
    }
    language_key = "en" if str(language).lower().startswith("en") else "tr"
    return values[language_key].get(key, key)


class DataEntryRecordMatrix(QWidget):
    """Compact record-map navigator with REDCap-style contextual add actions."""

    targetActivated = Signal(int)
    repeatActionRequested = Signal(object)

    def __init__(self, *, language: str = "tr", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.language = language
        self.matrix_model = RecordMatrixModel(columns=[], rows=[], cells={})
        self.target_buttons: dict[int, QToolButton] = {}
        self._target_button_instances: dict[int, list[QToolButton]] = {}
        self.repeat_buttons: list[tuple[dict[str, Any], QToolButton]] = []
        self._selected_section_index = -1
        self.setObjectName("DataEntryRecordMatrix")
        self.setStyleSheet(RECORD_MATRIX_STYLE)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("DataEntryRecordMatrixScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root_layout.addWidget(self.scroll)

        self.body = QWidget()
        self.body.setObjectName("DataEntryRecordMatrixBody")
        self.grid = QGridLayout(self.body)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(0)
        self.grid.setVerticalSpacing(0)
        self.scroll.setWidget(self.body)

    def set_record_model(
        self,
        model: Any,
        *,
        repeat_actions: Iterable[dict[str, Any]] | None = None,
        event_order: Iterable[str] | None = None,
        form_order: Iterable[str] | None = None,
    ) -> None:
        self.set_matrix_model(
            build_record_matrix(
                model,
                repeat_actions,
                language=self.language,
                event_order=event_order,
                form_order=form_order,
            )
        )

    def set_matrix_model(self, matrix_model: RecordMatrixModel) -> None:
        self.matrix_model = matrix_model
        self.target_buttons = {}
        self._target_button_instances = {}
        self.repeat_buttons = []
        clear_grid(self.grid)
        self.render_matrix()

    def render_matrix(self) -> None:
        corner = QLabel(matrix_text("corner", self.language))
        corner.setObjectName("DataEntryRecordMatrixCorner")
        corner.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.grid.addWidget(corner, 0, 0)
        self.grid.setColumnMinimumWidth(0, 190)

        for column_index, column in enumerate(self.matrix_model.columns, start=1):
            self.grid.addWidget(self.build_column_header(column), 0, column_index)
            self.grid.setColumnMinimumWidth(column_index, 158)
            self.grid.setColumnStretch(column_index, 1)

        for row_index, row in enumerate(self.matrix_model.rows, start=1):
            label = QLabel(row.label)
            label.setObjectName("DataEntryRecordMatrixRowLabel")
            label.setWordWrap(True)
            label.setProperty("form_name", row.form_name)
            self.grid.addWidget(label, row_index, 0)
            for column_index, column in enumerate(self.matrix_model.columns, start=1):
                cell = self.matrix_model.cells.get((row.form_name, column.key))
                self.grid.addWidget(self.build_cell(cell), row_index, column_index)

        minimum_width = 190 + max(1, len(self.matrix_model.columns)) * 158
        self.body.setMinimumWidth(minimum_width)
        self.body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.set_selected_section(self._selected_section_index)

    def build_column_header(self, column: RecordMatrixColumn) -> QWidget:
        frame = QFrame()
        frame.setObjectName("DataEntryRecordMatrixColumnHeader")
        frame.setProperty("event_id", column.event_id)
        frame.setProperty("event_instance", column.event_instance)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(9, 8, 9, 8)
        layout.setSpacing(6)
        label = QLabel(column.label)
        label.setObjectName("DataEntryRecordMatrixColumnLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label, 1)
        for action in column.repeat_actions:
            layout.addWidget(
                self.build_repeat_button(
                    action,
                    event_label=strip_instance_suffix(column.label),
                )
            )
        return frame

    def build_cell(self, cell: RecordMatrixCell | None) -> QWidget:
        frame = QFrame()
        frame.setObjectName("DataEntryRecordMatrixCell")
        if cell is not None:
            frame.setProperty("form_name", cell.form_name)
            frame.setProperty("event_id", cell.column_key[0])
            frame.setProperty("event_instance", cell.column_key[1])
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(6)

        if cell is None or (not cell.targets and not cell.repeat_actions):
            unavailable = QLabel("—")
            unavailable.setObjectName("DataEntryRecordMatrixUnavailable")
            unavailable.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(unavailable, 1)
            return frame

        target_row = QHBoxLayout()
        target_row.setContentsMargins(0, 0, 0, 0)
        target_row.setSpacing(5)
        target_row.addStretch(1)
        for target in cell.targets:
            target_row.addWidget(self.build_target_button(target))
        for action in cell.repeat_actions:
            if str(action.get("kind") or "") == "form":
                target_row.addWidget(self.build_repeat_button(action, compact=True))
        target_row.addStretch(1)
        layout.addLayout(target_row)
        return frame

    def build_target_button(self, target: RecordMatrixTarget) -> QToolButton:
        button = QToolButton()
        button.setObjectName("DataEntryRecordMatrixTarget")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("section_index", target.section_index)
        button.setProperty("matrix_status", target.status)
        button.setProperty("repeat_instance", target.instance)
        button.setProperty("dirty", target.dirty)
        button.setText(target_button_text(target, self.language))
        tooltip = target_tooltip(target, self.language)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.clicked.connect(
            lambda _checked=False, index=target.section_index: self.activate_target(index)
        )
        self.target_buttons.setdefault(target.section_index, button)
        self._target_button_instances.setdefault(target.section_index, []).append(button)
        return button

    def build_repeat_button(
        self,
        action: dict[str, Any],
        *,
        compact: bool = False,
        event_label: str = "",
    ) -> QToolButton:
        button = QToolButton()
        button.setObjectName("DataEntryRecordMatrixAdd")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        kind = str(action.get("kind") or "")
        button.setProperty("repeat_kind", kind)
        button.setProperty("compact", compact)
        if kind == "event":
            fallback_event = humanize_event_id(action.get("event_id"))
            display_event = strip_instance_suffix(
                str(action.get("event_label") or event_label or fallback_event)
            )
            full_text = tr(
                "data_entry_repeat_event_button",
                self.language,
                event=display_event,
            )
        else:
            full_text = tr("data_entry_repeat_form_button", self.language)
        button.setText("+" if compact else full_text)
        button.setToolTip(str(action.get("label") or full_text))
        button.setAccessibleName(button.toolTip())
        button.clicked.connect(
            lambda _checked=False, option=action: self.repeatActionRequested.emit(option)
        )
        self.repeat_buttons.append((action, button))
        return button

    def activate_target(self, section_index: int) -> None:
        self.set_selected_section(section_index)
        self.targetActivated.emit(section_index)

    def set_selected_section(self, section_index: int) -> None:
        self._selected_section_index = int(section_index)
        for index, buttons in self._target_button_instances.items():
            for button in buttons:
                button.setProperty("active", index == self._selected_section_index)
                repolish(button)


def target_button_text(target: RecordMatrixTarget, language: str) -> str:
    marker = "●"
    if target.is_repeating_instrument and target.instance:
        return f"{marker}  #{target.instance}"
    return marker


def target_tooltip(target: RecordMatrixTarget, language: str) -> str:
    status = matrix_text(target.status, language)
    instance = f" #{target.instance}" if target.is_repeating_instrument and target.instance else ""
    count = f"{target.filled_fields}/{target.total_fields}"
    return f"{target.form_title}{instance}\n{status} · {count}"


def clear_grid(layout: QGridLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
            continue
        child_layout = item.layout()
        if child_layout is not None:
            clear_layout(child_layout)


def clear_layout(layout: Any) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


RECORD_MATRIX_STYLE = """
QWidget#DataEntryRecordMatrix {
    background: #f8fafc;
}

QScrollArea#DataEntryRecordMatrixScroll,
QWidget#DataEntryRecordMatrixBody {
    background: transparent;
    border: none;
}

QLabel#DataEntryRecordMatrixCorner,
QFrame#DataEntryRecordMatrixColumnHeader,
QLabel#DataEntryRecordMatrixRowLabel,
QFrame#DataEntryRecordMatrixCell {
    background: #ffffff;
    border-right: 1px solid #dbe5ea;
    border-bottom: 1px solid #dbe5ea;
}

QLabel#DataEntryRecordMatrixCorner {
    color: #475569;
    font-size: 11px;
    font-weight: 700;
    padding: 10px 12px;
    border-left: 1px solid #dbe5ea;
    border-top: 1px solid #dbe5ea;
    border-top-left-radius: 8px;
}

QFrame#DataEntryRecordMatrixColumnHeader {
    background: #f5fbfa;
    border-top: 1px solid #dbe5ea;
}

QLabel#DataEntryRecordMatrixColumnLabel {
    color: #0f3f46;
    font-size: 11px;
    font-weight: 700;
}

QLabel#DataEntryRecordMatrixRowLabel {
    color: #0f172a;
    font-size: 12px;
    font-weight: 600;
    padding: 10px 12px;
    border-left: 1px solid #dbe5ea;
}

QFrame#DataEntryRecordMatrixCell {
    min-height: 48px;
}

QLabel#DataEntryRecordMatrixUnavailable {
    color: #cbd5e1;
    font-size: 13px;
}

QToolButton#DataEntryRecordMatrixTarget {
    background: transparent;
    color: #94a3b8;
    border: 1px solid transparent;
    border-radius: 14px;
    min-width: 26px;
    min-height: 26px;
    padding: 1px 6px;
    font-size: 12px;
    font-weight: 700;
}

QToolButton#DataEntryRecordMatrixTarget[matrix_status="partial"] {
    color: #dc2626;
}

QToolButton#DataEntryRecordMatrixTarget[matrix_status="incomplete"] {
    color: #dc2626;
}

QToolButton#DataEntryRecordMatrixTarget[matrix_status="unverified"] {
    color: #d69a16;
}

QToolButton#DataEntryRecordMatrixTarget[matrix_status="filled"] {
    color: #0d9488;
}

QToolButton#DataEntryRecordMatrixTarget[dirty="true"] {
    background: #fff7ed;
    border-color: #fed7aa;
}

QToolButton#DataEntryRecordMatrixTarget[active="true"] {
    background: #ccfbf1;
    border-color: #5eead4;
    color: #0f766e;
}

QToolButton#DataEntryRecordMatrixTarget:hover {
    background: #e6fffb;
    border-color: #99f6e4;
}

QToolButton#DataEntryRecordMatrixAdd {
    background: #ffffff;
    color: #0f766e;
    border: 1px solid #99d8d1;
    border-radius: 5px;
    min-height: 24px;
    padding: 2px 7px;
    font-size: 10px;
    font-weight: 700;
}

QToolButton#DataEntryRecordMatrixAdd:hover {
    background: #e6fffb;
    border-color: #14b8a6;
}

QToolButton#DataEntryRecordMatrixAdd[compact="true"] {
    border-radius: 13px;
    min-width: 26px;
    max-width: 26px;
    min-height: 26px;
    max-height: 26px;
    padding: 0;
    font-size: 16px;
}
"""
