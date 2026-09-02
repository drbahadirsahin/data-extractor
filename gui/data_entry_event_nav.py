from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class EventNavFormButton(QFrame):
    """Keyboard-accessible form target whose label can wrap at narrow widths."""

    clicked = Signal()

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = str(text or "")
        self.setObjectName("DataEntryEventNavFormButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 5, 6, 5)
        layout.setSpacing(0)
        self.label = QLabel(self._text)
        self.label.setObjectName("DataEntryEventNavFormButtonLabel")
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

    def setText(self, text: str) -> None:
        self._text = str(text or "")
        self.label.setText(self._text)

    def text(self) -> str:
        return self._text

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


@dataclass(frozen=True)
class EventNavTarget:
    section_index: int
    form_name: str
    form_title: str
    event_id: str
    event_label: str
    event_instance: str
    repeat_instrument: str
    instance: str
    status: str
    dirty: bool = False

    @property
    def is_repeating_form(self) -> bool:
        return bool(self.repeat_instrument)


@dataclass
class EventNavForm:
    form_name: str
    label: str
    targets: list[EventNavTarget] = field(default_factory=list)
    repeat_actions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EventNavInstance:
    instance: str
    forms: list[EventNavForm] = field(default_factory=list)

    def form(self, form_name: str, label: str = "") -> EventNavForm:
        existing = next((item for item in self.forms if item.form_name == form_name), None)
        if existing is not None:
            return existing
        item = EventNavForm(form_name=form_name, label=label or form_name)
        self.forms.append(item)
        return item


@dataclass
class EventNavGroup:
    key: str
    event_id: str
    label: str
    instances: list[EventNavInstance] = field(default_factory=list)
    repeat_actions: list[dict[str, Any]] = field(default_factory=list)

    def instance(self, instance: str, *, create: bool = True) -> EventNavInstance | None:
        instance_key = str(instance or "")
        existing = next((item for item in self.instances if item.instance == instance_key), None)
        if existing is not None or not create:
            return existing
        item = EventNavInstance(instance=instance_key)
        self.instances.append(item)
        return item

    @property
    def is_repeating_event(self) -> bool:
        return any(str(action.get("kind") or "") == "event" for action in self.repeat_actions) or any(
            item.instance for item in self.instances
        )


@dataclass
class EventNavModel:
    groups: list[EventNavGroup] = field(default_factory=list)

    def group(self, event_id: str) -> EventNavGroup | None:
        event_key = str(event_id or "")
        return next((item for item in self.groups if item.event_id == event_key), None)


def build_event_nav_model(
    model: Any,
    repeat_actions: Iterable[dict[str, Any]] | None = None,
    *,
    language: str = "tr",
    event_order: Iterable[str] | None = None,
    form_order: Iterable[str] | None = None,
) -> EventNavModel:
    """Build one collapsible group per REDCap event.

    Repeating events become compact instance selectors inside their one event
    group. Repeating instruments stay as numbered targets on their form row.
    Neither type of repeat is synthesized: a chip appears only for a section
    that actually exists in ``FormRenderModel.sections``.
    """

    nav_model = EventNavModel()
    for section_index, section in enumerate(getattr(model, "sections", []) or []):
        form_name = str(getattr(section, "form_name", "") or "").strip()
        if not form_name:
            continue
        event_id = str(getattr(section, "event_id", "") or "")
        group = nav_model.group(event_id)
        if group is None:
            group = EventNavGroup(
                key=event_id,
                event_id=event_id,
                label=event_group_label(section, language=language),
            )
            nav_model.groups.append(group)
        event_instance = section_event_instance(section)
        instance = group.instance(event_instance)
        assert instance is not None
        form = instance.form(
            form_name,
            str(getattr(section, "title", "") or form_name),
        )
        form.targets.append(target_for_section(section, section_index))

    for action in repeat_actions or ():
        place_repeat_action(nav_model, action, language=language)

    sort_event_nav(nav_model, event_order=event_order, form_order=form_order)
    return nav_model


def section_event_instance(section: Any) -> str:
    # REDCap uses the same ``instance`` slot for event and instrument repeats.
    # A repeat_instrument value tells us the instance belongs to the form, not
    # to the surrounding event.
    if str(getattr(section, "repeat_instrument", "") or ""):
        return ""
    return str(getattr(section, "instance", "") or "")


def event_group_label(section: Any, *, language: str) -> str:
    event_label = strip_instance_suffix(
        str(getattr(section, "event_label", "") or "").strip()
    )
    if event_label:
        return event_label
    event_id = str(getattr(section, "event_id", "") or "").strip()
    if not event_id:
        return event_nav_text("general", language)
    return humanize_event_id(event_id)


def target_for_section(section: Any, section_index: int) -> EventNavTarget:
    fields = [
        item
        for item in (getattr(section, "fields", []) or [])
        if str(getattr(item, "editor", "") or "") != "description"
    ]
    filled = sum(1 for item in fields if value_is_filled(getattr(item, "value", "")))
    missing_required = any(
        bool(getattr(item, "required", False)) and not value_is_filled(getattr(item, "value", ""))
        for item in fields
    )
    status = "partial" if missing_required else "filled" if filled else "empty"
    repeat_instrument = str(getattr(section, "repeat_instrument", "") or "")
    return EventNavTarget(
        section_index=section_index,
        form_name=str(getattr(section, "form_name", "") or ""),
        form_title=str(getattr(section, "title", "") or getattr(section, "form_name", "") or ""),
        event_id=str(getattr(section, "event_id", "") or ""),
        event_label=str(getattr(section, "event_label", "") or ""),
        event_instance=section_event_instance(section),
        repeat_instrument=repeat_instrument,
        instance=str(getattr(section, "instance", "") or ""),
        status=status,
        dirty=any(bool(getattr(item, "dirty", False)) for item in fields),
    )


def value_is_filled(value: Any) -> bool:
    if isinstance(value, (list, tuple, set)):
        return any(str(item or "").strip() for item in value)
    return bool(str(value or "").strip())


def place_repeat_action(nav_model: EventNavModel, action: dict[str, Any], *, language: str) -> None:
    kind = str(action.get("kind") or "")
    if kind not in {"event", "form"}:
        return
    event_id = str(action.get("event_id") or "")
    group = nav_model.group(event_id)
    if group is None:
        label = strip_instance_suffix(str(action.get("event_label") or "").strip())
        group = EventNavGroup(
            key=event_id,
            event_id=event_id,
            label=label or (humanize_event_id(event_id) if event_id else event_nav_text("general", language)),
        )
        nav_model.groups.append(group)

    if kind == "event":
        # An action alone proves the event can repeat, but not that instance #1
        # exists. Keep the group action-only until the user actually adds one.
        group.repeat_actions.append(action)
        return

    form_name = str(action.get("form_name") or "")
    if not form_name:
        return
    instance = latest_event_instance(group.instances)
    if instance is None:
        # A repeating form in a non-repeating/unspecified event still needs a
        # home for its inline +. This is an unnumbered event context, not a
        # phantom event instance.
        instance = group.instance("")
    assert instance is not None
    form = instance.form(form_name, str(action.get("form_label") or form_name))
    form.repeat_actions.append(action)


def latest_event_instance(instances: list[EventNavInstance]) -> EventNavInstance | None:
    if not instances:
        return None
    return max(
        enumerate(instances),
        key=lambda item: (numeric_instance(item[1].instance), item[0]),
    )[1]


def sort_event_nav(
    nav_model: EventNavModel,
    *,
    event_order: Iterable[str] | None,
    form_order: Iterable[str] | None,
) -> None:
    event_positions = {
        str(event_id): index
        for index, event_id in enumerate(event_order or ())
        if str(event_id)
    }
    if event_positions:
        original_groups = {id(group): index for index, group in enumerate(nav_model.groups)}
        nav_model.groups.sort(
            key=lambda group: (
                event_positions.get(group.event_id, len(event_positions)),
                original_groups[id(group)],
            )
        )

    form_positions = {
        str(form_name): index
        for index, form_name in enumerate(form_order or ())
        if str(form_name)
    }
    if form_positions:
        for group in nav_model.groups:
            for instance in group.instances:
                original_forms = {id(form): index for index, form in enumerate(instance.forms)}
                instance.forms.sort(
                    key=lambda form: (
                        form_positions.get(form.form_name, len(form_positions)),
                        original_forms[id(form)],
                    )
                )


def numeric_instance(value: Any) -> int:
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0


def humanize_event_id(event_id: Any) -> str:
    text = str(event_id or "").strip()
    return text.replace("_arm_", " arm ").replace("_", " ").strip().title()


def strip_instance_suffix(label: str) -> str:
    return re.sub(r"\s*#\s*\d+\s*$", "", str(label or "")).strip()


def event_nav_text(key: str, language: str, **values: str) -> str:
    texts = {
        "tr": {
            "general": "Genel formlar",
            "toggle": "{event} bölümünü aç veya kapat",
            "event_add": "Yeni {event} kaydı ekle",
            "event_instance": "{event} #{instance} kaydını göster",
            "open": "Aç",
            "form_open": "{form} formunu aç",
            "instance_open": "{form} #{instance} tekrarını aç",
            "form_add": "{form} için yeni tekrar ekle",
        },
        "en": {
            "general": "General forms",
            "toggle": "Expand or collapse {event}",
            "event_add": "Add another {event} record",
            "event_instance": "Show {event} record #{instance}",
            "open": "Open",
            "form_open": "Open {form}",
            "instance_open": "Open {form} instance #{instance}",
            "form_add": "Add another {form} instance",
        },
    }
    language_key = "en" if str(language).lower().startswith("en") else "tr"
    return texts[language_key].get(key, key).format(**values)


class DataEntryEventNav(QWidget):
    """One collapsible group per event with contextual repeat controls."""

    targetActivated = Signal(int)
    repeatActionRequested = Signal(object)

    def __init__(self, *, language: str = "tr", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.language = language
        self.nav_model = EventNavModel()
        self._selected_section_index = -1
        self._expanded_by_event: dict[str, bool] = {}
        self._selected_instance_by_event: dict[str, str] = {}
        self._section_context: dict[int, tuple[str, str]] = {}
        self.group_headers: dict[str, QToolButton] = {}
        self.group_contents: dict[str, QFrame] = {}
        self.instance_buttons: dict[tuple[str, str], QToolButton] = {}
        self.instance_bodies: dict[tuple[str, str], QFrame] = {}
        self.form_rows: dict[tuple[str, str, str], QFrame] = {}
        self.target_buttons: dict[int, QToolButton | EventNavFormButton] = {}
        self.status_labels: dict[int, QLabel] = {}
        self.repeat_buttons: list[tuple[dict[str, Any], QToolButton]] = []

        self.setObjectName("DataEntryEventNav")
        self.setStyleSheet(EVENT_NAV_STYLE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("DataEntryEventNavScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(self.scroll)

        self.body = QWidget()
        self.body.setObjectName("DataEntryEventNavBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(8)
        self.body_layout.addStretch(1)
        self.scroll.setWidget(self.body)

    def set_record_model(
        self,
        model: Any,
        *,
        repeat_actions: Iterable[dict[str, Any]] | None = None,
        event_order: Iterable[str] | None = None,
        form_order: Iterable[str] | None = None,
    ) -> None:
        self.set_nav_model(
            build_event_nav_model(
                model,
                repeat_actions,
                language=self.language,
                event_order=event_order,
                form_order=form_order,
            )
        )

    def set_nav_model(self, nav_model: EventNavModel) -> None:
        old_scroll = self.scroll_state()
        self.nav_model = nav_model
        self.group_headers = {}
        self.group_contents = {}
        self.instance_buttons = {}
        self.instance_bodies = {}
        self.form_rows = {}
        self.target_buttons = {}
        self.status_labels = {}
        self.repeat_buttons = []
        self._section_context = {}
        clear_layout(self.body_layout)
        for group in nav_model.groups:
            self.body_layout.addWidget(self.build_group(group))
        self.body_layout.addStretch(1)
        self.set_selected_section(self._selected_section_index)
        QTimer.singleShot(0, lambda state=old_scroll: self.set_scroll_state(state))

    def build_group(self, group: EventNavGroup) -> QFrame:
        frame = QFrame()
        frame.setObjectName("DataEntryEventNavGroup")
        frame.setProperty("event_id", group.event_id)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header_frame = QFrame()
        header_frame.setObjectName("DataEntryEventNavHeaderFrame")
        header_frame.setProperty("event_id", group.event_id)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(4, 3, 4, 3)
        header_layout.setSpacing(4)

        header = QToolButton()
        header.setObjectName("DataEntryEventNavHeader")
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header.setProperty("event_id", group.event_id)
        header.setToolTip(event_nav_text("toggle", self.language, event=group.label))
        header.setAccessibleName(header.toolTip())
        header.clicked.connect(
            lambda _checked=False, key=group.key: self.set_group_expanded(
                key,
                not self._expanded_by_event.get(key, True),
            )
        )
        self.group_headers[group.key] = header
        header_layout.addWidget(header, 1)

        for action in group.repeat_actions:
            if str(action.get("kind") or "") == "event":
                header_layout.addWidget(self.build_repeat_button(action, group=group))
        layout.addWidget(header_frame)

        content = QFrame()
        content.setObjectName("DataEntryEventNavContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 4, 4, 7)
        content_layout.setSpacing(4)

        numbered_instances = [item for item in group.instances if item.instance]
        if numbered_instances:
            chips = QFrame()
            chips.setObjectName("DataEntryEventNavEventInstances")
            chips_layout = QHBoxLayout(chips)
            chips_layout.setContentsMargins(6, 2, 5, 3)
            chips_layout.setSpacing(5)
            for instance in numbered_instances:
                chips_layout.addWidget(self.build_event_instance_button(group, instance))
            chips_layout.addStretch(1)
            content_layout.addWidget(chips)

        for instance in group.instances:
            body = QFrame()
            body.setObjectName("DataEntryEventNavInstanceBody")
            body.setProperty("event_id", group.event_id)
            body.setProperty("event_instance", instance.instance)
            body_layout = QVBoxLayout(body)
            body_layout.setContentsMargins(0, 0, 0, 0)
            body_layout.setSpacing(3)
            for form in instance.forms:
                body_layout.addWidget(self.build_form_row(group, instance, form))
            self.instance_bodies[(group.event_id, instance.instance)] = body
            content_layout.addWidget(body)

        self.group_contents[group.key] = content
        layout.addWidget(content)
        self.set_group_expanded(group.key, self._expanded_by_event.get(group.key, True))
        self.apply_instance_selection(group.event_id)
        return frame

    def build_event_instance_button(
        self,
        group: EventNavGroup,
        instance: EventNavInstance,
    ) -> QToolButton:
        button = QToolButton()
        button.setObjectName("DataEntryEventNavEventInstance")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setText(f"#{instance.instance}")
        button.setProperty("event_id", group.event_id)
        button.setProperty("event_instance", instance.instance)
        accessible = event_nav_text(
            "event_instance",
            self.language,
            event=group.label,
            instance=instance.instance,
        )
        button.setToolTip(accessible)
        button.setAccessibleName(accessible)
        button.clicked.connect(
            lambda _checked=False, event_id=group.event_id, value=instance.instance: self.select_event_instance(
                event_id,
                value,
            )
        )
        self.instance_buttons[(group.event_id, instance.instance)] = button
        return button

    def build_form_row(
        self,
        group: EventNavGroup,
        instance: EventNavInstance,
        form: EventNavForm,
    ) -> QFrame:
        row = QFrame()
        row.setObjectName("DataEntryEventNavFormRow")
        row.setProperty("event_id", group.event_id)
        row.setProperty("event_instance", instance.instance)
        row.setProperty("form_name", form.form_name)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 4, 5, 4)
        layout.setSpacing(5)

        repeating_targets = [target for target in form.targets if target.is_repeating_form]
        plain_targets = [target for target in form.targets if not target.is_repeating_form]
        if repeating_targets:
            label = self.build_form_label(form.label)
            layout.addWidget(label, 1)
            for target in repeating_targets:
                layout.addWidget(self.build_target_button(target, compact=True))
        elif plain_targets:
            target = plain_targets[0]
            layout.addWidget(self.build_status_label(target), 0)
            button = self.build_target_button(target, compact=False)
            button.setText(form.label)
            layout.addWidget(button, 1)
            for extra_target in plain_targets[1:]:
                layout.addWidget(self.build_target_button(extra_target, compact=True))
        else:
            layout.addWidget(self.build_form_label(form.label), 1)

        for action in form.repeat_actions:
            if str(action.get("kind") or "") == "form":
                layout.addWidget(self.build_repeat_button(action, form=form))

        self.form_rows[(group.event_id, instance.instance, form.form_name)] = row
        return row

    def build_status_label(self, target: EventNavTarget) -> QLabel:
        label = QLabel({"filled": "✓", "partial": "!", "empty": "○"}.get(target.status, "○"))
        label.setObjectName("DataEntryEventNavStatus")
        label.setProperty("nav_status", target.status)
        label.setProperty("dirty", target.dirty)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setFixedWidth(16)
        self.status_labels[target.section_index] = label
        return label

    def build_form_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("DataEntryEventNavFormLabel")
        label.setWordWrap(True)
        label.setToolTip(text)
        label.setAccessibleName(text)
        return label

    def build_target_button(
        self,
        target: EventNavTarget,
        *,
        compact: bool,
    ) -> QToolButton | EventNavFormButton:
        button = QToolButton() if compact else EventNavFormButton()
        button.setObjectName(
            "DataEntryEventNavInstance" if compact else "DataEntryEventNavFormButton"
        )
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("section_index", target.section_index)
        button.setProperty("form_name", target.form_name)
        button.setProperty("repeat_instance", target.instance if target.is_repeating_form else "")
        button.setProperty("nav_status", target.status)
        button.setProperty("dirty", target.dirty)
        if compact:
            button.setText(f"#{target.instance}" if target.instance else event_nav_text("open", self.language))
            accessible = event_nav_text(
                "instance_open",
                self.language,
                form=target.form_title,
                instance=target.instance or "1",
            )
        else:
            accessible = event_nav_text("form_open", self.language, form=target.form_title)
        button.setToolTip(accessible)
        button.setAccessibleName(accessible)
        button.clicked.connect(
            lambda _checked=False, index=target.section_index: self.activate_target(index)
        )
        self.target_buttons[target.section_index] = button
        self._section_context[target.section_index] = (target.event_id, target.event_instance)
        return button

    def build_repeat_button(
        self,
        action: dict[str, Any],
        *,
        group: EventNavGroup | None = None,
        form: EventNavForm | None = None,
    ) -> QToolButton:
        button = QToolButton()
        button.setObjectName("DataEntryEventNavAdd")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        kind = str(action.get("kind") or "")
        button.setProperty("repeat_kind", kind)
        button.setText("+")
        if kind == "event" and group is not None:
            event = strip_instance_suffix(
                str(action.get("event_label") or group.label or humanize_event_id(group.event_id))
            )
            tooltip = event_nav_text("event_add", self.language, event=event)
        else:
            form_label = form.label if form is not None else str(action.get("form_label") or "form")
            tooltip = event_nav_text("form_add", self.language, form=form_label)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.clicked.connect(
            lambda _checked=False, option=action: self.repeatActionRequested.emit(option)
        )
        self.repeat_buttons.append((action, button))
        return button

    def set_group_expanded(self, event_id: str, expanded: bool) -> None:
        event_key = str(event_id or "")
        content = self.group_contents.get(event_key)
        header = self.group_headers.get(event_key)
        if content is None or header is None:
            return
        expanded = bool(expanded)
        self._expanded_by_event[event_key] = expanded
        content.setVisible(expanded)
        header.setProperty("expanded", expanded)
        group = self.nav_model.group(event_key)
        label = group.label if group is not None else ""
        header.setText(escape_button_text(f"{'▾' if expanded else '▸'}  {label}"))
        repolish(header)

    def select_event_instance(self, event_id: str, instance: str) -> None:
        event_key = str(event_id or "")
        instance_key = str(instance or "")
        group = self.nav_model.group(event_key)
        if group is None or group.instance(instance_key, create=False) is None:
            return
        self._selected_instance_by_event[event_key] = instance_key
        self.set_group_expanded(event_key, True)
        self.apply_instance_selection(event_key)

    def apply_instance_selection(self, event_id: str) -> None:
        event_key = str(event_id or "")
        group = self.nav_model.group(event_key)
        if group is None or not group.instances:
            return
        available = [item.instance for item in group.instances]
        selected = self._selected_instance_by_event.get(event_key)
        if selected not in available:
            selected = available[0]
            self._selected_instance_by_event[event_key] = selected
        for instance in available:
            active = instance == selected
            body = self.instance_bodies.get((event_key, instance))
            if body is not None:
                body.setVisible(active)
            button = self.instance_buttons.get((event_key, instance))
            if button is not None:
                button.setProperty("active", active)
                repolish(button)

    def activate_target(self, section_index: int) -> None:
        self.set_selected_section(section_index)
        self.targetActivated.emit(section_index)

    def set_selected_section(self, section_index: int) -> None:
        self._selected_section_index = int(section_index)
        context = self._section_context.get(self._selected_section_index)
        if context is not None:
            event_id, event_instance = context
            self._selected_instance_by_event[event_id] = event_instance
            self.set_group_expanded(event_id, True)
            self.apply_instance_selection(event_id)
        for index, button in self.target_buttons.items():
            button.setProperty("active", index == self._selected_section_index)
            repolish(button)
        for (event_id, event_instance, form_name), row in self.form_rows.items():
            active = self._selected_row_matches(event_id, event_instance, form_name)
            row.setProperty("active", active)
            repolish(row)

    def set_section_status(self, section_index: int, status: str, *, dirty: bool = False) -> None:
        status = status if status in {"empty", "partial", "filled"} else "empty"
        button = self.target_buttons.get(int(section_index))
        if button is not None:
            button.setProperty("nav_status", status)
            button.setProperty("dirty", bool(dirty))
            repolish(button)
        label = self.status_labels.get(int(section_index))
        if label is not None:
            label.setText({"filled": "✓", "partial": "!", "empty": "○"}[status])
            label.setProperty("nav_status", status)
            label.setProperty("dirty", bool(dirty))
            repolish(label)

    def _selected_row_matches(self, event_id: str, event_instance: str, form_name: str) -> bool:
        if self._selected_section_index < 0:
            return False
        group = self.nav_model.group(event_id)
        if group is None:
            return False
        instance = group.instance(event_instance, create=False)
        if instance is None:
            return False
        form = next((item for item in instance.forms if item.form_name == form_name), None)
        return form is not None and any(
            target.section_index == self._selected_section_index for target in form.targets
        )

    # State API used by the containing form when its model is rebuilt.
    def expanded_keys(self) -> set[str]:
        return {
            group.key
            for group in self.nav_model.groups
            if self._expanded_by_event.get(group.key, True)
        }

    def set_expanded_keys(self, keys: Iterable[str]) -> None:
        expanded = {str(key or "") for key in keys}
        for group in self.nav_model.groups:
            self.set_group_expanded(group.key, group.key in expanded)

    def selected_instances(self) -> dict[str, str]:
        return {
            group.event_id: self._selected_instance_by_event[group.event_id]
            for group in self.nav_model.groups
            if group.event_id in self._selected_instance_by_event
        }

    def set_selected_instances(self, values: Mapping[str, str]) -> None:
        for event_id, instance in values.items():
            event_key = str(event_id or "")
            instance_key = str(instance or "")
            group = self.nav_model.group(event_key)
            if group is None or group.instance(instance_key, create=False) is None:
                continue
            self._selected_instance_by_event[event_key] = instance_key
            self.apply_instance_selection(event_key)

    def scroll_state(self) -> dict[str, int]:
        return {
            "vertical": self.scroll.verticalScrollBar().value(),
            "horizontal": self.scroll.horizontalScrollBar().value(),
        }

    def set_scroll_state(self, state: Mapping[str, int] | int) -> None:
        if isinstance(state, Mapping):
            vertical = int(state.get("vertical", 0))
            horizontal = int(state.get("horizontal", 0))
        else:
            vertical = int(state)
            horizontal = 0
        self.scroll.verticalScrollBar().setValue(vertical)
        self.scroll.horizontalScrollBar().setValue(horizontal)

    def navigation_state(self) -> dict[str, Any]:
        return {
            "expanded_keys": sorted(self.expanded_keys()),
            "selected_instances": self.selected_instances(),
            "scroll": self.scroll_state(),
        }

    def restore_navigation_state(self, state: Mapping[str, Any]) -> None:
        self.set_expanded_keys(state.get("expanded_keys", ()))
        selected = state.get("selected_instances", {})
        if isinstance(selected, Mapping):
            self.set_selected_instances(selected)
        scroll = state.get("scroll", {})
        if isinstance(scroll, (Mapping, int)):
            QTimer.singleShot(0, lambda value=scroll: self.set_scroll_state(value))


def clear_layout(layout: Any) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def escape_button_text(value: str) -> str:
    """Keep literal ampersands visible instead of turning them into mnemonics."""

    return str(value or "").replace("&", "&&")


def repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


EVENT_NAV_STYLE = """
QWidget#DataEntryEventNav,
QScrollArea#DataEntryEventNavScroll,
QWidget#DataEntryEventNavBody {
    background: transparent;
    border: none;
}

QFrame#DataEntryEventNavGroup {
    background: #ffffff;
    border: 1px solid #dbe5ea;
    border-radius: 9px;
}

QFrame#DataEntryEventNavHeaderFrame {
    background: #f8fafc;
    border: none;
    border-radius: 8px;
}

QToolButton#DataEntryEventNavHeader {
    min-height: 30px;
    padding: 2px 7px;
    background: #f8fafc;
    color: #17324d;
    border: none;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 700;
    text-align: left;
}

QToolButton#DataEntryEventNavHeader:hover {
    background: #eaf7f5;
    color: #007f78;
}

QFrame#DataEntryEventNavContent,
QFrame#DataEntryEventNavInstanceBody,
QFrame#DataEntryEventNavEventInstances {
    background: #ffffff;
    border: none;
}

QToolButton#DataEntryEventNavEventInstance {
    min-width: 34px;
    min-height: 25px;
    padding: 1px 6px;
    background: #f8fafc;
    color: #475569;
    border: 1px solid #d5e1e7;
    border-radius: 13px;
    font-size: 11px;
    font-weight: 700;
}

QToolButton#DataEntryEventNavEventInstance:hover,
QToolButton#DataEntryEventNavEventInstance[active="true"] {
    background: #17324d;
    color: #ffffff;
    border-color: #17324d;
}

QFrame#DataEntryEventNavFormRow {
    background: transparent;
    border: none;
    border-radius: 7px;
}

QFrame#DataEntryEventNavFormRow[active="true"] {
    background: #e8f7f4;
}

QLabel#DataEntryEventNavFormLabel,
QLabel#DataEntryEventNavFormButtonLabel {
    color: #334155;
    font-size: 12px;
}

QLabel#DataEntryEventNavStatus {
    background: transparent;
    color: #94a3b8;
    border: none;
    font-size: 13px;
    font-weight: 800;
}

QLabel#DataEntryEventNavStatus[nav_status="partial"] {
    color: #d98922;
}

QLabel#DataEntryEventNavStatus[nav_status="filled"] {
    color: #0d9488;
}

QLabel#DataEntryEventNavFormLabel {
    background: transparent;
    border: none;
    padding: 4px 5px;
}

QFrame#DataEntryEventNavFormButton {
    min-height: 28px;
    background: transparent;
    border: none;
    border-radius: 6px;
}

QLabel#DataEntryEventNavFormButtonLabel {
    background: transparent;
    border: none;
}

QFrame#DataEntryEventNavFormButton:hover,
QFrame#DataEntryEventNavFormButton[active="true"] {
    background: #e8f7f4;
}

QFrame#DataEntryEventNavFormButton:hover QLabel#DataEntryEventNavFormButtonLabel,
QFrame#DataEntryEventNavFormButton[active="true"] QLabel#DataEntryEventNavFormButtonLabel {
    color: #007f78;
    font-weight: 700;
}

QToolButton#DataEntryEventNavInstance {
    min-width: 31px;
    min-height: 27px;
    padding: 1px 5px;
    background: #f8fafc;
    color: #475569;
    border: 1px solid #d5e1e7;
    border-radius: 7px;
    font-size: 11px;
    font-weight: 700;
}

QToolButton#DataEntryEventNavInstance:hover,
QToolButton#DataEntryEventNavInstance[active="true"] {
    background: #008c83;
    color: #ffffff;
    border-color: #008c83;
}

QToolButton#DataEntryEventNavInstance[nav_status="partial"] {
    border-color: #f0a83b;
}

QToolButton#DataEntryEventNavAdd {
    min-width: 27px;
    max-width: 27px;
    min-height: 27px;
    max-height: 27px;
    padding: 0;
    background: #ffffff;
    color: #007f78;
    border: 1px solid #83c9c2;
    border-radius: 7px;
    font-size: 17px;
    font-weight: 700;
}

QToolButton#DataEntryEventNavAdd:hover {
    background: #008c83;
    color: #ffffff;
    border-color: #008c83;
}
"""
