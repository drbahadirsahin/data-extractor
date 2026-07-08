from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from llm_settings import managed_llm_settings_from_config
from runtime_context import RuntimeContext
from gui.i18n import tr
from release_profile import app_version, show_advanced_ui
from redcap_client import (
    RedcapAPIError,
    RedcapClient,
    has_redcap_user_context_value,
    load_redcap_user_context_module_config,
)
from settings_store import RedcapProjectToken
from workspace_flow import ensure_project_config


@dataclass
class ClinicalPage:
    key: str
    label_key: str
    widget: Any


def build_default_llm_settings(runtime: RuntimeContext) -> dict[str, Any]:
    managed_settings = managed_llm_settings_from_config(getattr(runtime, "app_config", None))
    if managed_settings is not None:
        return managed_settings
    inference = runtime.settings.inference
    provider = inference.selected_provider or runtime.inference_recommendation.mode
    if provider == "openai_compatible":
        return {
            "provider": "openai_compatible",
            "base_url": inference.openai_compatible_base_url or "",
            "model": inference.openai_compatible_model or "qwen/qwen3.5-9b",
            "temperature": 0,
            "max_tokens": 8192,
            "timeout_seconds": int(inference.timeout_seconds),
            "api_key_secret_name": inference.api_key_secret_name,
            "use_json_schema": True,
        }
    base_url = inference.local_ollama_base_url
    if provider == "remote_ollama" and inference.remote_ollama_base_url:
        base_url = inference.remote_ollama_base_url
    return {
        "provider": "ollama",
        "base_url": base_url,
        "model": "qwen3.5:9b",
        "temperature": 0,
        "max_tokens": 8192,
        "timeout_seconds": 600,
        "stream": True,
        "think": False,
        "options": {"num_ctx": 32768},
    }


class ClinicalMainWindow:
    def __init__(self, runtime: RuntimeContext) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QComboBox,
            QFrame,
            QHBoxLayout,
            QLabel,
            QMainWindow,
            QPushButton,
            QScrollArea,
            QStackedWidget,
            QVBoxLayout,
            QWidget,
        )

        from gui.workspace_page import WorkspacePage
        from gui.data_entry_page import ClinicalDataEntryPage

        self.runtime = runtime
        self.language = runtime.settings.ui.language
        self.show_advanced_ui = show_advanced_ui(runtime.app_config)
        self._updating_connection_combo = False
        self._window = QMainWindow()
        self._window.setObjectName("ClinicalMainWindow")
        self._window.setWindowTitle(tr("app_title", self.language))
        self._window.resize(runtime.settings.ui.window_width, runtime.settings.ui.window_height)

        self.workspace_page = WorkspacePage(runtime)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("ClinicalSidebar")
        sidebar.setFixedWidth(248)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(18, 22, 18, 18)
        sidebar_layout.setSpacing(8)

        brand_block = QFrame()
        brand_block.setObjectName("SidebarBrandBlock")
        brand_layout = QHBoxLayout(brand_block)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(10)
        app_mark = QLabel("LLM")
        app_mark.setObjectName("SidebarAppMark")
        app_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_layout.addWidget(app_mark, 0, Qt.AlignmentFlag.AlignTop)
        brand_text = QVBoxLayout()
        brand_text.setContentsMargins(0, 0, 0, 0)
        brand_text.setSpacing(3)
        brand = QLabel("LLM Extractor")
        brand.setObjectName("AppBrand")
        brand.setWordWrap(True)
        brand_text.addWidget(brand)
        version_hint = QLabel(app_version(runtime.app_config))
        version_hint.setObjectName("SidebarVersionHint")
        version_hint.setWordWrap(True)
        brand_text.addWidget(version_hint)
        brand_layout.addLayout(brand_text, 1)
        sidebar_layout.addWidget(brand_block)

        subtitle = QLabel(tr("clinical_sidebar_subtitle", self.language))
        subtitle.setObjectName("SmallMutedLabel")
        subtitle.setWordWrap(True)
        sidebar_layout.addWidget(subtitle)

        self.connection_project_combo = QComboBox()
        self.connection_project_combo.setObjectName("SidebarProjectCombo")
        self.connection_project_combo.setMinimumContentsLength(18)
        self.connection_project_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.connection_project_combo.currentIndexChanged.connect(self.select_sidebar_project)
        sidebar_layout.addWidget(self.connection_project_combo)
        sidebar_layout.addSpacing(12)

        self.stack = QStackedWidget()
        self.nav_buttons: dict[str, QPushButton] = {}

        self.home_page = ClinicalHomePage(
            runtime=runtime,
            open_redcap=lambda: self.set_page("redcap"),
            open_import=lambda: self.set_page("import"),
            open_data_entry=lambda: self.set_page("data_entry"),
            open_excel=self.open_excel_import_flow,
            open_document_flow=self.open_document_import_flow,
            change_dag=self.change_active_dag,
        )
        self.redcap_page = ClinicalRedcapPage(runtime=runtime, on_saved=self.after_redcap_saved)
        self.data_entry_page = ClinicalDataEntryPage(runtime, change_dag=self.change_active_dag)
        self.import_page = ClinicalImportPage(
            runtime=runtime,
            add_patient_documents=self.workspace_page.add_patient_documents_to_queue,
            remove_patient_at=self.workspace_page.remove_patient_queue_item,
            run_queue=self.workspace_page.run_patient_queue_extraction,
            import_excel=self.start_excel_import,
            configure_scope=self.open_scope_dialog,
            manage_extra_fields=self.workspace_page.manage_extra_fields,
            edit_rules=self.workspace_page.open_scan_settings_dialog,
            open_advanced=lambda: self.set_page("advanced"),
            show_advanced=self.show_advanced_ui,
            get_patient_count=lambda: len(self.workspace_page.patient_queue_items),
            get_patient_summaries=self.workspace_page.patient_queue_summaries,
            get_scope_summary=self.build_clinical_scope_summary,
            change_dag=self.change_active_dag,
        )

        self.pages = [
            ClinicalPage("home", "clinical_nav_home", self.home_page.widget),
            ClinicalPage("redcap", "clinical_nav_redcap", self.redcap_page.widget),
            ClinicalPage("import", "clinical_nav_import", self.import_page.widget),
            ClinicalPage("data_entry", "clinical_nav_data_entry", self.data_entry_page.widget),
        ]
        if self.show_advanced_ui:
            self.pages.append(ClinicalPage("advanced", "clinical_nav_advanced", self.workspace_page.widget))
        for page in self.pages:
            button = QPushButton(tr(page.label_key, self.language))
            button.setProperty("nav", True)
            button.setMinimumHeight(44)
            button.clicked.connect(lambda checked=False, key=page.key: self.set_page(key))
            self.nav_buttons[page.key] = button
            sidebar_layout.addWidget(button)
            self.stack.addWidget(self.build_scroll_page(page.widget, QScrollArea, QFrame, Qt))

        sidebar_layout.addStretch(1)
        if self.show_advanced_ui:
            mode_note = QLabel(tr("clinical_advanced_note", self.language))
            mode_note.setObjectName("SmallMutedLabel")
            mode_note.setWordWrap(True)
            sidebar_layout.addWidget(mode_note)
        version_label = QLabel(tr("clinical_version_label", self.language, version=app_version(runtime.app_config)))
        version_label.setObjectName("VersionLabel")
        version_label.setWordWrap(True)
        sidebar_layout.addWidget(version_label)

        content = QWidget()
        content.setObjectName("ClinicalContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 24, 28, 24)
        content_layout.setSpacing(16)
        content_layout.addWidget(self.stack)

        layout.addWidget(sidebar)
        layout.addWidget(content, 1)
        self._window.setCentralWidget(central)

        self.refresh_connection_state()
        self.set_page("home")

    def build_scroll_page(self, widget: Any, scroll_area_cls: Any, frame_cls: Any, qt_cls: Any) -> Any:
        scroll = scroll_area_cls()
        scroll.setObjectName("ClinicalPageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(frame_cls.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(qt_cls.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(widget)
        return scroll

    def refresh_connection_state(self) -> None:
        self.populate_connection_project_combo()
        self.home_page.refresh()
        self.import_page.refresh()
        self.data_entry_page.refresh_project_state()

    def populate_connection_project_combo(self) -> None:
        current_project_id = self.runtime.settings.redcap.selected_project_id
        projects = list(self.runtime.settings.redcap.saved_project_tokens)
        self._updating_connection_combo = True
        self.connection_project_combo.blockSignals(True)
        self.connection_project_combo.clear()
        if not projects:
            self.connection_project_combo.addItem(tr("clinical_not_connected", self.language), "")
            self.connection_project_combo.setEnabled(False)
            self.connection_project_combo.setToolTip(tr("clinical_not_connected", self.language))
        else:
            self.connection_project_combo.setEnabled(True)
            for project in projects:
                self.connection_project_combo.addItem(
                    tr("clinical_connected_project", self.language, project=project.project_name),
                    project.project_id,
                )
            if current_project_id:
                index = self.connection_project_combo.findData(current_project_id)
                if index >= 0:
                    self.connection_project_combo.setCurrentIndex(index)
            selected = self.connection_project_combo.currentText()
            self.connection_project_combo.setToolTip(selected)
            view = self.connection_project_combo.view()
            if view is not None:
                view.setMinimumWidth(360)
        self.connection_project_combo.blockSignals(False)
        self._updating_connection_combo = False

    def select_sidebar_project(self) -> None:
        if self._updating_connection_combo:
            return
        project_id = self.connection_project_combo.currentData()
        if not project_id:
            return
        for project in self.runtime.settings.redcap.saved_project_tokens:
            if project.project_id != str(project_id):
                continue
            settings = self.runtime.settings
            settings.redcap.api_url = project.api_url
            settings.redcap.selected_project_id = project.project_id
            settings.redcap.selected_project_name = project.project_name
            settings.redcap.selected_project_token_secret_name = project.token_secret_name
            self.runtime.settings_store.save(settings)
            self.refresh_project_user_context(project)
            self.workspace_page.refresh_redcap_projects()
            self.populate_connection_project_combo()
            self.home_page.refresh()
            self.import_page.refresh()
            self.data_entry_page.refresh_project_state()
            self.data_entry_page.start_sync(auto=True)
            return

    def after_redcap_saved(self) -> None:
        self.workspace_page.refresh_redcap_projects()
        self.refresh_connection_state()
        self.data_entry_page.start_sync(auto=True)
        self.set_page("import")

    def refresh_project_user_context(self, project: RedcapProjectToken | None = None) -> bool:
        project = project or current_redcap_project_token(self.runtime.settings)
        if project is None:
            return False
        token = self.runtime.secrets_store.get(project.token_secret_name)
        if not token:
            return False
        module_config = load_redcap_user_context_module_config(self.runtime.app_config)
        if not module_config.can_request:
            return False
        try:
            client = RedcapClient(api_url=project.api_url, api_token=token)
            context = client.get_external_module_user_context(
                prefix=module_config.prefix,
                action=module_config.action,
            )
        except Exception as exc:
            logging.info("Project user context refresh failed: %s", exc)
            return False
        if not has_redcap_user_context_value(context):
            return False
        self.update_saved_project_user_context(project.project_id, context)
        return True

    def update_saved_project_user_context(self, project_id: str, context: Any) -> None:
        updated = False
        for item in self.runtime.settings.redcap.saved_project_tokens:
            if item.project_id != str(project_id):
                continue
            apply_user_context_to_project_token(item, context)
            updated = True
            break
        if updated:
            self.runtime.settings_store.save(self.runtime.settings)

    def change_active_dag(self, option: dict[str, Any]) -> None:
        from PySide6.QtWidgets import QMessageBox

        project = current_redcap_project_token(self.runtime.settings)
        if project is None:
            return
        token = self.runtime.secrets_store.get(project.token_secret_name)
        if not token:
            QMessageBox.warning(
                self._window,
                tr("clinical_dag_switch_title", self.language),
                tr("clinical_dag_switch_missing_token", self.language),
            )
            return
        module_config = load_redcap_user_context_module_config(self.runtime.app_config)
        if not module_config.can_set_dag:
            return
        try:
            client = RedcapClient(api_url=project.api_url, api_token=token)
            context = client.set_external_module_user_dag(
                prefix=module_config.prefix,
                action=module_config.set_dag_action,
                data_access_group_unique_name=option.get("data_access_group_unique_name"),
                dag_group_id="0" if option.get("no_assignment") else option.get("data_access_group_id"),
                data_access_group=option.get("data_access_group"),
            )
        except Exception as exc:
            QMessageBox.warning(
                self._window,
                tr("clinical_dag_switch_title", self.language),
                tr("clinical_dag_switch_failed", self.language, error=str(exc)),
            )
            self.refresh_connection_state()
            return
        self.update_saved_project_user_context(project.project_id, context)
        self.refresh_connection_state()

    def open_document_import_flow(self) -> None:
        self.set_page("import")
        self.import_page.set_flow("documents")

    def open_excel_import_flow(self) -> None:
        self.set_page("import")
        self.import_page.set_flow("excel")
        self.import_page.set_excel_step(0)

    def start_excel_import(self, on_success: Callable[[], None] | None = None) -> bool:
        self.workspace_page.refresh_redcap_projects()
        imported = self.workspace_page.import_excel_patient_data(on_success=on_success)
        self.refresh_connection_state()
        return bool(imported)

    def open_scope_dialog(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QHBoxLayout,
            QLabel,
            QListWidget,
            QListWidgetItem,
            QMessageBox,
            QPushButton,
            QVBoxLayout,
        )

        self.workspace_page.refresh_redcap_projects()
        bundle = self.workspace_page.bundle
        if bundle is None:
            QMessageBox.warning(
                self._window,
                tr("clinical_scope_title", self.language),
                tr("clinical_import_project_missing", self.language),
            )
            return

        selected_forms = set(self.workspace_page.selected_form_names)
        selected_fields = set(self.workspace_page.selected_field_names)

        dialog = QDialog(self._window)
        dialog.setWindowTitle(tr("clinical_scope_title", self.language))
        dialog.setMinimumSize(860, 560)
        root = QVBoxLayout(dialog)
        root.setSpacing(12)

        intro = QLabel(tr("clinical_scope_desc", self.language))
        intro.setObjectName("MutedLabel")
        intro.setWordWrap(True)
        root.addWidget(intro)

        lists = QHBoxLayout()
        lists.setSpacing(14)
        form_list = QListWidget()
        field_list = QListWidget()
        summary = QLabel("")
        summary.setObjectName("SmallMutedLabel")
        summary.setWordWrap(True)

        lists.addWidget(form_list, 1)
        lists.addWidget(field_list, 1)
        root.addLayout(lists)
        root.addWidget(summary)

        rules_row = QHBoxLayout()
        rules_row.setSpacing(10)
        form_rule_button = QPushButton(tr("open_selected_form_rules", self.language))
        form_rule_button.setProperty("secondary", True)
        field_rule_button = QPushButton(tr("open_selected_field_rules", self.language))
        field_rule_button.setProperty("secondary", True)
        rules_row.addWidget(form_rule_button)
        rules_row.addWidget(field_rule_button)
        rules_row.addStretch(1)
        root.addLayout(rules_row)

        updating = {"value": False}

        def refresh_summary() -> None:
            effective_fields = selected_fields | {
                field_name
                for form_name in selected_forms
                for field_name in bundle.field_names_for_form(form_name)
            }
            summary.setText(
                tr(
                    "clinical_scope_summary",
                    self.language,
                    forms=len(selected_forms),
                    fields=len(effective_fields),
                    total_fields=len(bundle.all_field_names),
                )
            )

        def populate_fields(form_name: str | None) -> None:
            updating["value"] = True
            field_list.clear()
            if form_name:
                whole_form_selected = form_name in selected_forms
                for field_name in bundle.field_names_for_form(form_name):
                    field_spec = next(
                        (item for item in bundle.grouped_fields.get(form_name, []) if item.field_name == field_name),
                        None,
                    )
                    label = field_spec.field_label if field_spec else field_name
                    item = QListWidgetItem(f"{label} | {field_name}")
                    item.setData(Qt.ItemDataRole.UserRole, (form_name, field_name))
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(
                        Qt.CheckState.Checked
                        if whole_form_selected or field_name in selected_fields
                        else Qt.CheckState.Unchecked
                    )
                    field_list.addItem(item)
            updating["value"] = False
            refresh_summary()

        def populate_forms() -> None:
            updating["value"] = True
            form_list.clear()
            for form_name in bundle.form_names:
                item = QListWidgetItem(bundle.form_display_name(form_name))
                item.setData(Qt.ItemDataRole.UserRole, form_name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.CheckState.Checked if form_name in selected_forms else Qt.CheckState.Unchecked
                )
                form_list.addItem(item)
            if form_list.count() > 0:
                form_list.setCurrentRow(0)
            updating["value"] = False
            current = form_list.currentItem()
            populate_fields(str(current.data(Qt.ItemDataRole.UserRole)) if current else None)

        def on_form_changed(item: QListWidgetItem) -> None:
            if updating["value"]:
                return
            form_name = str(item.data(Qt.ItemDataRole.UserRole))
            if item.checkState() == Qt.CheckState.Checked:
                selected_forms.add(form_name)
                selected_fields.difference_update(bundle.field_names_for_form(form_name))
            else:
                selected_forms.discard(form_name)
            populate_fields(form_name)

        def on_current_form_changed(current, previous=None) -> None:
            form_name = str(current.data(Qt.ItemDataRole.UserRole)) if current is not None else None
            populate_fields(form_name)

        def on_field_changed(item: QListWidgetItem) -> None:
            if updating["value"]:
                return
            form_name, field_name = item.data(Qt.ItemDataRole.UserRole)
            if form_name in selected_forms:
                if item.checkState() == Qt.CheckState.Unchecked:
                    selected_forms.discard(form_name)
                    selected_fields.update(
                        name for name in bundle.field_names_for_form(form_name) if name != field_name
                    )
                    populate_forms()
                return
            if item.checkState() == Qt.CheckState.Checked:
                selected_fields.add(field_name)
            else:
                selected_fields.discard(field_name)
            refresh_summary()

        def selected_form_name() -> str | None:
            current = form_list.currentItem()
            return str(current.data(Qt.ItemDataRole.UserRole)) if current is not None else None

        def selected_field_target() -> tuple[str, str] | None:
            current = field_list.currentItem()
            if current is None:
                return None
            form_name, field_name = current.data(Qt.ItemDataRole.UserRole)
            return str(form_name), str(field_name)

        def edit_selected_form_rules() -> None:
            form_name = selected_form_name()
            if not form_name:
                QMessageBox.warning(
                    dialog,
                    tr("selected_form_rules", self.language),
                    tr("form_rules_require_selection", self.language),
                )
                return
            self.workspace_page.selected_form_names = set(selected_forms)
            self.workspace_page.selected_field_names = set(selected_fields)
            self.workspace_page.persist_selection_to_config()
            self.workspace_page.edit_form_rules_for(form_name, parent=dialog)
            self.import_page.refresh()

        def edit_selected_field_rules() -> None:
            target = selected_field_target()
            if target is None:
                QMessageBox.warning(
                    dialog,
                    tr("selected_field_rules", self.language),
                    tr("field_rules_require_selection", self.language),
                )
                return
            form_name, field_name = target
            self.workspace_page.selected_form_names = set(selected_forms)
            self.workspace_page.selected_field_names = set(selected_fields)
            self.workspace_page.persist_selection_to_config()
            self.workspace_page.edit_field_rules_for(form_name, field_name, parent=dialog)
            self.import_page.refresh()

        form_list.itemChanged.connect(on_form_changed)
        form_list.currentItemChanged.connect(on_current_form_changed)
        field_list.itemChanged.connect(on_field_changed)
        form_rule_button.clicked.connect(edit_selected_form_rules)
        field_rule_button.clicked.connect(edit_selected_field_rules)
        populate_forms()

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        root.addWidget(button_box)

        if dialog.exec() == 0:
            return

        self.workspace_page.selected_form_names = selected_forms
        self.workspace_page.selected_field_names = selected_fields
        self.workspace_page.persist_selection_to_config()
        self.workspace_page.refresh_selection_status()
        self.import_page.refresh()

    def build_clinical_scope_summary(self) -> str:
        bundle = self.workspace_page.bundle
        if bundle is None:
            return tr("clinical_scope_missing", self.language)
        selected_forms = set(self.workspace_page.selected_form_names)
        selected_fields = set(self.workspace_page.selected_field_names)
        effective_fields = selected_fields | {
            field_name
            for form_name in selected_forms
            for field_name in bundle.field_names_for_form(form_name)
        }
        if not selected_forms and not selected_fields:
            return tr("clinical_scope_all_fields", self.language, total_fields=len(bundle.all_field_names))
        return tr(
            "clinical_scope_inline_summary",
            self.language,
            forms=len(selected_forms),
            fields=len(effective_fields),
            total_fields=len(bundle.all_field_names),
        )

    def set_page(self, key: str) -> None:
        page_keys = [page.key for page in self.pages]
        if key == "advanced" and not self.show_advanced_ui:
            key = "import"
        if key not in page_keys:
            key = "home"
        if key == "advanced":
            self.workspace_page.refresh_redcap_projects()
        if key == "data_entry":
            self.data_entry_page.refresh_project_state()
        self.stack.setCurrentIndex(page_keys.index(key))
        for item_key, button in self.nav_buttons.items():
            button.setProperty("active", item_key == key)
            button.style().unpolish(button)
            button.style().polish(button)

    def show(self) -> None:
        self._window.show()


class ClinicalHomePage:
    def __init__(
        self,
        *,
        runtime: RuntimeContext,
        open_redcap: Callable[[], None],
        open_import: Callable[[], None],
        open_data_entry: Callable[[], None],
        open_excel: Callable[[], None],
        open_document_flow: Callable[[], None],
        change_dag: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        from PySide6.QtWidgets import (
            QComboBox,
            QFrame,
            QGridLayout,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QVBoxLayout,
            QWidget,
        )

        self.runtime = runtime
        self.language = runtime.settings.ui.language
        self.change_dag = change_dag
        self.widget = QWidget()
        layout = QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        dashboard_header = QFrame()
        dashboard_header.setObjectName("DashboardHeader")
        header_layout = QHBoxLayout(dashboard_header)
        header_layout.setContentsMargins(24, 22, 24, 22)
        header_layout.setSpacing(18)

        greeting_group = QVBoxLayout()
        greeting_group.setContentsMargins(0, 0, 0, 0)
        greeting_group.setSpacing(7)
        eyebrow = QLabel(tr("clinical_home_eyebrow", self.language))
        eyebrow.setObjectName("DashboardEyebrow")
        greeting_group.addWidget(eyebrow)
        self.welcome_label = QLabel("")
        self.welcome_label.setObjectName("PageTitle")
        self.welcome_label.setWordWrap(True)
        greeting_group.addWidget(self.welcome_label)
        self.welcome_subtitle = QLabel(tr("clinical_home_subtitle", self.language))
        self.welcome_subtitle.setObjectName("MutedLabel")
        self.welcome_subtitle.setWordWrap(True)
        greeting_group.addWidget(self.welcome_subtitle)
        header_layout.addLayout(greeting_group, 1)

        project_context = QFrame()
        project_context.setObjectName("DashboardContextCard")
        project_context_layout = QVBoxLayout(project_context)
        project_context_layout.setContentsMargins(14, 12, 14, 12)
        project_context_layout.setSpacing(6)
        self.status_label = QLabel("")
        self.status_label.setObjectName("WarningPill")
        self.user_context_label = QLabel("")
        self.user_context_label.setObjectName("ProjectContextLabel")
        self.user_context_label.setWordWrap(True)
        self.dag_combo = QComboBox()
        self.dag_combo.setObjectName("DagSwitchCombo")
        self.dag_combo.setMinimumWidth(180)
        self.dag_combo.currentIndexChanged.connect(self.on_dag_changed)
        project_context_layout.addWidget(self.status_label)
        project_context_layout.addWidget(self.user_context_label)
        project_context_layout.addWidget(self.dag_combo)
        header_layout.addWidget(project_context, 0)
        layout.addWidget(dashboard_header)

        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(12)
        self.record_metric_value = QLabel("-")
        self.pending_metric_value = QLabel("-")
        self.connection_metric_value = QLabel("-")
        self.sync_metric_value = QLabel("-")
        metrics_grid.addWidget(
            build_dashboard_metric_card(
                tr("clinical_home_metric_records", self.language),
                self.record_metric_value,
                tr("clinical_home_metric_local_cache", self.language),
            ),
            0,
            0,
        )
        metrics_grid.addWidget(
            build_dashboard_metric_card(
                tr("clinical_home_metric_pending", self.language),
                self.pending_metric_value,
                tr("clinical_home_metric_submission_queue", self.language),
            ),
            0,
            1,
        )
        metrics_grid.addWidget(
            build_dashboard_metric_card(
                tr("clinical_home_metric_redcap", self.language),
                self.connection_metric_value,
                tr("clinical_home_metric_active_project", self.language),
            ),
            0,
            2,
        )
        metrics_grid.addWidget(
            build_dashboard_metric_card(
                tr("clinical_home_metric_last_sync", self.language),
                self.sync_metric_value,
                tr("clinical_home_metric_local_status", self.language),
            ),
            0,
            3,
        )
        for column in range(4):
            metrics_grid.setColumnStretch(column, 1)
        layout.addLayout(metrics_grid)

        quick_title = QLabel(tr("clinical_home_quick_actions", self.language))
        quick_title.setObjectName("DashboardSectionTitle")
        layout.addWidget(quick_title)

        action_grid = QGridLayout()
        action_grid.setSpacing(12)
        action_grid.addWidget(
            build_dashboard_action_card(
                code="01",
                title=tr("clinical_card_data_entry_title", self.language).replace("4. ", ""),
                body=tr("clinical_card_data_entry_body", self.language),
                primary_label=tr("clinical_card_data_entry_action", self.language),
                primary_action=open_data_entry,
            ),
            0,
            0,
        )
        action_grid.addWidget(
            build_dashboard_action_card(
                code="02",
                title=tr("clinical_card_document_title", self.language).replace("2. ", ""),
                body=tr("clinical_card_document_body", self.language),
                primary_label=tr("clinical_card_document_action", self.language),
                primary_action=open_document_flow,
            ),
            0,
            1,
        )
        action_grid.addWidget(
            build_dashboard_action_card(
                code="03",
                title=tr("clinical_card_excel_title", self.language).replace("3. ", ""),
                body=tr("clinical_card_excel_body", self.language),
                primary_label=tr("clinical_card_excel_action", self.language),
                primary_action=open_excel,
            ),
            0,
            2,
        )
        action_grid.addWidget(
            build_dashboard_action_card(
                code="04",
                title=tr("clinical_card_redcap_title", self.language).replace("1. ", ""),
                body=tr("clinical_card_redcap_body", self.language),
                primary_label=tr("clinical_card_redcap_action", self.language),
                primary_action=open_redcap,
            ),
            0,
            3,
        )
        for column in range(4):
            action_grid.setColumnStretch(column, 1)
        layout.addLayout(action_grid)

        lower_grid = QGridLayout()
        lower_grid.setSpacing(12)
        activity_panel = QFrame()
        activity_panel.setObjectName("DashboardPanel")
        activity_layout = QVBoxLayout(activity_panel)
        activity_layout.setContentsMargins(18, 16, 18, 16)
        activity_layout.setSpacing(10)
        activity_title = QLabel(tr("clinical_home_recent_activity", self.language))
        activity_title.setObjectName("DashboardSectionTitle")
        activity_layout.addWidget(activity_title)
        self.activity_project_row = build_dashboard_status_row(tr("clinical_home_status_project", self.language), "-")
        self.activity_records_row = build_dashboard_status_row(tr("clinical_home_status_records", self.language), "-")
        self.activity_pending_row = build_dashboard_status_row(tr("clinical_home_status_pending", self.language), "-")
        activity_layout.addWidget(self.activity_project_row)
        activity_layout.addWidget(self.activity_records_row)
        activity_layout.addWidget(self.activity_pending_row)
        activity_layout.addStretch(1)

        system_panel = QFrame()
        system_panel.setObjectName("DashboardPanel")
        system_layout = QVBoxLayout(system_panel)
        system_layout.setContentsMargins(18, 16, 18, 16)
        system_layout.setSpacing(10)
        system_title = QLabel(tr("clinical_home_system_status", self.language))
        system_title.setObjectName("DashboardSectionTitle")
        system_layout.addWidget(system_title)
        self.system_redcap_row = build_dashboard_status_row(tr("clinical_home_system_server", self.language), "-")
        self.system_llm_row = build_dashboard_status_row(tr("clinical_home_system_llm", self.language), "-")
        self.system_local_row = build_dashboard_status_row(tr("clinical_home_system_local_db", self.language), "-")
        system_layout.addWidget(self.system_redcap_row)
        system_layout.addWidget(self.system_llm_row)
        system_layout.addWidget(self.system_local_row)
        system_layout.addStretch(1)

        lower_grid.addWidget(activity_panel, 0, 0)
        lower_grid.addWidget(system_panel, 0, 1)
        lower_grid.setColumnStretch(0, 1)
        lower_grid.setColumnStretch(1, 1)
        layout.addLayout(lower_grid)
        layout.addStretch(1)
        self.refresh()

    def on_dag_changed(self) -> None:
        option = self.dag_combo.currentData()
        if self.change_dag is None or not isinstance(option, dict) or option.get("active") or not option.get("switchable"):
            return
        self.change_dag(option)

    def refresh(self) -> None:
        project = self.runtime.settings.redcap.selected_project_name
        project_token = current_redcap_project_token(self.runtime.settings)
        username = project_token.username if project_token is not None and project_token.username else None
        self.welcome_label.setText(
            tr("clinical_home_welcome_user", self.language, username=username)
            if username
            else tr("clinical_home_title", self.language)
        )
        record_count, pending_count, last_sync = self.dashboard_cache_stats(project_token)
        if project:
            self.status_label.setObjectName("StatusPill")
            self.status_label.setText(tr("clinical_ready_status", self.language, project=project))
            self.user_context_label.setVisible(True)
            self.user_context_label.setText(
                format_project_user_context(project_token, self.language)
                if project_token is not None
                else tr("clinical_user_context_missing", self.language)
            )
        else:
            self.status_label.setObjectName("WarningPill")
            self.status_label.setText(tr("clinical_setup_required_status", self.language))
            self.user_context_label.setVisible(False)
            self.user_context_label.setText("")
        self.record_metric_value.setText(format_dashboard_count(record_count))
        self.pending_metric_value.setText(format_dashboard_count(pending_count))
        self.connection_metric_value.setText(
            tr("clinical_home_connection_ready", self.language)
            if project
            else tr("clinical_home_connection_missing", self.language)
        )
        self.sync_metric_value.setText(last_sync or "-")
        set_dashboard_status_row(
            self.activity_project_row,
            tr("clinical_home_status_project", self.language),
            project or tr("clinical_home_project_waiting", self.language),
        )
        set_dashboard_status_row(
            self.activity_records_row,
            tr("clinical_home_status_records", self.language),
            tr("clinical_home_local_record_count", self.language, count=format_dashboard_count(record_count)),
        )
        set_dashboard_status_row(
            self.activity_pending_row,
            tr("clinical_home_status_pending", self.language),
            tr("clinical_home_pending_change_count", self.language, count=format_dashboard_count(pending_count)),
        )
        set_dashboard_status_row(
            self.system_redcap_row,
            tr("clinical_home_system_server", self.language),
            tr("clinical_home_server_online", self.language)
            if project
            else tr("clinical_home_server_offline", self.language),
        )
        llm_provider = managed_llm_settings_from_config(getattr(self.runtime, "app_config", None))
        llm_status = (
            tr("clinical_home_llm_gateway", self.language)
            if llm_provider
            else str(self.runtime.settings.inference.selected_provider or tr("clinical_home_default_status", self.language))
        )
        set_dashboard_status_row(self.system_llm_row, tr("clinical_home_system_llm", self.language), llm_status)
        set_dashboard_status_row(
            self.system_local_row,
            tr("clinical_home_system_local_db", self.language),
            tr("clinical_home_local_db_ready", self.language),
        )
        configure_dag_switch_combo(self.dag_combo, project_token, self.language)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.user_context_label.style().unpolish(self.user_context_label)
        self.user_context_label.style().polish(self.user_context_label)

    def dashboard_cache_stats(self, project_token: RedcapProjectToken | None) -> tuple[int, int, str]:
        if project_token is None:
            return 0, 0, ""
        try:
            from data_entry_store import DataEntryStore
            from gui.data_entry_page import data_entry_store_path

            store = DataEntryStore(data_entry_store_path(self.runtime.app_home))
            store.initialize()
            with store.connect() as db:
                record_row = db.execute(
                    """
                    WITH records AS (
                        SELECT project_id, record FROM record_sync_state WHERE project_id = ?
                        UNION
                        SELECT project_id, record FROM redcap_data_values WHERE project_id = ?
                        UNION
                        SELECT project_id, record FROM identity_hash_map WHERE project_id = ?
                    )
                    SELECT COUNT(*) AS count FROM records
                    """,
                    (project_token.project_id, project_token.project_id, project_token.project_id),
                ).fetchone()
                pending_row = db.execute(
                    "SELECT COUNT(*) AS count FROM pending_changes WHERE project_id = ? AND status = 'queued'",
                    (project_token.project_id,),
                ).fetchone()
                sync_row = db.execute(
                    "SELECT MAX(last_synced_at) AS value FROM record_sync_state WHERE project_id = ?",
                    (project_token.project_id,),
                ).fetchone()
            record_count = int(record_row["count"] or 0) if record_row is not None else 0
            pending_count = int(pending_row["count"] or 0) if pending_row is not None else 0
            last_sync = compact_datetime_text(str(sync_row["value"] or "")) if sync_row is not None else ""
            return record_count, pending_count, last_sync
        except Exception:
            return 0, 0, ""


class ClinicalRedcapPage:
    def __init__(self, *, runtime: RuntimeContext, on_saved: Callable[[], None]) -> None:
        from PySide6.QtWidgets import (
            QComboBox,
            QFormLayout,
            QFrame,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMessageBox,
            QPushButton,
            QVBoxLayout,
            QWidget,
        )

        from redcap_client import RedcapAPIError, RedcapClient

        self.runtime = runtime
        self.on_saved = on_saved
        self.language = runtime.settings.ui.language
        self.validated_project = None
        self.validated_user_context = None
        self.RedcapAPIError = RedcapAPIError
        self.RedcapClient = RedcapClient

        self.widget = QWidget()
        layout = QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        header = QFrame()
        header.setObjectName("PageHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 18, 22, 18)
        header_layout.setSpacing(16)
        title_group = QVBoxLayout()
        title_group.setContentsMargins(0, 0, 0, 0)
        title_group.setSpacing(7)
        title = QLabel(tr("clinical_redcap_title", self.language))
        title.setObjectName("PageTitle")
        title_group.addWidget(title)
        desc = QLabel(tr("clinical_redcap_desc", self.language))
        desc.setObjectName("MutedLabel")
        desc.setWordWrap(True)
        title_group.addWidget(desc)
        header_layout.addLayout(title_group, 1)
        context_card = QFrame()
        context_card.setObjectName("PageContextCard")
        context_layout = QVBoxLayout(context_card)
        context_layout.setContentsMargins(14, 12, 14, 12)
        context_layout.setSpacing(6)
        self.header_project_status = QLabel("")
        self.header_project_status.setObjectName("WarningPill")
        self.header_project_status.setWordWrap(True)
        self.header_user_context = QLabel("")
        self.header_user_context.setObjectName("ProjectContextLabel")
        self.header_user_context.setWordWrap(True)
        context_layout.addWidget(self.header_project_status)
        context_layout.addWidget(self.header_user_context)
        header_layout.addWidget(context_card, 0)
        layout.addWidget(header)

        panel = QFrame()
        panel.setObjectName("ConnectionPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 18, 18, 18)
        panel_layout.setSpacing(12)

        connection_columns = QHBoxLayout()
        connection_columns.setSpacing(14)

        form_card = QFrame()
        form_card.setObjectName("ConnectionInnerCard")
        form_card_layout = QVBoxLayout(form_card)
        form_card_layout.setContentsMargins(18, 16, 18, 16)
        form_card_layout.setSpacing(12)
        form_title = QLabel(tr("clinical_redcap_server_info", self.language))
        form_title.setObjectName("SectionTitle")
        form_card_layout.addWidget(form_title)

        form = QFormLayout()
        form.setSpacing(10)
        configured_url = (
            runtime.settings.redcap.api_url
            or str(runtime.app_config.get("redcap", {}).get("api_url", "") or "")
        )
        self.api_url_input = QLineEdit(configured_url)
        allow_api_url_edit = bool(runtime.app_config.get("redcap", {}).get("allow_api_url_edit", False)) or not configured_url
        self.api_url_input.setReadOnly(not allow_api_url_edit)
        self.token_input = QLineEdit("")
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(tr("redcap_api_url", self.language), self.api_url_input)
        form.addRow(tr("redcap_api_token", self.language), self.token_input)
        form_card_layout.addLayout(form)

        buttons = QHBoxLayout()
        self.validate_button = QPushButton(tr("clinical_validate_token", self.language))
        self.validate_button.clicked.connect(self.validate_token)
        self.save_button = QPushButton(tr("clinical_save_connection", self.language))
        self.save_button.clicked.connect(self.save_connection)
        self.remove_button = QPushButton(tr("redcap_remove_saved_token", self.language))
        self.remove_button.setProperty("secondary", True)
        self.remove_button.clicked.connect(self.remove_saved_project)
        buttons.addWidget(self.validate_button)
        buttons.addWidget(self.save_button)
        buttons.addStretch(1)
        form_card_layout.addLayout(buttons)

        summary_card = QFrame()
        summary_card.setObjectName("ConnectionInnerCard")
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(18, 16, 18, 16)
        summary_layout.setSpacing(12)
        summary_title = QLabel(tr("clinical_redcap_connection_info", self.language))
        summary_title.setObjectName("SectionTitle")
        summary_layout.addWidget(summary_title)
        summary_form = QFormLayout()
        summary_form.setSpacing(10)
        self.project_value = QLabel("-")
        self.project_value.setObjectName("ReadonlyInfoValue")
        self.project_value.setWordWrap(True)
        self.user_context_value = QLabel("-")
        self.user_context_value.setObjectName("ReadonlyInfoValue")
        self.user_context_value.setWordWrap(True)
        self.saved_projects = QComboBox()
        summary_form.addRow(tr("validated_project", self.language), self.project_value)
        summary_form.addRow(tr("redcap_user_context", self.language), self.user_context_value)
        summary_form.addRow(tr("saved_redcap_projects", self.language), self.saved_projects)
        summary_layout.addLayout(summary_form)
        remove_row = QHBoxLayout()
        remove_row.addWidget(self.remove_button)
        remove_row.addStretch(1)
        summary_layout.addLayout(remove_row)
        summary_layout.addStretch(1)

        connection_columns.addWidget(form_card, 3)
        connection_columns.addWidget(summary_card, 2)
        panel_layout.addLayout(connection_columns)

        self.status = QLabel("")
        self.status.setObjectName("WizardStatus")
        self.status.setWordWrap(True)
        panel_layout.addWidget(self.status)

        self.populate_saved_projects()
        self.update_selected_project_display()
        self.saved_projects.currentIndexChanged.connect(self.select_saved_project)

        layout.addWidget(panel)
        layout.addStretch(1)
        self.refresh_remove_button()

    def get_api_url(self) -> str:
        return self.api_url_input.text().strip()

    def validate_token(self) -> None:
        api_url = self.get_api_url()
        token = self.token_input.text().strip()
        if not api_url or not token:
            self.status.setText(tr("redcap_missing_credentials", self.language))
            return
        try:
            client = self.RedcapClient(api_url=api_url, api_token=token)
            project = client.get_project()
        except self.RedcapAPIError as exc:
            self.validated_project = None
            self.validated_user_context = None
            self.project_value.setText("-")
            self.user_context_value.setText("-")
            self.status.setText(str(exc))
            return
        if project is None:
            self.validated_project = None
            self.validated_user_context = None
            self.project_value.setText("-")
            self.user_context_value.setText("-")
            self.status.setText(tr("redcap_no_projects", self.language))
            return
        self.validated_user_context = self.fetch_user_context(client)
        self.validated_project = project
        self.project_value.setText(f"{project.project_title} ({project.project_id})")
        self.user_context_value.setText(format_redcap_user_context(self.validated_user_context, self.language))
        self.status.setText(tr("redcap_project_validated", self.language, project=project.project_title))
        self.save_connection()

    def fetch_user_context(self, client) -> Any:
        module_config = load_redcap_user_context_module_config(self.runtime.app_config)
        if module_config.can_request:
            try:
                context = client.get_external_module_user_context(
                    prefix=module_config.prefix,
                    action=module_config.action,
                )
                if has_redcap_user_context_value(context):
                    return context
            except RedcapAPIError as exc:
                logging.info("External module user context request failed: %s", exc)
            except Exception as exc:
                logging.info("External module user context request failed: %s", exc)

        try:
            context = client.get_user_context()
        except RedcapAPIError:
            return None
        except Exception:
            return None
        if not has_redcap_user_context_value(context):
            return None
        return context

    def save_connection(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        api_url = self.get_api_url()
        token = self.token_input.text().strip()
        project = self.validated_project
        if not api_url or not token or project is None:
            self.status.setText(tr("redcap_validate_before_save", self.language))
            return
        token_secret_name = build_redcap_token_secret_name(project.project_id)
        self.runtime.secrets_store.set(token_secret_name, token)
        settings = self.runtime.settings
        settings.redcap.api_url = api_url
        settings.redcap.selected_project_id = project.project_id
        settings.redcap.selected_project_name = project.project_title
        settings.redcap.selected_project_token_secret_name = token_secret_name
        replacing_existing = any(
            item.project_id == project.project_id for item in settings.redcap.saved_project_tokens
        )
        project_token = RedcapProjectToken(
            api_url=api_url,
            project_id=project.project_id,
            project_name=project.project_title,
            token_secret_name=token_secret_name,
        )
        apply_user_context_to_project_token(project_token, self.validated_user_context)
        upsert_project_token(
            settings.redcap.saved_project_tokens,
            project_token,
        )
        settings.first_run_completed = True
        self.runtime.settings_store.save(settings)
        self.populate_saved_projects()
        self.update_selected_project_display()
        self.status.setText(
            tr(
                "redcap_project_replaced" if replacing_existing else "redcap_project_saved",
                self.language,
                project=project.project_title,
            )
        )
        try:
            config_path = ensure_project_config(
                app_home=self.runtime.app_home,
                project_id=project.project_id,
                project_name=project.project_title,
                api_url=api_url,
                api_token=token,
                default_llm_settings=build_default_llm_settings(self.runtime),
                project_defaults=self.runtime.app_config.get("project_defaults", {}),
            )
        except Exception as exc:
            QMessageBox.warning(
                self.widget,
                tr("clinical_redcap_title", self.language),
                tr("config_load_error", self.language, error=str(exc)),
            )
            return
        settings.preferred_project_config_path = str(config_path)
        self.runtime.settings_store.save(settings)
        self.token_input.clear()
        self.status.setText(
            tr(
                "redcap_project_replaced" if replacing_existing else "redcap_project_saved",
                self.language,
                project=project.project_title,
            )
        )
        self.on_saved()

    def populate_saved_projects(self) -> None:
        self.saved_projects.blockSignals(True)
        self.saved_projects.clear()
        self.saved_projects.addItem(tr("redcap_saved_placeholder", self.language), "")
        for project in self.runtime.settings.redcap.saved_project_tokens:
            self.saved_projects.addItem(project.project_name, project.project_id)
        selected_id = self.runtime.settings.redcap.selected_project_id
        if selected_id:
            index = self.saved_projects.findData(selected_id)
            if index >= 0:
                self.saved_projects.setCurrentIndex(index)
        self.saved_projects.blockSignals(False)
        self.update_selected_project_display()
        self.refresh_remove_button()

    def update_selected_project_display(self) -> None:
        project_id = self.runtime.settings.redcap.selected_project_id
        if not project_id:
            self.project_value.setText("-")
            self.user_context_value.setText("-")
            self.header_project_status.setObjectName("WarningPill")
            self.header_project_status.setText(tr("clinical_setup_required_status", self.language))
            self.header_user_context.setText(tr("clinical_user_context_missing", self.language))
            repolish(self.header_project_status)
            repolish(self.header_user_context)
            return
        for project in self.runtime.settings.redcap.saved_project_tokens:
            if project.project_id != str(project_id):
                continue
            self.api_url_input.setText(project.api_url)
            self.project_value.setText(f"{project.project_name} ({project.project_id})")
            self.user_context_value.setText(format_project_user_context(project, self.language))
            self.header_project_status.setObjectName("StatusPill")
            self.header_project_status.setText(tr("clinical_ready_status", self.language, project=project.project_name))
            self.header_user_context.setText(format_project_user_context(project, self.language))
            repolish(self.header_project_status)
            repolish(self.header_user_context)
            return

    def select_saved_project(self) -> None:
        project_id = self.saved_projects.currentData()
        if not project_id:
            return
        for project in self.runtime.settings.redcap.saved_project_tokens:
            if project.project_id != str(project_id):
                continue
            settings = self.runtime.settings
            settings.redcap.api_url = project.api_url
            settings.redcap.selected_project_id = project.project_id
            settings.redcap.selected_project_name = project.project_name
            settings.redcap.selected_project_token_secret_name = project.token_secret_name
            self.runtime.settings_store.save(settings)
            self.api_url_input.setText(project.api_url)
            self.project_value.setText(f"{project.project_name} ({project.project_id})")
            self.user_context_value.setText(format_project_user_context(project, self.language))
            self.status.setText(tr("redcap_project_selected", self.language, project=project.project_name))
            self.on_saved()
            return

    def remove_saved_project(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        project = self.current_saved_project()
        if project is None:
            self.status.setText(tr("redcap_remove_no_saved_selection", self.language))
            return
        answer = QMessageBox.question(
            self.widget,
            tr("redcap_remove_saved_token", self.language),
            tr("redcap_remove_saved_token_confirm", self.language, project=project.project_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        settings = self.runtime.settings
        settings.redcap.saved_project_tokens = [
            item for item in settings.redcap.saved_project_tokens if item.project_id != project.project_id
        ]
        self.runtime.secrets_store.delete(project.token_secret_name)

        replacement = settings.redcap.saved_project_tokens[0] if settings.redcap.saved_project_tokens else None
        if replacement is not None:
            settings.redcap.api_url = replacement.api_url
            settings.redcap.selected_project_id = replacement.project_id
            settings.redcap.selected_project_name = replacement.project_name
            settings.redcap.selected_project_token_secret_name = replacement.token_secret_name
        else:
            configured_url = str(self.runtime.app_config.get("redcap", {}).get("api_url", "") or "").strip()
            settings.redcap.api_url = configured_url or None
            settings.redcap.selected_project_id = None
            settings.redcap.selected_project_name = None
            settings.redcap.selected_project_token_secret_name = None
            settings.preferred_project_config_path = None

        self.runtime.settings_store.save(settings)
        self.validated_project = None
        self.validated_user_context = None
        self.token_input.clear()
        self.populate_saved_projects()
        self.update_selected_project_display()
        self.status.setText(tr("redcap_project_removed", self.language, project=project.project_name))
        self.on_saved()

    def current_saved_project(self) -> RedcapProjectToken | None:
        project_id = self.saved_projects.currentData()
        if not project_id:
            return None
        for project in self.runtime.settings.redcap.saved_project_tokens:
            if project.project_id == str(project_id):
                return project
        return None

    def refresh_remove_button(self) -> None:
        if hasattr(self, "remove_button"):
            self.remove_button.setEnabled(self.current_saved_project() is not None)


class ClinicalImportPage:
    def __init__(
        self,
        *,
        runtime: RuntimeContext,
        add_patient_documents: Callable[[], bool | None],
        remove_patient_at: Callable[[int], bool],
        run_queue: Callable[[], None],
        import_excel: Callable[[Callable[[], None] | None], bool | None],
        configure_scope: Callable[[], None],
        manage_extra_fields: Callable[[], None],
        edit_rules: Callable[[], None],
        open_advanced: Callable[[], None],
        get_patient_count: Callable[[], int],
        get_patient_summaries: Callable[[], list[str]],
        get_scope_summary: Callable[[], str],
        change_dag: Callable[[dict[str, Any]], None] | None = None,
        show_advanced: bool = False,
    ) -> None:
        from PySide6.QtWidgets import (
            QComboBox,
            QFrame,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QStackedWidget,
            QVBoxLayout,
            QWidget,
        )

        self.runtime = runtime
        self.language = runtime.settings.ui.language
        self.add_patient_documents = add_patient_documents
        self.remove_patient_at = remove_patient_at
        self.run_queue = run_queue
        self.import_excel = import_excel
        self.configure_scope = configure_scope
        self.manage_extra_fields = manage_extra_fields
        self.edit_rules = edit_rules
        self.open_advanced = open_advanced
        self.show_advanced = show_advanced
        self.get_patient_count = get_patient_count
        self.get_patient_summaries = get_patient_summaries
        self.get_scope_summary = get_scope_summary
        self.change_dag = change_dag
        self.document_step = 0
        self.excel_step = 0
        self.document_step_labels = []
        self.excel_step_labels = []
        self.widget = QWidget()
        layout = QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        header = QFrame()
        header.setObjectName("PageHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(14)
        title_group = QVBoxLayout()
        title = QLabel(tr("clinical_import_title", self.language))
        title.setObjectName("PageTitle")
        title_group.addWidget(title)
        subtitle = QLabel(tr("clinical_import_subtitle", self.language))
        subtitle.setObjectName("MutedLabel")
        subtitle.setWordWrap(True)
        title_group.addWidget(subtitle)
        header_layout.addLayout(title_group, 1)

        self.project_status = QLabel("")
        self.project_status.setObjectName("StatusPill")
        self.project_status.setWordWrap(True)
        self.project_user_context = QLabel("")
        self.project_user_context.setObjectName("ProjectContextLabel")
        self.project_user_context.setWordWrap(True)
        self.dag_combo = QComboBox()
        self.dag_combo.setObjectName("DagSwitchCombo")
        self.dag_combo.setMinimumWidth(180)
        self.dag_combo.currentIndexChanged.connect(self.on_dag_changed)
        project_status_group = QFrame()
        project_status_group.setObjectName("PageContextCard")
        project_status_layout = QVBoxLayout(project_status_group)
        project_status_layout.setContentsMargins(14, 12, 14, 12)
        project_status_layout.setSpacing(6)
        project_status_layout.addWidget(self.project_status)
        project_status_layout.addWidget(self.project_user_context)
        project_status_layout.addWidget(self.dag_combo)
        header_layout.addWidget(project_status_group)
        layout.addWidget(header)

        source_row = QHBoxLayout()
        source_row.setSpacing(10)
        self.document_mode_button = QPushButton(tr("clinical_source_documents", self.language))
        self.document_mode_button.setProperty("tab", True)
        self.document_mode_button.clicked.connect(lambda: self.set_flow("documents"))
        self.excel_mode_button = QPushButton(tr("clinical_source_excel", self.language))
        self.excel_mode_button.setProperty("tab", True)
        self.excel_mode_button.clicked.connect(lambda: self.set_flow("excel"))
        source_row.addWidget(self.document_mode_button)
        source_row.addWidget(self.excel_mode_button)
        source_row.addStretch(1)
        layout.addLayout(source_row)

        self.flow_stack = QStackedWidget()
        self.document_flow = self.build_document_flow()
        self.excel_flow = self.build_excel_flow()
        self.flow_stack.addWidget(self.document_flow)
        self.flow_stack.addWidget(self.excel_flow)
        layout.addWidget(self.flow_stack, 1)

        self.refresh()
        self.set_flow("documents")

    def on_dag_changed(self) -> None:
        option = self.dag_combo.currentData()
        if self.change_dag is None or not isinstance(option, dict) or option.get("active") or not option.get("switchable"):
            return
        self.change_dag(option)

    def refresh(self) -> None:
        project = self.runtime.settings.redcap.selected_project_name
        project_token = current_redcap_project_token(self.runtime.settings)
        if project:
            self.project_status.setObjectName("StatusPill")
            self.project_status.setText(tr("clinical_import_project_ready", self.language, project=project))
            self.project_user_context.setText(
                format_project_user_context(project_token, self.language)
                if project_token is not None
                else tr("clinical_user_context_missing", self.language)
            )
        else:
            self.project_status.setObjectName("WarningPill")
            self.project_status.setText(tr("clinical_import_project_missing", self.language))
            self.project_user_context.setText(tr("clinical_user_context_missing", self.language))
        configure_dag_switch_combo(self.dag_combo, project_token, self.language)
        self.project_status.style().unpolish(self.project_status)
        self.project_status.style().polish(self.project_status)
        self.project_user_context.style().unpolish(self.project_user_context)
        self.project_user_context.style().polish(self.project_user_context)
        self.refresh_document_status()
        self.refresh_excel_status()
        self.refresh_document_navigation()
        self.refresh_excel_navigation()

    def set_flow(self, flow: str) -> None:
        is_documents = flow == "documents"
        self.flow_stack.setCurrentIndex(0 if is_documents else 1)
        self.document_mode_button.setProperty("active", is_documents)
        self.excel_mode_button.setProperty("active", not is_documents)
        for button in [self.document_mode_button, self.excel_mode_button]:
            button.style().unpolish(button)
            button.style().polish(button)
        self.refresh()

    def build_document_flow(self):
        from PySide6.QtWidgets import (
            QFrame,
            QHBoxLayout,
            QLabel,
            QListWidget,
            QPushButton,
            QStackedWidget,
            QVBoxLayout,
            QWidget,
        )

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(
            self.build_stepper(
                [
                    tr("clinical_doc_step_1", self.language),
                    tr("clinical_doc_step_2", self.language),
                    tr("clinical_doc_step_3", self.language),
                ],
                "documents",
            )
        )

        self.document_stack = QStackedWidget()
        self.document_queue_status = QLabel("")
        self.document_scope_status = QLabel("")
        self.document_review_status = QLabel("")
        self.document_patient_queue_list = QListWidget()
        self.document_patient_queue_list.setObjectName("WizardQueueList")

        self.document_stack.addWidget(
            self.build_wizard_page(
                number="01",
                title=tr("clinical_document_queue_title", self.language),
                body=tr("clinical_document_queue_body", self.language),
                status_label=self.document_queue_status,
                extra_widget=self.document_patient_queue_list,
                actions=[
                    (tr("clinical_add_patient_to_queue", self.language), self.add_patient, False),
                    (tr("remove_selected_patient", self.language), self.remove_selected_patient, True),
                ],
            )
        )
        self.document_stack.addWidget(
            self.build_wizard_page(
                number="02",
                title=tr("clinical_document_scope_title", self.language),
                body=tr("clinical_document_scope_body", self.language),
                status_label=self.document_scope_status,
                actions=[
                    (tr("clinical_configure_scope", self.language), self.configure_scope, False),
                    (tr("clinical_manage_extra_fields", self.language), self.manage_extra_fields, True),
                ],
            )
        )
        self.document_stack.addWidget(
            self.build_wizard_page(
                number="03",
                title=tr("clinical_document_review_title", self.language),
                body=tr("clinical_document_review_body", self.language),
                status_label=self.document_review_status,
                actions=self.document_review_actions(),
            )
        )
        layout.addWidget(self.document_stack, 1)

        guidance = QFrame()
        guidance.setObjectName("GuidancePanel")
        guidance_layout = QVBoxLayout(guidance)
        guidance_layout.setContentsMargins(18, 16, 18, 16)
        guidance_title = QLabel(tr("clinical_document_guidance_title", self.language))
        guidance_title.setObjectName("SectionTitle")
        guidance_layout.addWidget(guidance_title)
        guidance_body = QLabel(tr("clinical_document_guidance_body", self.language))
        guidance_body.setObjectName("MutedLabel")
        guidance_body.setWordWrap(True)
        guidance_layout.addWidget(guidance_body)
        layout.addWidget(guidance)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addStretch(1)
        self.document_back_button = QPushButton(tr("clinical_previous", self.language))
        self.document_back_button.setProperty("secondary", True)
        self.document_back_button.clicked.connect(self.previous_document_step)
        self.document_next_button = QPushButton("")
        self.document_next_button.clicked.connect(self.next_document_step)
        footer.addWidget(self.document_back_button)
        footer.addWidget(self.document_next_button)
        layout.addLayout(footer)
        return page

    def build_excel_flow(self):
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(
            self.build_stepper(
                [
                    tr("clinical_excel_step_1", self.language),
                    tr("clinical_excel_step_2", self.language),
                ],
                "excel",
            )
        )

        self.excel_stack = QStackedWidget()
        self.excel_file_status = QLabel("")
        self.excel_review_status = QLabel("")
        self.excel_stack.addWidget(
            self.build_wizard_page(
                number="01",
                title=tr("clinical_excel_file_title", self.language),
                body=tr("clinical_excel_file_body", self.language),
                status_label=self.excel_file_status,
                actions=[(tr("clinical_import_excel_now", self.language), self.run_excel_import_step, False)],
            )
        )
        self.excel_stack.addWidget(
            self.build_wizard_page(
                number="02",
                title=tr("clinical_excel_review_title", self.language),
                body=tr("clinical_excel_review_body", self.language),
                status_label=self.excel_review_status,
                actions=self.excel_review_actions(),
            )
        )
        layout.addWidget(self.excel_stack, 1)
        note = QLabel(tr("clinical_excel_guidance_body", self.language))
        note.setObjectName("MutedLabel")
        note.setWordWrap(True)
        layout.addWidget(note)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addStretch(1)
        self.excel_back_button = QPushButton(tr("clinical_previous", self.language))
        self.excel_back_button.setProperty("secondary", True)
        self.excel_back_button.clicked.connect(self.previous_excel_step)
        self.excel_next_button = QPushButton("")
        self.excel_next_button.clicked.connect(self.next_excel_step)
        footer.addWidget(self.excel_back_button)
        footer.addWidget(self.excel_next_button)
        layout.addLayout(footer)
        return page

    def document_review_actions(self) -> list[tuple[str, Callable[[], None], bool]]:
        actions = [(tr("clinical_run_queue", self.language), self.run_queue, False)]
        if self.show_advanced:
            actions.append((tr("clinical_open_advanced", self.language), self.open_advanced, True))
        return actions

    def excel_review_actions(self) -> list[tuple[str, Callable[[], None], bool]]:
        if not self.show_advanced:
            return []
        return [(tr("clinical_open_advanced", self.language), self.open_advanced, True)]

    def build_stepper(self, labels: list[str], flow: str):
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton

        frame = QFrame()
        frame.setObjectName("Stepper")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        label_widgets = []
        for index, label in enumerate(labels, start=1):
            item = QPushButton(f"{index}. {label}")
            item.setObjectName("WizardStepPill")
            item.setProperty("step", True)
            if flow == "documents":
                item.clicked.connect(lambda checked=False, step=index - 1: self.set_document_step(step))
            else:
                item.clicked.connect(lambda checked=False, step=index - 1: self.set_excel_step(step))
            layout.addWidget(item)
            label_widgets.append(item)
        if flow == "documents":
            self.document_step_labels = label_widgets
        else:
            self.excel_step_labels = label_widgets
        return frame

    def build_wizard_page(
        self,
        *,
        number: str,
        title: str,
        body: str,
        status_label,
        actions: list[tuple[str, Callable[[], bool | None], bool]],
        extra_widget=None,
    ):
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

        panel = QFrame()
        panel.setObjectName("WizardPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(13)
        number_label = QLabel(number)
        number_label.setObjectName("StepNumber")
        layout.addWidget(number_label)
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)
        body_label = QLabel(body)
        body_label.setObjectName("MutedLabel")
        body_label.setWordWrap(True)
        layout.addWidget(body_label)
        status_label.setObjectName("WizardStatus")
        status_label.setWordWrap(True)
        layout.addWidget(status_label)
        if extra_widget is not None:
            layout.addWidget(extra_widget, 1)
        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)
        for label, callback, secondary in actions:
            button = QPushButton(label)
            if secondary:
                button.setProperty("secondary", True)
            button.clicked.connect(lambda checked=False, cb=callback: self.run_action(cb))
            actions_row.addWidget(button)
        actions_row.addStretch(1)
        layout.addLayout(actions_row)
        layout.addStretch(1)
        return panel

    def run_action(self, callback: Callable[[], bool | None]) -> bool:
        result = callback()
        self.refresh()
        return result is not False

    def add_patient(self) -> bool:
        added = self.run_action(self.add_patient_documents)
        if added:
            self.set_document_step(0)
        return added

    def remove_selected_patient(self) -> bool:
        if not hasattr(self, "document_patient_queue_list"):
            return False
        removed = self.remove_patient_at(self.document_patient_queue_list.currentRow())
        self.refresh()
        return removed

    def set_document_step(self, index: int) -> None:
        self.document_step = max(0, min(index, self.document_stack.count() - 1))
        self.document_stack.setCurrentIndex(self.document_step)
        self.refresh_document_navigation()

    def previous_document_step(self) -> None:
        self.set_document_step(self.document_step - 1)

    def next_document_step(self) -> None:
        if self.document_step == self.document_stack.count() - 1:
            self.run_action(self.run_queue)
            return
        self.set_document_step(self.document_step + 1)

    def refresh_document_navigation(self) -> None:
        if not hasattr(self, "document_back_button"):
            return
        self.document_back_button.setEnabled(self.document_step > 0)
        is_last = self.document_step == self.document_stack.count() - 1
        if is_last:
            self.document_next_button.setText(tr("clinical_run_queue", self.language))
            self.document_next_button.setEnabled(self.get_patient_count() > 0)
        else:
            self.document_next_button.setText(tr("clinical_next", self.language))
            if self.document_step == 0:
                self.document_next_button.setEnabled(self.get_patient_count() > 0)
            else:
                self.document_next_button.setEnabled(True)
        self.update_step_labels(self.document_step_labels, self.document_step)

    def refresh_document_status(self) -> None:
        if not hasattr(self, "document_queue_status"):
            return
        patient_count = self.get_patient_count()
        summaries = self.get_patient_summaries()
        self.document_patient_queue_list.clear()
        for summary in summaries:
            self.document_patient_queue_list.addItem(summary)
        self.document_queue_status.setText(
            tr("clinical_document_queue_status", self.language, count=patient_count)
            if patient_count
            else tr("clinical_document_queue_status_empty", self.language)
        )
        self.document_scope_status.setText(self.get_scope_summary())
        self.document_review_status.setText(
            tr("clinical_document_review_status", self.language, count=patient_count)
            if patient_count
            else tr("clinical_document_review_status_empty", self.language)
        )

    def set_excel_step(self, index: int) -> None:
        self.excel_step = max(0, min(index, self.excel_stack.count() - 1))
        self.excel_stack.setCurrentIndex(self.excel_step)
        self.refresh_excel_navigation()

    def previous_excel_step(self) -> None:
        self.set_excel_step(self.excel_step - 1)

    def next_excel_step(self) -> None:
        if self.excel_step == 0:
            self.run_excel_import_step()
            return
        if self.excel_step == self.excel_stack.count() - 1:
            if self.show_advanced:
                self.run_action(self.open_advanced)
            return
        self.set_excel_step(self.excel_step + 1)

    def run_excel_import_step(self) -> None:
        started = self.import_excel(lambda: self.set_excel_step(1))
        self.refresh()
        if started is False:
            return

    def refresh_excel_navigation(self) -> None:
        if not hasattr(self, "excel_back_button"):
            return
        self.excel_back_button.setEnabled(self.excel_step > 0)
        if self.excel_step == 0:
            self.excel_next_button.setText(tr("clinical_import_excel_now", self.language))
        elif self.excel_step == self.excel_stack.count() - 1:
            self.excel_next_button.setText(
                tr("clinical_open_advanced", self.language)
                if self.show_advanced
                else tr("clinical_next", self.language)
            )
        else:
            self.excel_next_button.setText(tr("clinical_next", self.language))
        self.excel_next_button.setEnabled(self.show_advanced or self.excel_step == 0)
        self.update_step_labels(self.excel_step_labels, self.excel_step)

    def refresh_excel_status(self) -> None:
        if not hasattr(self, "excel_file_status"):
            return
        self.excel_file_status.setText(tr("clinical_excel_file_status", self.language))
        self.excel_review_status.setText(tr("clinical_excel_review_status", self.language))

    def update_step_labels(self, labels: list[Any], active_index: int) -> None:
        for index, label in enumerate(labels):
            label.setProperty("active", index == active_index)
            label.setProperty("complete", index < active_index)
            label.setEnabled(index <= active_index)
            label.style().unpolish(label)
            label.style().polish(label)


def build_workflow_card(title: str, body: str, primary_label: str, primary_action: Callable[[], None]):
    from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout

    card = QFrame()
    card.setObjectName("WorkflowCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(22, 20, 22, 20)
    layout.setSpacing(12)
    accent = QFrame()
    accent.setObjectName("AccentStrip")
    accent.setFixedHeight(6)
    accent.setFixedWidth(46)
    layout.addWidget(accent)
    title_label = QLabel(title)
    title_label.setObjectName("SectionTitle")
    layout.addWidget(title_label)
    body_label = QLabel(body)
    body_label.setObjectName("MutedLabel")
    body_label.setWordWrap(True)
    layout.addWidget(body_label)
    layout.addStretch(1)
    button = QPushButton(primary_label)
    button.setMinimumHeight(42)
    button.clicked.connect(primary_action)
    layout.addWidget(button)
    return card


def build_dashboard_metric_card(label: str, value_label: Any, note: str):
    from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

    card = QFrame()
    card.setObjectName("DashboardMetricCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(6)
    caption = QLabel(label)
    caption.setObjectName("DashboardMetricCaption")
    caption.setWordWrap(True)
    value_label.setObjectName("DashboardMetricValue")
    value_label.setWordWrap(True)
    note_label = QLabel(note)
    note_label.setObjectName("DashboardMetricNote")
    note_label.setWordWrap(True)
    layout.addWidget(caption)
    layout.addWidget(value_label)
    layout.addWidget(note_label)
    return card


def build_dashboard_action_card(
    *,
    code: str,
    title: str,
    body: str,
    primary_label: str,
    primary_action: Callable[[], None],
):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

    card = QFrame()
    card.setObjectName("DashboardActionCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 16, 16, 14)
    layout.setSpacing(10)
    heading = QHBoxLayout()
    heading.setContentsMargins(0, 0, 0, 0)
    heading.setSpacing(9)
    badge = QLabel(code)
    badge.setObjectName("DashboardActionBadge")
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    heading.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
    title_label = QLabel(title)
    title_label.setObjectName("DashboardActionTitle")
    title_label.setWordWrap(True)
    heading.addWidget(title_label, 1)
    layout.addLayout(heading)
    body_label = QLabel(body)
    body_label.setObjectName("DashboardActionBody")
    body_label.setWordWrap(True)
    layout.addWidget(body_label)
    layout.addStretch(1)
    button = QPushButton(primary_label)
    button.setObjectName("DashboardActionButton")
    button.clicked.connect(primary_action)
    layout.addWidget(button)
    return card


def build_dashboard_status_row(label: str, value: str):
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

    row = QFrame()
    row.setObjectName("DashboardStatusRow")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    label_widget = QLabel(label)
    label_widget.setObjectName("DashboardStatusLabel")
    label_widget.setWordWrap(True)
    value_widget = QLabel(value)
    value_widget.setObjectName("DashboardStatusValue")
    value_widget.setWordWrap(True)
    layout.addWidget(label_widget, 1)
    layout.addWidget(value_widget, 0)
    row.dashboard_label_widget = label_widget
    row.dashboard_value_widget = value_widget
    return row


def set_dashboard_status_row(row: Any, label: str, value: str) -> None:
    label_widget = getattr(row, "dashboard_label_widget", None)
    value_widget = getattr(row, "dashboard_value_widget", None)
    if label_widget is not None:
        label_widget.setText(label)
    if value_widget is not None:
        value_widget.setText(value)


def format_dashboard_count(value: int) -> str:
    return f"{int(value):,}".replace(",", ".")


def compact_datetime_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "T" in text:
        text = text.replace("T", " ")
    if len(text) >= 16:
        return text[:16]
    return text


def repolish(widget: Any) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def build_redcap_token_secret_name(project_id: str | None) -> str:
    suffix = str(project_id or "default").strip() or "default"
    return f"redcap_api_token_{suffix}"


def format_redcap_user_context(context: Any, language: str) -> str:
    if context is None:
        return tr("redcap_user_context_unknown", language)
    username = getattr(context, "username", None) or tr("clinical_user_unknown", language)
    dag = (
        getattr(context, "data_access_group", None)
        or getattr(context, "data_access_group_unique_name", None)
        or tr("clinical_dag_none", language)
    )
    return tr("clinical_user_context", language, username=username, dag=dag)


def format_project_user_context(project: RedcapProjectToken, language: str) -> str:
    username = project.username or tr("clinical_user_unknown", language)
    dag = project.data_access_group or project.data_access_group_unique_name or tr("clinical_dag_none", language)
    return tr("clinical_user_context", language, username=username, dag=dag)


def apply_user_context_to_project_token(project: RedcapProjectToken, context: Any) -> None:
    if context is None:
        return
    project.username = getattr(context, "username", None)
    project.data_access_group_id = getattr(context, "data_access_group_id", None)
    project.data_access_group = getattr(context, "data_access_group", None)
    project.data_access_group_unique_name = getattr(context, "data_access_group_unique_name", None)
    project.can_switch_data_access_group = getattr(context, "can_switch_data_access_group", None)
    project.available_data_access_groups = [
        redcap_dag_option_to_dict(option)
        for option in (getattr(context, "available_data_access_groups", None) or [])
    ]


def redcap_dag_option_to_dict(option: Any) -> dict[str, Any]:
    return {
        "data_access_group_id": getattr(option, "data_access_group_id", None),
        "data_access_group": getattr(option, "data_access_group", None),
        "data_access_group_unique_name": getattr(option, "data_access_group_unique_name", None),
        "active": bool(getattr(option, "active", False)),
        "switchable": bool(getattr(option, "switchable", False)),
        "no_assignment": bool(getattr(option, "no_assignment", False)),
    }


def configure_dag_switch_combo(combo: Any, project: RedcapProjectToken | None, language: str) -> None:
    combo.blockSignals(True)
    combo.clear()
    options = list(getattr(project, "available_data_access_groups", []) or []) if project is not None else []
    can_switch = bool(getattr(project, "can_switch_data_access_group", False)) and len(options) > 1
    if not can_switch:
        combo.setVisible(False)
        combo.blockSignals(False)
        return

    active_index = 0
    for option in options:
        if not isinstance(option, dict):
            continue
        normalized = normalize_dag_option(option, project)
        combo.addItem(dag_option_label(normalized, language), normalized)
        if normalized.get("active"):
            active_index = combo.count() - 1
    combo.setCurrentIndex(active_index)
    combo.setEnabled(any(not item.get("active") and item.get("switchable") for item in combo_item_data(combo)))
    combo.setVisible(combo.count() > 1)
    combo.blockSignals(False)


def combo_item_data(combo: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index in range(combo.count()):
        item = combo.itemData(index)
        if isinstance(item, dict):
            items.append(item)
    return items


def normalize_dag_option(option: dict[str, Any], project: RedcapProjectToken | None) -> dict[str, Any]:
    normalized = {
        "data_access_group_id": option.get("data_access_group_id"),
        "data_access_group": option.get("data_access_group"),
        "data_access_group_unique_name": option.get("data_access_group_unique_name"),
        "active": bool(option.get("active")),
        "switchable": bool(option.get("switchable")),
        "no_assignment": bool(option.get("no_assignment")),
    }
    if project is not None and not normalized["active"]:
        normalized["active"] = any(
            [
                normalized["data_access_group_unique_name"]
                and normalized["data_access_group_unique_name"] == project.data_access_group_unique_name,
                normalized["data_access_group_id"] and normalized["data_access_group_id"] == project.data_access_group_id,
                normalized["no_assignment"] and not project.data_access_group_unique_name and not project.data_access_group_id,
            ]
        )
    return normalized


def dag_option_label(option: dict[str, Any], language: str) -> str:
    if option.get("no_assignment"):
        return tr("clinical_dag_no_assignment", language)
    return (
        str(option.get("data_access_group") or "").strip()
        or str(option.get("data_access_group_unique_name") or "").strip()
        or str(option.get("data_access_group_id") or "").strip()
        or tr("clinical_dag_none", language)
    )


def current_redcap_project_token(settings: Any) -> RedcapProjectToken | None:
    redcap = getattr(settings, "redcap", None)
    selected_project_id = getattr(redcap, "selected_project_id", None)
    if not selected_project_id:
        return None
    for project in getattr(redcap, "saved_project_tokens", []) or []:
        if project.project_id == str(selected_project_id):
            return project
    return None


def upsert_project_token(tokens: list[RedcapProjectToken], project: RedcapProjectToken) -> None:
    for index, item in enumerate(tokens):
        if item.project_id == project.project_id:
            tokens[index] = project
            return
    tokens.append(project)
