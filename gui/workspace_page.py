from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtWidgets import QComboBox, QLabel

from excel_import import (
    ExcelColumnMapping,
    ExcelImportOptions,
    build_procedural_column_mappings,
    import_patient_excel,
    read_excel_table,
    resolve_patient_id_column,
    sample_column_values,
)
from gui.i18n import tr
from gui.view_models import provider_label_for_key
from llm_provider import API_KEY_PROVIDER_NAMES, can_resolve_api_key, merge_llm_settings
from project_config import ProjectConfig
from release_profile import show_model_settings
from runtime_context import RuntimeContext
from submission_service import build_field_specs_by_name
from workspace_extraction import PatientExtractionResult, extract_patient_documents
from workspace_flow import (
    WorkspaceBundle,
    build_scoped_project_config,
    ensure_project_config,
    load_workspace_bundle,
    reload_workspace_bundle,
    save_workspace_bundle,
    summarize_selection,
)


@dataclass
class PendingPatientJob:
    queue_label: str
    patient_mode: str
    identifier_type: str | None
    identifier_value: str | None
    documents: list[str]
    config_snapshot: ProjectConfig


class ExcelImportWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        path: str,
        project_name: str,
        field_specs_by_name: dict[str, Any],
        options: ExcelImportOptions,
    ) -> None:
        super().__init__()
        self.path = path
        self.project_name = project_name
        self.field_specs_by_name = field_specs_by_name
        self.options = options

    def run(self) -> None:
        try:
            report = import_patient_excel(
                path=self.path,
                project_name=self.project_name,
                field_specs_by_name=self.field_specs_by_name,
                options=self.options,
                progress_callback=self.progress.emit,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(report)


class PatientQueueExtractionWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, *, jobs: list[PendingPatientJob]) -> None:
        super().__init__()
        self.jobs = jobs
        self._canceled = False

    def cancel(self) -> None:
        self._canceled = True

    def run(self) -> None:
        results: list[PatientExtractionResult] = []
        try:
            for index, job in enumerate(self.jobs, start=1):
                if self._canceled:
                    break
                self.progress.emit(index - 1, job.queue_label)
                result = extract_patient_documents(
                    config=job.config_snapshot,
                    queue_label=job.queue_label,
                    patient_mode=job.patient_mode,
                    identifier_type=job.identifier_type,
                    identifier_value=job.identifier_value,
                    documents=job.documents,
                )
                results.append(result)
            if not self._canceled:
                self.progress.emit(len(self.jobs), "done")
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit({"results": results, "canceled": self._canceled})


class ExcelImportUiBridge(QObject):
    def __init__(
        self,
        *,
        page: "WorkspacePage",
        progress,
        file_path: str,
        on_success,
    ) -> None:
        super().__init__(page.widget)
        self.page = page
        self.progress = progress
        self.file_path = file_path
        self.on_success = on_success

    @Slot(str)
    def handle_failure(self, error: str) -> None:
        self.progress.close()
        self.page.show_warning(
            tr("import_excel_patients", self.page.language),
            tr("excel_import_failed", self.page.language, error=error),
        )

    @Slot(object)
    def handle_success(self, report) -> None:
        self.progress.close()
        if not report.mapped_columns:
            self.page.show_warning(
                tr("import_excel_patients", self.page.language),
                tr("excel_import_no_mapped_columns", self.page.language),
            )
            return

        self.page.runtime.settings.ui.last_open_directory = str(Path(self.file_path).resolve().parent)
        self.page.runtime.settings_store.save(self.page.runtime.settings)
        self.page.latest_extraction_results = report.results
        summary_message = tr(
            "excel_import_summary",
            self.page.language,
            patients=len(report.results),
            mapped=len(report.mapped_columns),
            ignored=len(report.ignored_columns),
        )
        if report.mapping_warnings:
            summary_message = "\n\n".join(
                [
                    summary_message,
                    tr(
                        "excel_import_mapping_warnings",
                        self.page.language,
                        warnings="\n".join(report.mapping_warnings),
                    ),
                ]
            )
        if getattr(report, "value_normalization_warnings", None):
            summary_message = "\n\n".join(
                [
                    summary_message,
                    tr(
                        "excel_import_value_normalization_warnings",
                        self.page.language,
                        warnings="\n".join(report.value_normalization_warnings),
                    ),
                ]
            )
        normalized_value_count = int(getattr(report, "normalized_value_count", 0) or 0)
        if normalized_value_count:
            summary_message = "\n\n".join(
                [
                    summary_message,
                    tr(
                        "excel_import_value_normalization_summary",
                        self.page.language,
                        count=normalized_value_count,
                    ),
                ]
            )
        self.page.show_info(
            tr("import_excel_patients", self.page.language),
            summary_message,
        )
        if self.on_success is not None:
            self.on_success()
        self.page.show_extraction_results_dialog(report.results)

    @Slot(int, int, str)
    def handle_progress(self, current: int, total: int, stage: str) -> None:
        if total > 0:
            if self.progress.maximum() != total:
                self.progress.setRange(0, total)
            self.progress.setValue(max(0, min(current, total)))
        else:
            self.progress.setRange(0, 0)
        key = f"excel_import_progress_{stage}"
        self.progress.setLabelText(
            tr(key, self.page.language, current=current, total=total)
        )

    @Slot()
    def cleanup(self) -> None:
        self.page._excel_thread = None
        self.page._excel_worker = None
        self.page._excel_bridge = None


class PatientExtractionUiBridge(QObject):
    def __init__(self, *, page: "WorkspacePage", progress) -> None:
        super().__init__(page.widget)
        self.page = page
        self.progress = progress

    @Slot(int, str)
    def update_progress(self, current: int, patient: str) -> None:
        display_patient = tr("extraction_progress_done", self.page.language) if patient == "done" else patient
        self.progress.update_progress(current=current, patient=display_patient)

    @Slot(str)
    def handle_failure(self, error: str) -> None:
        self.progress.close()
        self.page.show_warning(
            tr("run_patient_queue", self.page.language),
            tr("extraction_failed", self.page.language, error=error),
        )

    @Slot(object)
    def handle_finished(self, payload: dict[str, Any]) -> None:
        self.progress.close()
        if payload.get("canceled"):
            return
        results = list(payload.get("results") or [])
        self.page.latest_extraction_results = results
        self.page.show_extraction_results_dialog(results)

    @Slot()
    def cleanup(self) -> None:
        self.page._extraction_thread = None
        self.page._extraction_worker = None
        self.page._extraction_bridge = None


def is_ollama_base_url(base_url: str) -> bool:
    normalized = base_url.strip().rstrip("/")
    return normalized.endswith(":11434") or normalized in {"http://localhost", "http://127.0.0.1"}


class WorkspacePage:
    def __init__(self, runtime: RuntimeContext) -> None:
        from PySide6.QtWidgets import (
            QFormLayout,
            QFrame,
            QHBoxLayout,
            QListWidget,
            QMessageBox,
            QPushButton,
            QVBoxLayout,
            QWidget,
        )

        self.runtime = runtime
        self.language = runtime.settings.ui.language
        self.show_model_settings = show_model_settings(runtime.app_config)
        self.widget = QWidget()
        self.bundle: WorkspaceBundle | None = None
        self.selected_form_names: set[str] = set()
        self.selected_field_names: set[str] = set()
        self._updating_form_states = False
        self._updating_field_states = False
        self.message_box_class = QMessageBox
        self.patient_queue_items: list[PendingPatientJob] = []
        self.latest_extraction_results: list[PatientExtractionResult] = []
        self._excel_thread: QThread | None = None
        self._excel_worker: ExcelImportWorker | None = None
        self._excel_bridge: ExcelImportUiBridge | None = None
        self._extraction_thread: QThread | None = None
        self._extraction_worker: PatientQueueExtractionWorker | None = None
        self._extraction_bridge: PatientExtractionUiBridge | None = None

        root = QVBoxLayout(self.widget)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        summary_card = QFrame()
        summary_card.setObjectName("HeroCard")
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(24, 24, 24, 24)
        summary_layout.setSpacing(8)

        title = QLabel(tr("workspace_title", self.language))
        title.setObjectName("TitleLabel")
        summary_layout.addWidget(title)

        selected_provider = runtime.settings.inference.selected_provider or runtime.inference_recommendation.mode
        provider_label = provider_label_for_key(selected_provider, self.language)
        summary = QLabel(tr("workspace_summary", self.language, provider=provider_label))
        summary.setWordWrap(True)
        summary.setObjectName("MutedLabel")
        summary_layout.addWidget(summary)
        root.addWidget(summary_card)

        config_card = QFrame()
        config_card.setObjectName("PanelCard")
        config_layout = QVBoxLayout(config_card)
        config_layout.setContentsMargins(20, 20, 20, 20)
        config_layout.setSpacing(12)
        config_title = QLabel(tr("project_config", self.language))
        config_title.setObjectName("SectionLabel")
        config_layout.addWidget(config_title)

        config_form = QFormLayout()
        self.redcap_project_combo = QComboBox()
        self.redcap_project_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.redcap_project_combo.setMinimumContentsLength(28)
        self.redcap_project_combo.currentIndexChanged.connect(self.select_saved_redcap_project)
        self.config_path_value = QLabel("-")
        self.config_path_value.setWordWrap(True)
        config_form.addRow(tr("active_redcap_project", self.language), self.redcap_project_combo)
        config_layout.addLayout(config_form)

        self.project_status = QLabel(tr("workspace_no_redcap_projects", self.language))
        self.project_status.setObjectName("MutedLabel")
        self.project_status.setWordWrap(True)
        config_layout.addWidget(self.project_status)

        self.selection_status = QLabel(tr("selection_empty", self.language))
        self.selection_status.setObjectName("MutedLabel")
        self.selection_status.setWordWrap(True)
        config_layout.addWidget(self.selection_status)
        root.addWidget(config_card)

        queue_row = QHBoxLayout()
        queue_row.setSpacing(18)

        docs_card = QFrame()
        docs_card.setObjectName("PanelCard")
        docs_layout = QVBoxLayout(docs_card)
        docs_layout.setContentsMargins(20, 20, 20, 20)
        docs_layout.setSpacing(12)
        docs_title = QLabel(tr("document_queue", self.language))
        docs_title.setObjectName("SectionLabel")
        docs_layout.addWidget(docs_title)

        docs_hint = QLabel(tr("document_queue_hint", self.language))
        docs_hint.setObjectName("MutedLabel")
        docs_hint.setWordWrap(True)
        docs_layout.addWidget(docs_hint)

        self.document_list = QListWidget()
        docs_layout.addWidget(self.document_list)

        docs_buttons = QHBoxLayout()
        self.add_documents_button = QPushButton(tr("add_documents", self.language))
        self.add_documents_button.clicked.connect(self.add_documents)
        self.clear_documents_button = QPushButton(tr("clear_documents", self.language))
        self.clear_documents_button.setProperty("secondary", True)
        self.clear_documents_button.clicked.connect(self.clear_document_draft)
        self.add_patient_button = QPushButton(tr("add_patient_to_queue", self.language))
        self.add_patient_button.clicked.connect(self.add_patient_to_queue)
        docs_buttons.addWidget(self.add_documents_button)
        docs_buttons.addWidget(self.clear_documents_button)
        docs_buttons.addWidget(self.add_patient_button)
        docs_layout.addLayout(docs_buttons)

        self.queue_status = QLabel(tr("no_documents", self.language))
        self.queue_status.setObjectName("MutedLabel")
        docs_layout.addWidget(self.queue_status)
        queue_row.addWidget(docs_card, 1)

        patient_card = QFrame()
        patient_card.setObjectName("PanelCard")
        patient_layout = QVBoxLayout(patient_card)
        patient_layout.setContentsMargins(20, 20, 20, 20)
        patient_layout.setSpacing(12)
        patient_title = QLabel(tr("patient_queue", self.language))
        patient_title.setObjectName("SectionLabel")
        patient_layout.addWidget(patient_title)

        patient_hint = QLabel(tr("patient_queue_hint", self.language))
        patient_hint.setObjectName("MutedLabel")
        patient_hint.setWordWrap(True)
        patient_layout.addWidget(patient_hint)

        self.patient_queue_list = QListWidget()
        patient_layout.addWidget(self.patient_queue_list)

        patient_buttons = QHBoxLayout()
        self.import_excel_button = QPushButton(tr("import_excel_patients", self.language))
        self.import_excel_button.clicked.connect(lambda checked=False: self.import_excel_patient_data())
        self.run_patient_queue_button = QPushButton(tr("run_patient_queue", self.language))
        self.run_patient_queue_button.clicked.connect(self.run_patient_queue_extraction)
        self.remove_patient_button = QPushButton(tr("remove_selected_patient", self.language))
        self.remove_patient_button.setProperty("secondary", True)
        self.remove_patient_button.clicked.connect(self.remove_selected_patient)
        patient_buttons.addWidget(self.import_excel_button)
        patient_buttons.addWidget(self.run_patient_queue_button)
        patient_buttons.addWidget(self.remove_patient_button)
        patient_buttons.addStretch(1)
        patient_layout.addLayout(patient_buttons)

        self.patient_queue_status = QLabel(tr("patient_queue_empty", self.language))
        self.patient_queue_status.setObjectName("MutedLabel")
        self.patient_queue_status.setWordWrap(True)
        patient_layout.addWidget(self.patient_queue_status)
        queue_row.addWidget(patient_card, 1)

        root.addLayout(queue_row)

        selection_row = QHBoxLayout()
        selection_row.setSpacing(18)

        forms_card = QFrame()
        forms_card.setObjectName("PanelCard")
        forms_layout = QVBoxLayout(forms_card)
        forms_layout.setContentsMargins(20, 20, 20, 20)
        forms_layout.setSpacing(12)
        forms_title = QLabel(tr("forms", self.language))
        forms_title.setObjectName("SectionLabel")
        forms_layout.addWidget(forms_title)
        self.form_list = QListWidget()
        self.form_list.itemChanged.connect(self.on_form_item_changed)
        self.form_list.currentItemChanged.connect(self.on_current_form_changed)
        forms_layout.addWidget(self.form_list)
        selection_row.addWidget(forms_card, 1)

        fields_card = QFrame()
        fields_card.setObjectName("PanelCard")
        fields_layout = QVBoxLayout(fields_card)
        fields_layout.setContentsMargins(20, 20, 20, 20)
        fields_layout.setSpacing(12)
        self.fields_title = QLabel(tr("fields", self.language))
        self.fields_title.setObjectName("SectionLabel")
        fields_layout.addWidget(self.fields_title)
        self.field_list = QListWidget()
        self.field_list.itemChanged.connect(self.on_field_item_changed)
        self.field_list.currentItemChanged.connect(self.on_current_field_changed)
        fields_layout.addWidget(self.field_list)
        self.field_info = QLabel("")
        self.field_info.setObjectName("MutedLabel")
        self.field_info.setWordWrap(True)
        fields_layout.addWidget(self.field_info)
        selection_row.addWidget(fields_card, 1)

        root.addLayout(selection_row)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(12)
        self.scan_settings_button = QPushButton(tr("scan_settings", self.language))
        self.scan_settings_button.setToolTip(tr("scan_settings_tooltip", self.language))
        self.scan_settings_button.clicked.connect(self.open_scan_settings_dialog)
        self.project_llm_button = QPushButton(tr("open_project_llm_settings", self.language))
        self.project_llm_button.setToolTip(tr("project_llm_tooltip", self.language))
        self.project_llm_button.setProperty("secondary", True)
        self.project_llm_button.clicked.connect(lambda checked=False: self.edit_project_llm_settings(self.widget))
        self.project_llm_button.setVisible(self.show_model_settings)
        self.extra_fields_button = QPushButton(tr("extra_fields", self.language))
        self.extra_fields_button.setToolTip(tr("extra_fields_tooltip", self.language))
        self.extra_fields_button.clicked.connect(self.manage_extra_fields)
        actions_row.addWidget(self.scan_settings_button)
        if self.show_model_settings:
            actions_row.addWidget(self.project_llm_button)
        actions_row.addWidget(self.extra_fields_button)
        actions_row.addStretch(1)
        root.addLayout(actions_row)

        self.refresh_redcap_projects()

    def refresh_redcap_projects(self) -> None:
        settings = self.runtime.settings
        current_project_id = settings.redcap.selected_project_id
        self.redcap_project_combo.blockSignals(True)
        self.redcap_project_combo.clear()
        for project in settings.redcap.saved_project_tokens:
            self.redcap_project_combo.addItem(project.project_name, project.project_id)
        if current_project_id:
            index = self.redcap_project_combo.findData(current_project_id)
            if index >= 0:
                self.redcap_project_combo.setCurrentIndex(index)
        elif self.redcap_project_combo.count() > 0:
            self.redcap_project_combo.setCurrentIndex(0)
        self.redcap_project_combo.blockSignals(False)

        if self.redcap_project_combo.count() == 0:
            self.clear_bundle_state(tr("workspace_no_redcap_projects", self.language))
            return
        self.select_saved_redcap_project()

    def select_saved_redcap_project(self) -> None:
        selected_project_id = self.redcap_project_combo.currentData()
        if not selected_project_id:
            self.clear_bundle_state(tr("workspace_no_redcap_projects", self.language))
            return
        for project in self.runtime.settings.redcap.saved_project_tokens:
            if project.project_id != str(selected_project_id):
                continue
            self.runtime.settings.redcap.selected_project_id = project.project_id
            self.runtime.settings.redcap.selected_project_name = project.project_name
            self.runtime.settings.redcap.selected_project_token_secret_name = project.token_secret_name
            self.runtime.settings.redcap.api_url = project.api_url
            self.runtime.settings_store.save(self.runtime.settings)
            self.load_selected_project_bundle(project.token_secret_name)
            return
        self.clear_bundle_state(tr("workspace_no_redcap_projects", self.language))

    def load_selected_project_bundle(self, token_secret_name: str) -> None:
        selected_project_id = self.runtime.settings.redcap.selected_project_id
        selected_project_name = self.runtime.settings.redcap.selected_project_name
        api_url = self.runtime.settings.redcap.api_url
        api_token = self.runtime.secrets_store.get(token_secret_name, "") or ""
        previous_project_id = self.bundle.config.project_id if self.bundle else None
        project_changed = previous_project_id != selected_project_id
        if project_changed:
            self.patient_queue_items = []
            self.latest_extraction_results = []
            self.document_list.clear()
            self.queue_status.setText(tr("no_documents", self.language))
            self.refresh_patient_queue_list()

        if not selected_project_id or not selected_project_name or not api_url:
            self.clear_bundle_state(tr("workspace_project_missing_settings", self.language))
            return
        if not api_token:
            self.clear_bundle_state(tr("workspace_project_missing_token", self.language))
            return

        try:
            config_path = ensure_project_config(
                app_home=self.runtime.app_home,
                project_id=selected_project_id,
                project_name=selected_project_name,
                api_url=api_url,
                api_token=api_token,
                default_llm_settings=self.build_project_llm_defaults(),
            )
            self.bundle = load_workspace_bundle(config_path)
        except Exception as exc:
            self.clear_bundle_state(tr("config_load_error", self.language, error=str(exc)))
            return

        self.runtime.settings.preferred_project_config_path = str(config_path)
        self.runtime.settings_store.save(self.runtime.settings)
        self.config_path_value.setText(str(config_path))
        self.load_selection_state_from_config()
        self.populate_form_list()
        self.project_status.setText(tr("config_loaded", self.language, project=self.bundle.config.project_name))
        self.refresh_selection_status()

    def clear_bundle_state(self, message: str) -> None:
        self.bundle = None
        self.selected_form_names = set()
        self.selected_field_names = set()
        self.patient_queue_items = []
        self.latest_extraction_results = []
        self.form_list.clear()
        self.field_list.clear()
        self.config_path_value.setText("-")
        self.project_status.setText(message)
        self.selection_status.setText(message)
        self.fields_title.setText(tr("fields", self.language))
        self.field_info.setText("")
        self.document_list.clear()
        self.queue_status.setText(tr("no_documents", self.language))
        self.refresh_patient_queue_list()

    def load_selection_state_from_config(self) -> None:
        if not self.bundle:
            self.selected_form_names = set()
            self.selected_field_names = set()
            return
        self.selected_form_names = set(self.bundle.config.target_forms or [])
        self.selected_field_names = set(self.bundle.config.target_fields or [])

    def populate_form_list(self) -> None:
        from PySide6.QtWidgets import QListWidgetItem

        self._updating_form_states = True
        self.form_list.clear()
        if not self.bundle:
            self._updating_form_states = False
            return
        for form_name in self.bundle.form_names:
            item = QListWidgetItem(self.bundle.form_display_name(form_name))
            item.setData(Qt.ItemDataRole.UserRole, form_name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(self.form_check_state(form_name))
            self.form_list.addItem(item)
        self._updating_form_states = False
        if self.form_list.count() > 0:
            self.form_list.setCurrentRow(0)
        else:
            self.populate_field_list(None)

    def form_check_state(self, form_name: str) -> Qt.CheckState:
        if form_name in self.selected_form_names:
            return Qt.CheckState.Checked
        if not self.bundle:
            return Qt.CheckState.Unchecked
        selected_count = sum(
            1 for field_name in self.bundle.field_names_for_form(form_name) if field_name in self.selected_field_names
        )
        return Qt.CheckState.PartiallyChecked if selected_count else Qt.CheckState.Unchecked

    def on_form_item_changed(self, item) -> None:
        if self._updating_form_states or not self.bundle:
            return
        form_name = str(item.data(Qt.ItemDataRole.UserRole))
        field_names = set(self.bundle.field_names_for_form(form_name))
        state = item.checkState()
        if state == Qt.CheckState.Checked:
            self.selected_form_names.add(form_name)
            self.selected_field_names.difference_update(field_names)
        elif state == Qt.CheckState.Unchecked:
            self.selected_form_names.discard(form_name)
            self.selected_field_names.difference_update(field_names)
        else:
            return
        self.persist_selection_to_config()
        if self.current_form_name() == form_name:
            self.populate_field_list(form_name)
        self.refresh_selection_status()

    def on_current_form_changed(self, current, previous) -> None:
        form_name = str(current.data(Qt.ItemDataRole.UserRole)) if current is not None else None
        self.populate_field_list(form_name)

    def populate_field_list(self, form_name: str | None) -> None:
        from PySide6.QtWidgets import QListWidgetItem

        self._updating_field_states = True
        self.field_list.clear()
        if not self.bundle or not form_name:
            self._updating_field_states = False
            self.fields_title.setText(tr("fields", self.language))
            self.field_info.setText("")
            return

        self.fields_title.setText(tr("fields_for_form", self.language, form=self.bundle.form_display_name(form_name)))
        for field in self.bundle.grouped_fields.get(form_name, []):
            item = QListWidgetItem(f"{field.field_label} | {field.field_name}")
            item.setData(Qt.ItemDataRole.UserRole, field.field_name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if self.is_field_selected(form_name, field.field_name) else Qt.CheckState.Unchecked)
            self.field_list.addItem(item)
        self._updating_field_states = False
        if self.field_list.count() > 0:
            self.field_list.setCurrentRow(0)
        else:
            self.field_info.setText("")

    def is_field_selected(self, form_name: str, field_name: str) -> bool:
        return form_name in self.selected_form_names or field_name in self.selected_field_names

    def on_field_item_changed(self, item) -> None:
        if self._updating_field_states or not self.bundle:
            return
        form_name = self.current_form_name()
        if not form_name:
            return
        field_name = str(item.data(Qt.ItemDataRole.UserRole))
        fields_in_form = self.bundle.field_names_for_form(form_name)

        if form_name in self.selected_form_names:
            if item.checkState() == Qt.CheckState.Unchecked:
                self.selected_form_names.discard(form_name)
                for name in fields_in_form:
                    if name != field_name:
                        self.selected_field_names.add(name)
                self.selected_field_names.discard(field_name)
        else:
            if item.checkState() == Qt.CheckState.Checked:
                self.selected_field_names.add(field_name)
            else:
                self.selected_field_names.discard(field_name)

            selected_in_form = {name for name in fields_in_form if name in self.selected_field_names}
            if fields_in_form and len(selected_in_form) == len(fields_in_form):
                self.selected_form_names.add(form_name)
                for name in fields_in_form:
                    self.selected_field_names.discard(name)

        self.persist_selection_to_config()
        self.update_form_item_state(form_name)
        self.refresh_selection_status()

    def on_current_field_changed(self, current, previous) -> None:
        if current is None or not self.bundle:
            self.field_info.setText("")
            return
        field = self.find_field(self.current_form_name(), str(current.data(Qt.ItemDataRole.UserRole)))
        if field is None or not field.choices_options:
            self.field_info.setText("")
            return
        preview = ", ".join(f"{choice.code}: {choice.label}" for choice in field.choices_options[:6])
        self.field_info.setText(tr("field_choices_info", self.language, choices=preview))

    def update_form_item_state(self, form_name: str) -> None:
        self._updating_form_states = True
        for index in range(self.form_list.count()):
            item = self.form_list.item(index)
            if str(item.data(Qt.ItemDataRole.UserRole)) == form_name:
                item.setCheckState(self.form_check_state(form_name))
                break
        self._updating_form_states = False

    def persist_selection_to_config(self) -> None:
        if not self.bundle:
            return
        self.bundle.config.target_forms = sorted(self.selected_form_names)
        self.bundle.config.target_fields = sorted(self.selected_field_names)
        save_workspace_bundle(self.bundle)

    def effective_selected_forms(self) -> set[str]:
        forms = set(self.selected_form_names)
        if not self.bundle:
            return forms
        for form_name in self.bundle.form_names:
            if any(field_name in self.selected_field_names for field_name in self.bundle.field_names_for_form(form_name)):
                forms.add(form_name)
        return forms

    def refresh_selection_status(self) -> None:
        if not self.bundle:
            self.selection_status.setText(tr("selection_empty", self.language))
            return
        effective_fields = self.selected_field_names | {
            field_name
            for form_name in self.selected_form_names
            for field_name in self.bundle.field_names_for_form(form_name)
        }
        forms_selected, forms_total, fields_selected, fields_total = summarize_selection(
            self.bundle,
            self.effective_selected_forms(),
            effective_fields,
        )
        summary = tr(
            "selection_counts",
            self.language,
            forms_selected=forms_selected,
            forms_total=forms_total,
            fields_selected=fields_selected,
            fields_total=fields_total,
        )
        scoped = build_scoped_project_config(self.bundle, self.selected_form_names, self.selected_field_names)
        self.project_status.setText(tr("selected_project", self.language, project=scoped.project_name))
        self.selection_status.setText(tr("selection_ready", self.language, summary=summary))

    def current_form_name(self) -> str | None:
        current = self.form_list.currentItem()
        return str(current.data(Qt.ItemDataRole.UserRole)) if current is not None else None

    def current_field_name(self) -> str | None:
        current = self.field_list.currentItem()
        return str(current.data(Qt.ItemDataRole.UserRole)) if current is not None else None

    def open_scan_settings_dialog(self) -> None:
        from PySide6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QFrame,
            QPushButton,
            QVBoxLayout,
        )

        if not self.bundle:
            return

        dialog = QDialog(self.widget)
        dialog.setWindowTitle(tr("scan_settings", self.language))
        layout = QVBoxLayout(dialog)
        layout.setSpacing(14)

        info = QLabel(tr("scan_settings_dialog", self.language))
        info.setWordWrap(True)
        layout.addWidget(info)

        form_name = self.resolve_form_rule_target()
        field_name = self.resolve_field_rule_target(form_name)
        form_card = QFrame()
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(12, 12, 12, 12)
        form_layout.setSpacing(8)
        form_title = QLabel(tr("selected_form_rule_title", self.language))
        form_title.setObjectName("SectionLabel")
        form_layout.addWidget(form_title)
        form_summary = QLabel(
            tr(
                "selected_form_summary",
                self.language,
                form=self.bundle.form_display_name(form_name) if form_name else tr("not_selected", self.language),
            )
        )
        form_summary.setWordWrap(True)
        form_layout.addWidget(form_summary)
        form_button = QPushButton(tr("open_selected_form_rules", self.language))
        form_button.setToolTip(tr("selected_form_rules_tooltip", self.language))
        form_layout.addWidget(form_button)
        layout.addWidget(form_card)

        field_card = QFrame()
        field_layout = QVBoxLayout(field_card)
        field_layout.setContentsMargins(12, 12, 12, 12)
        field_layout.setSpacing(8)
        field_title = QLabel(tr("selected_field_rule_title", self.language))
        field_title.setObjectName("SectionLabel")
        field_layout.addWidget(field_title)
        field_summary = QLabel(
            tr(
                "selected_field_summary",
                self.language,
                field=self.field_display_name(form_name, field_name) or tr("not_selected", self.language),
            )
        )
        field_summary.setWordWrap(True)
        field_layout.addWidget(field_summary)
        field_button = QPushButton(tr("open_selected_field_rules", self.language))
        field_button.setToolTip(tr("selected_field_rules_tooltip", self.language))
        field_layout.addWidget(field_button)
        layout.addWidget(field_card)

        def open_form_rules() -> None:
            dialog.accept()
            self.edit_form_rules(self.widget)

        def open_field_rules() -> None:
            dialog.accept()
            self.edit_field_rules(self.widget)

        form_button.clicked.connect(open_form_rules)
        field_button.clicked.connect(open_field_rules)

        button_box = QDialogButtonBox()
        close_button = button_box.addButton(tr("close_button", self.language), QDialogButtonBox.ButtonRole.RejectRole)
        close_button.clicked.connect(dialog.reject)
        layout.addWidget(button_box)
        dialog.exec()

    def edit_project_llm_settings(self, parent=None) -> None:
        from PySide6.QtWidgets import (
            QCheckBox,
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QDoubleSpinBox,
            QFormLayout,
            QLineEdit,
            QMessageBox,
            QSpinBox,
            QVBoxLayout,
        )

        if not self.bundle or not self.show_model_settings:
            return

        dialog = QDialog(parent or self.widget)
        dialog.setWindowTitle(tr("project_llm_settings", self.language))
        dialog.setMinimumWidth(560)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        info = QLabel(tr("project_llm_settings_desc", self.language))
        info.setWordWrap(True)
        layout.addWidget(info)

        current_settings = dict(self.bundle.config.llm or {})
        current_provider = str(current_settings.get("provider", "ollama")).strip().lower()
        current_base_url = str(current_settings.get("base_url", "") or "").strip()
        if current_provider == "ollama":
            inference_provider = self.runtime.settings.inference.selected_provider or self.runtime.inference_recommendation.mode
            provider_mode = "remote_ollama" if inference_provider == "remote_ollama" else "local_ollama"
        else:
            provider_mode = "openai_compatible"

        form = QFormLayout()
        form.setSpacing(10)

        provider_input = QComboBox()
        provider_input.addItem(tr("provider_local_ollama", self.language), "local_ollama")
        provider_input.addItem(tr("provider_remote_ollama", self.language), "remote_ollama")
        provider_input.addItem(tr("provider_openai_compatible", self.language), "openai_compatible")
        index = provider_input.findData(provider_mode)
        if index >= 0:
            provider_input.setCurrentIndex(index)

        local_url_input = QLineEdit(
            current_base_url or self.runtime.settings.inference.local_ollama_base_url or "http://127.0.0.1:11434"
        )
        remote_url_input = QLineEdit(
            current_base_url or self.runtime.settings.inference.remote_ollama_base_url or ""
        )
        api_url_input = QLineEdit(
            current_base_url or self.runtime.settings.inference.openai_compatible_base_url or ""
        )
        model_input = QLineEdit(
            str(
                current_settings.get("model")
                or self.runtime.settings.inference.openai_compatible_model
                or "qwen3.5:9b"
            )
        )
        api_key_input = QLineEdit("")
        api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_key_secret_name = self.runtime.settings.inference.api_key_secret_name
        if self.runtime.secrets_store.has(api_key_secret_name):
            api_key_input.setPlaceholderText(tr("api_key_saved_placeholder", self.language))

        temperature_input = QDoubleSpinBox()
        temperature_input.setRange(0.0, 2.0)
        temperature_input.setDecimals(2)
        temperature_input.setSingleStep(0.1)
        temperature_input.setValue(float(current_settings.get("temperature", 0)))

        max_tokens_input = QSpinBox()
        max_tokens_input.setRange(128, 131072)
        max_tokens_input.setSingleStep(512)
        max_tokens_input.setValue(int(current_settings.get("max_tokens", 8192)))

        timeout_input = QSpinBox()
        timeout_input.setRange(10, 3600)
        timeout_input.setValue(int(current_settings.get("timeout_seconds", 600)))

        think_input = QCheckBox(tr("llm_thinking_enabled", self.language))
        think_input.setChecked(bool(current_settings.get("think", False)))
        think_input.setToolTip(tr("llm_thinking_warning", self.language))

        num_ctx_input = QSpinBox()
        num_ctx_input.setRange(1024, 262144)
        num_ctx_input.setSingleStep(1024)
        num_ctx_input.setValue(int((current_settings.get("options") or {}).get("num_ctx", 32768)))

        use_json_schema_input = QCheckBox(tr("llm_use_json_schema", self.language))
        use_json_schema_input.setChecked(bool(current_settings.get("use_json_schema", True)))

        provider_label = QLabel(tr("provider_label", self.language))
        local_url_label = QLabel(tr("local_ollama_url", self.language))
        remote_url_label = QLabel(tr("remote_ollama_url", self.language))
        api_url_label = QLabel(tr("api_base_url", self.language))
        model_label = QLabel(tr("api_model", self.language))
        api_key_label = QLabel(tr("api_key", self.language))
        temperature_label = QLabel(tr("llm_temperature", self.language))
        max_tokens_label = QLabel(tr("llm_max_tokens", self.language))
        timeout_label = QLabel(tr("llm_timeout", self.language))
        num_ctx_label = QLabel(tr("llm_num_ctx", self.language))

        form.addRow(provider_label, provider_input)
        form.addRow(local_url_label, local_url_input)
        form.addRow(remote_url_label, remote_url_input)
        form.addRow(api_url_label, api_url_input)
        form.addRow(model_label, model_input)
        form.addRow(api_key_label, api_key_input)
        form.addRow(temperature_label, temperature_input)
        form.addRow(max_tokens_label, max_tokens_input)
        form.addRow(timeout_label, timeout_input)
        form.addRow(num_ctx_label, num_ctx_input)
        form.addRow("", use_json_schema_input)
        layout.addLayout(form)

        thinking_warning = QLabel(tr("llm_thinking_warning", self.language))
        thinking_warning.setWordWrap(True)
        thinking_warning.setObjectName("MutedLabel")
        thinking_warning.setVisible(bool(think_input.isChecked()))
        form.addRow("", think_input)
        layout.addWidget(thinking_warning)

        def update_provider_fields() -> None:
            provider_value = str(provider_input.currentData())
            is_local = provider_value == "local_ollama"
            is_remote = provider_value == "remote_ollama"
            is_api = provider_value == "openai_compatible"

            local_url_label.setVisible(is_local)
            local_url_input.setVisible(is_local)
            remote_url_label.setVisible(is_remote)
            remote_url_input.setVisible(is_remote)
            api_url_label.setVisible(is_api)
            api_url_input.setVisible(is_api)
            api_key_label.setVisible(is_api)
            api_key_input.setVisible(is_api)
            use_json_schema_input.setVisible(is_api)

            num_ctx_label.setVisible(not is_api)
            num_ctx_input.setVisible(not is_api)
            think_input.setVisible(not is_api)
            thinking_warning.setVisible(not is_api and bool(think_input.isChecked()))

        provider_input.currentIndexChanged.connect(update_provider_fields)
        think_input.toggled.connect(lambda checked: thinking_warning.setVisible(provider_input.currentData() != "openai_compatible" and checked))
        update_provider_fields()

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.rejected.connect(dialog.reject)
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setAutoDefault(False)
            ok_button.setDefault(False)
        layout.addWidget(button_box)

        def validate_and_accept() -> None:
            provider_value = str(provider_input.currentData())
            if provider_value == "local_ollama":
                base_url = local_url_input.text().strip()
                if not base_url:
                    QMessageBox.warning(dialog, tr("project_llm_settings", self.language), tr("llm_url_required", self.language))
                    return
                payload: dict[str, Any] = {
                    "provider": "ollama",
                    "base_url": base_url,
                    "model": model_input.text().strip() or "qwen3.5:9b",
                    "temperature": float(temperature_input.value()),
                    "max_tokens": int(max_tokens_input.value()),
                    "timeout_seconds": int(timeout_input.value()),
                    "stream": True,
                    "think": bool(think_input.isChecked()),
                    "options": {"num_ctx": int(num_ctx_input.value())},
                }
            elif provider_value == "remote_ollama":
                base_url = remote_url_input.text().strip()
                if not base_url:
                    QMessageBox.warning(dialog, tr("project_llm_settings", self.language), tr("llm_url_required", self.language))
                    return
                payload = {
                    "provider": "ollama",
                    "base_url": base_url,
                    "model": model_input.text().strip() or "qwen3.5:9b",
                    "temperature": float(temperature_input.value()),
                    "max_tokens": int(max_tokens_input.value()),
                    "timeout_seconds": int(timeout_input.value()),
                    "stream": True,
                    "think": bool(think_input.isChecked()),
                    "options": {"num_ctx": int(num_ctx_input.value())},
                }
            else:
                base_url = api_url_input.text().strip()
                if not base_url:
                    QMessageBox.warning(dialog, tr("project_llm_settings", self.language), tr("llm_url_required", self.language))
                    return
                payload = {
                    "provider": "openai_compatible",
                    "base_url": base_url,
                    "model": model_input.text().strip() or "qwen/qwen3.5-9b",
                    "temperature": float(temperature_input.value()),
                    "max_tokens": int(max_tokens_input.value()),
                    "timeout_seconds": int(timeout_input.value()),
                    "api_key_secret_name": self.runtime.settings.inference.api_key_secret_name,
                    "use_json_schema": bool(use_json_schema_input.isChecked()),
                }
                api_key = api_key_input.text().strip()
                if api_key:
                    self.runtime.secrets_store.set(self.runtime.settings.inference.api_key_secret_name, api_key)
                    api_key_input.clear()
                    api_key_input.setPlaceholderText(tr("api_key_saved_placeholder", self.language))

            self.bundle.config.llm = payload
            dialog.accept()

        button_box.accepted.connect(validate_and_accept)

        if dialog.exec() == 0:
            return
        self.save_bundle_and_reload(tr("project_llm_saved", self.language), parent=parent)

    def edit_form_rules(self, parent=None) -> None:
        if not self.bundle:
            return
        form_name = self.resolve_form_rule_target()
        if not form_name:
            self.show_warning(tr("selected_form_rules", self.language), tr("form_rules_require_selection", self.language), parent)
            return
        self.edit_form_rules_for(form_name, parent=parent)

    def edit_form_rules_for(self, form_name: str, parent=None) -> None:
        if not self.bundle:
            return
        payload = self.edit_override_payload(
            title=tr("selected_form_rules", self.language),
            subject_label=self.bundle.form_display_name(form_name),
            payload=self.bundle.config.form_overrides.get(form_name, {}),
            parent=parent,
        )
        if payload is None:
            return
        if payload:
            self.bundle.config.form_overrides[form_name] = payload
        else:
            self.bundle.config.form_overrides.pop(form_name, None)
        self.save_bundle_and_reload(tr("form_override_saved", self.language, form=self.bundle.form_display_name(form_name)), parent=parent)

    def edit_field_rules(self, parent=None) -> None:
        if not self.bundle:
            return
        form_name = self.resolve_form_rule_target()
        field_name = self.resolve_field_rule_target(form_name)
        if not form_name or not field_name:
            self.show_warning(tr("selected_field_rules", self.language), tr("field_rules_require_selection", self.language), parent)
            return
        self.edit_field_rules_for(form_name, field_name, parent=parent)

    def edit_field_rules_for(self, form_name: str, field_name: str, parent=None) -> None:
        if not self.bundle:
            return
        payload = self.edit_override_payload(
            title=tr("selected_field_rules", self.language),
            subject_label=self.field_display_name(form_name, field_name) or field_name,
            payload=self.bundle.config.field_overrides.get(field_name, {}),
            parent=parent,
        )
        if payload is None:
            return
        if payload:
            self.bundle.config.field_overrides[field_name] = payload
        else:
            self.bundle.config.field_overrides.pop(field_name, None)
        self.save_bundle_and_reload(tr("field_override_saved", self.language, field=field_name), parent=parent)

    def edit_override_payload(self, *, title: str, subject_label: str, payload: dict, parent=None) -> dict | None:
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

        dialog = QDialog(parent or self.widget)
        dialog.setWindowTitle(title)
        dialog.setMinimumWidth(560)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        info = QLabel(tr("override_editor_desc", self.language, name=subject_label))
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        form.setSpacing(10)

        prompt_append_input = QPlainTextEdit()
        prompt_append_input.setPlainText(str(payload.get("prompt_append", "") or ""))
        prompt_append_input.setMinimumHeight(96)

        cardinality_input = QComboBox()
        cardinality_input.addItem(tr("override_use_default", self.language), "")
        cardinality_input.addItem("single", "single")
        cardinality_input.addItem("multiple", "multiple")
        cardinality_input.addItem("repeat_entity", "repeat_entity")
        self._set_combo_value(cardinality_input, str(payload.get("cardinality", "") or ""))

        selection_rule_input = QComboBox()
        selection_rule_input.addItem(tr("override_use_default", self.language), "")
        for value in ["latest", "earliest", "highest", "lowest", "all", "manual_review"]:
            selection_rule_input.addItem(value, value)
        self._set_combo_value(selection_rule_input, str(payload.get("selection_rule", "") or ""))

        max_candidates_enabled = QCheckBox(tr("override_enable_max_candidates", self.language))
        max_candidates_input = QSpinBox()
        max_candidates_input.setRange(1, 50)
        max_candidates_value = payload.get("max_candidates")
        max_candidates_enabled.setChecked(max_candidates_value is not None)
        max_candidates_input.setValue(int(max_candidates_value or 3))
        max_candidates_input.setEnabled(max_candidates_enabled.isChecked())

        post_processing = payload.get("post_processing") or []
        limit_length_value = self.extract_limit_output_length(post_processing)
        limit_length_enabled = QCheckBox(tr("override_limit_output_length", self.language))
        limit_length_enabled.setChecked(limit_length_value is not None)
        limit_length_input = QSpinBox()
        limit_length_input.setRange(1, 5000)
        limit_length_input.setValue(int(limit_length_value or 100))
        limit_length_input.setEnabled(limit_length_enabled.isChecked())

        form.addRow(tr("override_prompt_append", self.language), prompt_append_input)
        form.addRow(tr("override_cardinality", self.language), cardinality_input)
        form.addRow(tr("override_selection_rule", self.language), selection_rule_input)
        form.addRow("", max_candidates_enabled)
        form.addRow(tr("override_max_candidates", self.language), max_candidates_input)
        form.addRow("", limit_length_enabled)
        form.addRow(tr("override_limit_length_value", self.language), limit_length_input)
        layout.addLayout(form)

        max_candidates_enabled.toggled.connect(max_candidates_input.setEnabled)
        limit_length_enabled.toggled.connect(limit_length_input.setEnabled)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.rejected.connect(dialog.reject)
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setAutoDefault(False)
            ok_button.setDefault(False)
        layout.addWidget(button_box)

        result_payload: dict | None = None

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

            post_processing_items = self.merge_post_processing(
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

    def manage_extra_fields(self) -> None:
        from PySide6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QHBoxLayout,
            QListWidget,
            QListWidgetItem,
            QPushButton,
            QVBoxLayout,
        )

        if not self.bundle:
            return

        dialog = QDialog(self.widget)
        dialog.setWindowTitle(tr("extra_fields", self.language))
        layout = QVBoxLayout(dialog)

        info = QLabel(tr("extra_fields_dialog", self.language))
        info.setWordWrap(True)
        layout.addWidget(info)

        list_widget = QListWidget()
        source_field_name = self.bundle.config.dictionary_legend.get("field_name", "Variable / Field Name")
        source_form_name = self.bundle.config.dictionary_legend.get("form_name", "Form Name")
        source_field_label = self.bundle.config.dictionary_legend.get("field_label", "Field Label")
        for item in self.bundle.config.append_fields:
            field_name = str(item.get(source_field_name, "")).strip()
            form_name = str(item.get(source_form_name, "")).strip()
            field_label = str(item.get(source_field_label, "")).strip()
            list_item = QListWidgetItem(f"{self.bundle.form_display_name(form_name)} | {field_label} | {field_name}")
            list_item.setData(Qt.ItemDataRole.UserRole, field_name)
            list_widget.addItem(list_item)
        layout.addWidget(list_widget)

        changed = {"value": False}
        buttons_row = QHBoxLayout()
        add_button = QPushButton(tr("add_extra_field", self.language))
        add_button.setToolTip(tr("add_extra_field_tooltip", self.language))
        edit_button = QPushButton(tr("edit_extra_field", self.language))
        edit_button.setToolTip(tr("edit_extra_field_tooltip", self.language))
        remove_button = QPushButton(tr("remove_extra_field", self.language))
        remove_button.setProperty("secondary", True)
        buttons_row.addWidget(add_button)
        buttons_row.addWidget(edit_button)
        buttons_row.addWidget(remove_button)
        layout.addLayout(buttons_row)

        def add_item() -> None:
            payload = self.prompt_extra_field()
            if not payload:
                return
            self.bundle.config.append_fields.append(payload)
            changed["value"] = True
            self.refresh_extra_field_list_widget(list_widget)
            self.select_extra_field_in_list(list_widget, str(payload.get(source_field_name, "")).strip())
            self.show_info(tr("extra_fields", self.language), tr("append_field_added", self.language), dialog)

        def edit_item() -> None:
            current = list_widget.currentItem()
            if current is None:
                return
            field_name = str(current.data(Qt.ItemDataRole.UserRole))
            existing = self.find_append_field(field_name)
            if existing is None:
                return
            payload = self.prompt_extra_field(existing)
            if not payload:
                return
            updated: list[dict[str, str]] = []
            for item in self.bundle.config.append_fields:
                existing_name = str(item.get(source_field_name, "")).strip()
                updated.append(payload if existing_name == field_name else item)
            self.bundle.config.append_fields = updated
            changed["value"] = True
            self.refresh_extra_field_list_widget(list_widget)
            updated_name = str(payload.get(source_field_name, "")).strip()
            self.select_extra_field_in_list(list_widget, updated_name)
            self.show_info(tr("extra_fields", self.language), tr("append_field_updated", self.language, field=updated_name), dialog)

        def remove_item() -> None:
            current = list_widget.currentItem()
            if current is None:
                return
            field_name = str(current.data(Qt.ItemDataRole.UserRole))
            self.bundle.config.append_fields = [
                item for item in self.bundle.config.append_fields if str(item.get(source_field_name, "")).strip() != field_name
            ]
            changed["value"] = True
            self.refresh_extra_field_list_widget(list_widget)
            self.show_info(tr("extra_fields", self.language), tr("append_field_removed", self.language, field=field_name), dialog)

        add_button.clicked.connect(add_item)
        edit_button.clicked.connect(edit_item)
        remove_button.clicked.connect(remove_item)

        button_box = QDialogButtonBox()
        close_button = button_box.addButton(tr("close_button", self.language), QDialogButtonBox.ButtonRole.RejectRole)
        close_button.clicked.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.exec()
        if changed["value"]:
            self.save_bundle_and_reload(tr("append_fields_saved", self.language), parent=dialog)

    def select_extra_field_in_list(self, list_widget, field_name: str) -> None:
        for index in range(list_widget.count()):
            item = list_widget.item(index)
            if str(item.data(Qt.ItemDataRole.UserRole)) == field_name:
                list_widget.setCurrentRow(index)
                return

    def refresh_extra_field_list_widget(self, list_widget) -> None:
        if not self.bundle:
            return
        source_field_name = self.bundle.config.dictionary_legend.get("field_name", "Variable / Field Name")
        source_form_name = self.bundle.config.dictionary_legend.get("form_name", "Form Name")
        source_field_label = self.bundle.config.dictionary_legend.get("field_label", "Field Label")
        list_widget.clear()
        for item in self.bundle.config.append_fields:
            field_name = str(item.get(source_field_name, "")).strip()
            form_name = str(item.get(source_form_name, "")).strip()
            field_label = str(item.get(source_field_label, "")).strip()
            from PySide6.QtWidgets import QListWidgetItem
            list_item = QListWidgetItem(f"{self.bundle.form_display_name(form_name)} | {field_label} | {field_name}")
            list_item.setData(Qt.ItemDataRole.UserRole, field_name)
            list_widget.addItem(list_item)

    def prompt_extra_field(self, existing: dict[str, str] | None = None) -> dict[str, str] | None:
        from PySide6.QtWidgets import (
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QFormLayout,
            QHBoxLayout,
            QLineEdit,
            QListWidget,
            QListWidgetItem,
            QPlainTextEdit,
            QPushButton,
            QVBoxLayout,
        )

        if not self.bundle:
            return None

        legend = self.bundle.config.dictionary_legend
        source_field_name = legend.get("field_name", "Variable / Field Name")
        source_form_name = legend.get("form_name", "Form Name")
        source_field_label = legend.get("field_label", "Field Label")
        source_field_type = legend.get("field_type", "Field Type")
        source_field_note = legend.get("field_note", "Field Note")
        source_choices = legend.get("choices", "Choices, Calculations, OR Slider Labels")

        dialog = QDialog(self.widget)
        dialog.setWindowTitle(tr("add_extra_field", self.language) if existing is None else tr("edit_extra_field", self.language))
        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        form_name_input = QComboBox()
        for form_name in self.bundle.form_names:
            form_name_input.addItem(self.bundle.form_display_name(form_name), form_name)
        initial_form = str(existing.get(source_form_name, "")) if existing else self.current_form_name()
        if initial_form:
            index = form_name_input.findData(initial_form)
            if index >= 0:
                form_name_input.setCurrentIndex(index)

        field_name_input = QLineEdit(str(existing.get(source_field_name, "")) if existing else "")
        field_label_input = QLineEdit(str(existing.get(source_field_label, "")) if existing else "")
        field_type_input = QComboBox()
        field_type_input.addItems(["text", "radio", "dropdown", "checkbox", "yesno"])
        if existing:
            idx = field_type_input.findText(str(existing.get(source_field_type, "")))
            if idx >= 0:
                field_type_input.setCurrentIndex(idx)
        field_note_input = QPlainTextEdit()
        field_note_input.setPlainText(str(existing.get(source_field_note, "")) if existing else "")
        field_note_input.setMinimumHeight(96)

        form.addRow(tr("forms", self.language), form_name_input)
        form.addRow(tr("append_field_name", self.language), field_name_input)
        form.addRow(tr("append_field_label", self.language), field_label_input)
        form.addRow(tr("append_field_type", self.language), field_type_input)
        form.addRow(tr("append_field_note", self.language), field_note_input)
        layout.addLayout(form)

        options_form = QFormLayout()
        option_code_input = QLineEdit()
        option_label_input = QLineEdit()
        option_list = QListWidget()
        add_option_button = QPushButton(tr("append_add_option", self.language))
        edit_option_button = QPushButton(tr("append_edit_option", self.language))
        remove_option_button = QPushButton(tr("append_remove_option", self.language))
        remove_option_button.setProperty("secondary", True)
        options_form.addRow(tr("append_option_code", self.language), option_code_input)
        options_form.addRow(tr("append_option_label", self.language), option_label_input)
        layout.addLayout(options_form)
        layout.addWidget(option_list)
        option_buttons = QHBoxLayout()
        option_buttons.addWidget(add_option_button)
        option_buttons.addWidget(edit_option_button)
        option_buttons.addWidget(remove_option_button)
        layout.addLayout(option_buttons)

        def update_choice_widgets() -> None:
            show_choices = field_type_input.currentText() in {"radio", "dropdown", "checkbox", "yesno"}
            for widget in [
                option_code_input,
                option_label_input,
                option_list,
                add_option_button,
                edit_option_button,
                remove_option_button,
            ]:
                widget.setVisible(show_choices)
            code_label = options_form.labelForField(option_code_input)
            label_label = options_form.labelForField(option_label_input)
            if code_label is not None:
                code_label.setVisible(show_choices)
            if label_label is not None:
                label_label.setVisible(show_choices)

        def add_option() -> None:
            code = option_code_input.text().strip()
            label = option_label_input.text().strip()
            if not code or not label:
                self.show_warning(tr("extra_fields", self.language), tr("append_option_required", self.language), dialog)
                return
            QListWidgetItem(f"{code}, {label}", option_list)
            option_code_input.clear()
            option_label_input.clear()
            option_code_input.setFocus()

        def edit_option() -> None:
            current = option_list.currentItem()
            if current is None:
                self.show_warning(tr("extra_fields", self.language), tr("append_option_select_to_edit", self.language), dialog)
                return
            code = option_code_input.text().strip()
            label = option_label_input.text().strip()
            if not code or not label:
                self.show_warning(tr("extra_fields", self.language), tr("append_option_required", self.language), dialog)
                return
            current.setText(f"{code}, {label}")
            option_code_input.clear()
            option_label_input.clear()

        def remove_option() -> None:
            current = option_list.currentItem()
            if current is not None:
                option_list.takeItem(option_list.row(current))

        def load_current_option(current, previous=None) -> None:
            if current is None:
                return
            raw_value = current.text().strip()
            if "," in raw_value:
                code, label = raw_value.split(",", 1)
                option_code_input.setText(code.strip())
                option_label_input.setText(label.strip())
            else:
                option_code_input.setText(raw_value)
                option_label_input.setText(raw_value)

        if existing:
            raw_choices = str(existing.get(source_choices, "")).strip()
            for part in [segment.strip() for segment in raw_choices.split("|") if segment.strip()]:
                QListWidgetItem(part, option_list)

        field_type_input.currentIndexChanged.connect(update_choice_widgets)
        add_option_button.clicked.connect(add_option)
        edit_option_button.clicked.connect(edit_option)
        remove_option_button.clicked.connect(remove_option)
        option_list.currentItemChanged.connect(load_current_option)
        option_list.itemDoubleClicked.connect(load_current_option)
        update_choice_widgets()

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.rejected.connect(dialog.reject)
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setAutoDefault(False)
            ok_button.setDefault(False)
        layout.addWidget(button_box)

        result: dict[str, str] | None = None

        def validate_and_accept() -> None:
            nonlocal result
            payload = self.build_append_field_payload(
                form_name=str(form_name_input.currentData()),
                field_name=field_name_input.text().strip(),
                field_label=field_label_input.text().strip(),
                field_type=field_type_input.currentText().strip(),
                field_note=field_note_input.toPlainText().strip(),
                choices=" | ".join(option_list.item(index).text() for index in range(option_list.count())),
                parent=dialog,
            )
            if not payload:
                return
            result = payload
            dialog.accept()

        button_box.accepted.connect(validate_and_accept)

        if dialog.exec() == 0:
            return None
        return result

    def build_append_field_payload(
        self,
        *,
        form_name: str,
        field_name: str,
        field_label: str,
        field_type: str,
        field_note: str,
        choices: str,
        parent=None,
    ) -> dict[str, str]:
        if not self.bundle:
            return {}
        if not form_name or not field_name or not field_label:
            self.show_warning(tr("extra_fields", self.language), tr("append_field_required", self.language), parent)
            return {}
        if field_type in {"radio", "dropdown", "checkbox", "yesno"} and not choices:
            self.show_warning(tr("extra_fields", self.language), tr("append_field_choices_required", self.language), parent)
            return {}
        legend = self.bundle.config.dictionary_legend
        payload = {source_name: "" for source_name in legend.values()}
        payload[legend.get("field_name", "Variable / Field Name")] = field_name
        payload[legend.get("form_name", "Form Name")] = form_name
        payload[legend.get("field_type", "Field Type")] = field_type
        payload[legend.get("field_label", "Field Label")] = field_label
        payload[legend.get("field_note", "Field Note")] = field_note
        payload[legend.get("choices", "Choices, Calculations, OR Slider Labels")] = choices
        return payload

    def edit_json_payload(self, title: str, payload: dict, parent=None) -> dict | None:
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QVBoxLayout

        dialog = QDialog(parent or self.widget)
        dialog.setWindowTitle(title)
        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit()
        editor.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))
        layout.addWidget(editor)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.rejected.connect(dialog.reject)
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setAutoDefault(False)
            ok_button.setDefault(False)
        layout.addWidget(button_box)

        parsed_result: dict | None = None

        def validate_and_accept() -> None:
            nonlocal parsed_result
            try:
                parsed = json.loads(editor.toPlainText().strip() or "{}")
            except json.JSONDecodeError as exc:
                self.show_warning(title, tr("json_parse_error", self.language, error=str(exc)), dialog)
                return
            if not isinstance(parsed, dict):
                self.show_warning(title, tr("json_object_required", self.language), dialog)
                return
            parsed_result = parsed
            dialog.accept()

        button_box.accepted.connect(validate_and_accept)

        if dialog.exec() == 0:
            return None
        return parsed_result

    def save_bundle_and_reload(self, message: str, parent=None) -> None:
        if not self.bundle:
            return
        current_form = self.current_form_name()
        current_field = self.current_field_name()
        save_workspace_bundle(self.bundle)
        self.bundle = reload_workspace_bundle(self.bundle)
        self.load_selection_state_from_config()
        self.populate_form_list()
        self.restore_current_items(current_form, current_field)
        self.refresh_selection_status()
        self.show_info(tr("workspace_title", self.language), message, parent)

    def restore_current_items(self, current_form: str | None, current_field: str | None) -> None:
        if current_form:
            for index in range(self.form_list.count()):
                item = self.form_list.item(index)
                if str(item.data(Qt.ItemDataRole.UserRole)) == current_form:
                    self.form_list.setCurrentRow(index)
                    break
        if current_field:
            for index in range(self.field_list.count()):
                item = self.field_list.item(index)
                if str(item.data(Qt.ItemDataRole.UserRole)) == current_field:
                    self.field_list.setCurrentRow(index)
                    break

    def import_excel_patient_data(self, on_success=None) -> bool:
        from PySide6.QtWidgets import QFileDialog, QProgressDialog

        if not self.bundle:
            return False
        if self._excel_thread is not None:
            self.show_warning(
                tr("import_excel_patients", self.language),
                tr("excel_import_already_running", self.language),
            )
            return False
        start_dir = self.runtime.settings.ui.last_open_directory or str(Path.cwd())
        file_path, _ = QFileDialog.getOpenFileName(
            self.widget,
            tr("select_patient_excel", self.language),
            start_dir,
            "Excel Workbook (*.xlsx *.xlsm)",
        )
        if not file_path:
            return False

        try:
            table = read_excel_table(file_path)
        except Exception as exc:
            self.show_warning(
                tr("import_excel_patients", self.language),
                tr("excel_import_failed", self.language, error=str(exc)),
            )
            return False

        self.ensure_tc_identifier_append_field()

        field_specs_by_name = build_field_specs_by_name(
            self.bundle.grouped_fields,
            append_fields=self.bundle.config.append_fields,
            dictionary_legend=self.bundle.config.dictionary_legend,
        )
        options = self.prompt_excel_import_options(table, field_specs_by_name)
        if options is None:
            return False
        options.llm_settings = self.build_excel_llm_settings()
        progress = QProgressDialog(
            tr("excel_import_progress_body", self.language),
            "",
            0,
            0,
            self.widget,
        )
        progress.setWindowTitle(tr("excel_import_progress_title", self.language))
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.show()

        thread = QThread(self.widget)
        worker = ExcelImportWorker(
            path=file_path,
            project_name=self.bundle.config.project_name,
            field_specs_by_name=field_specs_by_name,
            options=options,
        )
        worker.moveToThread(thread)
        self._excel_thread = thread
        self._excel_worker = worker
        bridge = ExcelImportUiBridge(
            page=self,
            progress=progress,
            file_path=file_path,
            on_success=on_success,
        )
        self._excel_bridge = bridge

        thread.started.connect(worker.run)
        worker.progress.connect(bridge.handle_progress, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(bridge.handle_success, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(bridge.handle_failure, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(bridge.cleanup, Qt.ConnectionType.QueuedConnection)
        thread.start()
        return True

    def scoped_grouped_fields(self) -> dict[str, list]:
        if not self.bundle:
            return {}
        if not self.selected_form_names and not self.selected_field_names:
            return self.bundle.grouped_fields
        effective_field_names = set(self.selected_field_names)
        for form_name in self.selected_form_names:
            effective_field_names.update(self.bundle.field_names_for_form(form_name))
        return {
            form_name: [
                field
                for field in fields
                if field.field_name in effective_field_names
            ]
            for form_name, fields in self.bundle.grouped_fields.items()
            if any(field.field_name in effective_field_names for field in fields)
        }

    def prompt_excel_import_options(self, table, field_specs_by_name: dict[str, Any]) -> ExcelImportOptions | None:
        from PySide6.QtWidgets import (
            QAbstractItemView,
            QCheckBox,
            QCompleter,
            QDialog,
            QDialogButtonBox,
            QFormLayout,
            QHeaderView,
            QHBoxLayout,
            QPushButton,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
        )

        headers = list(table.headers)
        if not headers:
            return None

        dialog = QDialog(self.widget)
        dialog.setWindowTitle(tr("excel_column_mapping_title", self.language))
        dialog.setMinimumSize(1120, 720)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        info = QLabel(tr("excel_column_mapping_hint", self.language))
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        patient_id_input = QComboBox()
        for header in headers:
            patient_id_input.addItem(header, header)
        try:
            detected_column = resolve_patient_id_column(headers)
        except ValueError:
            detected_column = headers[0]
        detected_index = patient_id_input.findData(detected_column)
        if detected_index >= 0:
            patient_id_input.setCurrentIndex(detected_index)

        form.addRow(tr("excel_patient_id_column", self.language), patient_id_input)
        layout.addLayout(form)

        llm_unmatched_input = QCheckBox(tr("excel_mapping_use_llm_unmatched", self.language))
        llm_unmatched_input.setChecked(False)
        layout.addWidget(llm_unmatched_input)

        llm_value_normalization_input = QCheckBox(
            tr("excel_mapping_use_llm_value_normalization", self.language)
        )
        llm_value_normalization_input.setChecked(False)
        layout.addWidget(llm_value_normalization_input)

        mapping_table = QTableWidget(0, 4)
        mapping_table.setHorizontalHeaderLabels(
            [
                tr("excel_mapping_col_column", self.language),
                tr("excel_mapping_col_sample", self.language),
                tr("excel_mapping_col_field", self.language),
                tr("excel_mapping_col_transform", self.language),
            ]
        )
        mapping_table.setObjectName("ExcelMappingTable")
        mapping_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        mapping_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        mapping_table.setAlternatingRowColors(True)
        mapping_table.setShowGrid(False)
        mapping_table.verticalHeader().setVisible(False)
        mapping_table.verticalHeader().setDefaultSectionSize(48)
        mapping_table.verticalHeader().setMinimumSectionSize(44)
        mapping_table.horizontalHeader().setMinimumHeight(46)
        mapping_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        mapping_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        mapping_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        mapping_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(mapping_table, 1)

        summary_label = QLabel("")
        summary_label.setObjectName("MutedLabel")
        summary_label.setWordWrap(True)
        layout.addWidget(summary_label)

        field_choices = [("", tr("excel_mapping_unmapped", self.language))]
        field_search_labels: list[str] = []
        field_text_lookup: dict[str, str | None] = {}
        fields_by_form: dict[str, list[tuple[str, Any]]] = {}

        def remember_field_text(text: str, field_name: str) -> None:
            if not text:
                return
            existing = field_text_lookup.get(text)
            if existing is None and text in field_text_lookup:
                return
            if existing and existing != field_name:
                field_text_lookup[text] = None
                return
            field_text_lookup[text] = field_name

        for field_name, spec in field_specs_by_name.items():
            fields_by_form.setdefault(str(spec.form_name or ""), []).append((field_name, spec))
        for form_name, fields in fields_by_form.items():
            form_label = form_name
            if self.bundle:
                form_label = self.bundle.form_display_name(form_name)
            field_choices.append((f"__form__:{form_name}", f"── {form_label} ──"))
            for field_name, spec in fields:
                field_label = str(spec.field_label or field_name).strip() or field_name
                display_label = f"{field_label} ({field_name})"
                search_label = f"{field_label} | {field_name} | {form_label}"
                field_choices.append((field_name, display_label))
                field_search_labels.append(search_label)
                remember_field_text(search_label, field_name)
                remember_field_text(display_label, field_name)
                remember_field_text(field_name, field_name)

        transform_choices = self.excel_transform_choices()

        def search_key(value: str) -> str:
            return value.casefold().replace("ı", "i")

        def resolve_combo_data(combo: QComboBox) -> str:
            text = combo.currentText().strip()
            current_label = combo.itemText(combo.currentIndex()) if combo.currentIndex() >= 0 else ""
            if text and text != current_label:
                if text in field_specs_by_name:
                    return text
                exact_field_name = field_text_lookup.get(text)
                if exact_field_name:
                    return exact_field_name
                for field_name, label in field_choices:
                    if field_name.startswith("__form__:"):
                        continue
                    if text == label or f"| {field_name}" in text:
                        return field_name
                text_key = search_key(text)
                partial_matches = [
                    field_name
                    for label, field_name in field_text_lookup.items()
                    if field_name and text_key and (text_key in search_key(label) or text_key == search_key(field_name))
                ]
                if len(set(partial_matches)) == 1:
                    return partial_matches[0]
                return ""
            value = combo.currentData()
            if value is not None:
                resolved = str(value)
                return "" if resolved.startswith("__form__:") else resolved
            if text in field_specs_by_name:
                return text
            for field_name, label in field_choices:
                if field_name.startswith("__form__:"):
                    continue
                if text == label:
                    return field_name
            return ""

        def sample_text(column_name: str) -> str:
            samples = sample_column_values(table.rows, column_name, limit=3)
            if not samples:
                return ""
            return " | ".join(str(item) for item in samples)

        def make_column_combo(column_name: str | None = None) -> QComboBox:
            combo = QComboBox()
            combo.setMinimumHeight(38)
            for header in headers:
                combo.addItem(header, header)
            if column_name:
                index = combo.findData(column_name)
                if index >= 0:
                    combo.setCurrentIndex(index)
            return combo

        def make_field_combo(field_name: str | None = None) -> QComboBox:
            combo = QComboBox()
            combo.setMinimumHeight(38)
            combo.setEditable(True)
            combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            if combo.lineEdit() is not None:
                combo.lineEdit().setPlaceholderText(tr("excel_mapping_field_search_placeholder", self.language))
            for value, label in field_choices:
                combo.addItem(label, value)
                row_index = combo.count() - 1
                if str(value).startswith("__form__:"):
                    item = combo.model().item(row_index)
                    if item is not None:
                        item.setEnabled(False)
                elif value:
                    spec = field_specs_by_name.get(str(value))
                    form_label = self.bundle.form_display_name(spec.form_name) if self.bundle and spec else ""
                    tooltip = f"{form_label} / {label}" if form_label else label
                    combo.setItemData(row_index, tooltip, Qt.ItemDataRole.ToolTipRole)
            if field_name:
                index = combo.findData(field_name)
                if index >= 0:
                    combo.setCurrentIndex(index)
            completer = QCompleter(field_search_labels, combo)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            completer.setMaxVisibleItems(12)

            def apply_completion(text: str, target_combo=combo) -> None:
                field_name = field_text_lookup.get(text)
                index = target_combo.findData(field_name) if field_name else target_combo.findText(text)
                if index is not None and index >= 0:
                    target_combo.setCurrentIndex(index)
                else:
                    target_combo.setEditText(text)

            completer.activated[str].connect(apply_completion)
            combo.setCompleter(completer)
            combo.setMinimumContentsLength(28)
            combo.view().setMinimumWidth(560)
            completer.popup().setMinimumWidth(620)
            return combo

        def make_transform_combo(value_transform: str | None = None) -> QComboBox:
            combo = QComboBox()
            combo.setMinimumHeight(38)
            for value, label in transform_choices:
                combo.addItem(label, value)
            index = combo.findData(value_transform or "direct")
            if index >= 0:
                combo.setCurrentIndex(index)
            return combo

        def refresh_row(row: int) -> None:
            column_combo = mapping_table.cellWidget(row, 0)
            field_combo = mapping_table.cellWidget(row, 2)
            if not isinstance(column_combo, QComboBox) or not isinstance(field_combo, QComboBox):
                return
            column_name = str(column_combo.currentData() or "")
            sample_item = mapping_table.item(row, 1)
            if sample_item is not None:
                sample_item.setText(sample_text(column_name))
            field_name = resolve_combo_data(field_combo)
            refresh_mapping_summary()

        def refresh_mapping_summary() -> None:
            patient_id_column = str(patient_id_input.currentData() or "")
            mapped_columns: set[str] = set()
            mapped_fields: list[str] = []
            duplicates: set[str] = set()
            for row in range(mapping_table.rowCount()):
                column_combo = mapping_table.cellWidget(row, 0)
                field_combo = mapping_table.cellWidget(row, 2)
                if not isinstance(column_combo, QComboBox) or not isinstance(field_combo, QComboBox):
                    continue
                column_name = str(column_combo.currentData() or "")
                field_name = resolve_combo_data(field_combo)
                if not field_name or column_name == patient_id_column:
                    continue
                mapped_columns.add(column_name)
                if field_name in mapped_fields:
                    duplicates.add(field_name)
                mapped_fields.append(field_name)
            candidate_columns = [header for header in headers if header != patient_id_column]
            unmapped_count = len([header for header in candidate_columns if header not in mapped_columns])
            text = tr(
                "excel_mapping_summary",
                self.language,
                mapped=len(mapped_fields),
                unmapped=unmapped_count,
            )
            if duplicates:
                text = f"{text} {tr('excel_mapping_duplicate_hint', self.language, fields=', '.join(sorted(duplicates)))}"
            summary_label.setText(text)

        def add_mapping_row(
            column_name: str | None = None,
            field_name: str | None = None,
            value_transform: str | None = None,
        ) -> None:
            row = mapping_table.rowCount()
            mapping_table.insertRow(row)
            column_combo = make_column_combo(column_name)
            field_combo = make_field_combo(field_name)
            transform_combo = make_transform_combo(value_transform)
            sample_item = QTableWidgetItem(sample_text(str(column_combo.currentData() or "")))
            sample_item.setFlags(sample_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            mapping_table.setCellWidget(row, 0, column_combo)
            mapping_table.setItem(row, 1, sample_item)
            mapping_table.setCellWidget(row, 2, field_combo)
            mapping_table.setCellWidget(row, 3, transform_combo)
            column_combo.currentIndexChanged.connect(lambda index, table_row=row: refresh_row(table_row))
            field_combo.currentIndexChanged.connect(lambda index, table_row=row: refresh_row(table_row))
            field_combo.editTextChanged.connect(lambda text, table_row=row: refresh_row(table_row))
            transform_combo.currentIndexChanged.connect(lambda index, table_row=row: refresh_row(table_row))
            refresh_row(row)
            mapping_table.setRowHeight(row, 48)

        initial_excluded = {str(patient_id_input.currentData() or "")}
        suggested_mappings = build_procedural_column_mappings(
            headers,
            table.rows,
            field_specs_by_name,
            excluded_columns=initial_excluded,
        )
        suggestions_by_column: dict[str, list[ExcelColumnMapping]] = {}
        for mapping in suggested_mappings:
            suggestions_by_column.setdefault(mapping.column_name, []).append(mapping)

        for header in headers:
            if header in initial_excluded:
                continue
            suggestions = suggestions_by_column.get(header) or []
            if suggestions:
                for mapping in suggestions:
                    add_mapping_row(mapping.column_name, mapping.field_name, mapping.value_transform)
            else:
                add_mapping_row(header, "", "direct")

        controls = QHBoxLayout()
        add_row_button = QPushButton(tr("excel_mapping_add_row", self.language))
        remove_row_button = QPushButton(tr("excel_mapping_remove_row", self.language))
        remove_row_button.setProperty("secondary", True)
        controls.addWidget(add_row_button)
        controls.addWidget(remove_row_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        def default_mapping_column() -> str | None:
            patient_id_column = str(patient_id_input.currentData() or "")
            for header in headers:
                if header != patient_id_column:
                    return header
            return headers[0] if headers else None

        add_row_button.clicked.connect(lambda checked=False: add_mapping_row(default_mapping_column(), "", "direct"))

        def remove_selected_row() -> None:
            row = mapping_table.currentRow()
            if row >= 0:
                mapping_table.removeRow(row)
                refresh_mapping_summary()

        remove_row_button.clicked.connect(remove_selected_row)
        patient_id_input.currentIndexChanged.connect(lambda index: refresh_mapping_summary())
        refresh_mapping_summary()

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.rejected.connect(dialog.reject)
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText(tr("excel_mapping_start_import", self.language))
            ok_button.setAutoDefault(False)
            ok_button.setDefault(False)
        cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setText(tr("cancel_button", self.language))
        layout.addWidget(button_box)

        selected_options: ExcelImportOptions | None = None

        def validate_and_accept() -> None:
            nonlocal selected_options
            patient_id_column = str(patient_id_input.currentData() or "")
            mappings: list[ExcelColumnMapping] = []
            used_fields: set[str] = set()
            duplicate_fields: set[str] = set()
            for row in range(mapping_table.rowCount()):
                column_combo = mapping_table.cellWidget(row, 0)
                field_combo = mapping_table.cellWidget(row, 2)
                transform_combo = mapping_table.cellWidget(row, 3)
                if (
                    not isinstance(column_combo, QComboBox)
                    or not isinstance(field_combo, QComboBox)
                    or not isinstance(transform_combo, QComboBox)
                ):
                    continue
                column_name = str(column_combo.currentData() or "")
                field_name = resolve_combo_data(field_combo)
                if not field_name or column_name == patient_id_column:
                    continue
                if field_name in used_fields:
                    duplicate_fields.add(field_name)
                    continue
                used_fields.add(field_name)
                mappings.append(
                    ExcelColumnMapping(
                        column_name=column_name,
                        field_name=field_name,
                        match_type="manual",
                        value_transform=str(transform_combo.currentData() or "direct"),
                    )
                )
            if duplicate_fields:
                self.show_warning(
                    tr("excel_column_mapping_title", self.language),
                    tr("excel_mapping_duplicate_field_warning", self.language, fields=", ".join(sorted(duplicate_fields))),
                    dialog,
                )
                return
            if not mappings and not llm_unmatched_input.isChecked():
                self.show_warning(
                    tr("excel_column_mapping_title", self.language),
                    tr("excel_mapping_required", self.language),
                    dialog,
                )
                return
            selected_options = ExcelImportOptions(
                patient_id_column=patient_id_column,
                patient_mode="auto",
                use_llm_mapping=llm_unmatched_input.isChecked(),
                use_llm_value_normalization=llm_value_normalization_input.isChecked(),
                column_mappings=mappings,
                automatic_mapping=False,
            )
            dialog.accept()

        button_box.accepted.connect(validate_and_accept)
        if dialog.exec() == 0:
            return None
        return selected_options

    def excel_transform_choices(self) -> list[tuple[str, str]]:
        return [
            ("direct", tr("excel_transform_direct", self.language)),
            ("name_given", tr("excel_transform_name_given", self.language)),
            ("name_family", tr("excel_transform_name_family", self.language)),
            ("first_2", tr("excel_transform_first_2", self.language)),
            ("name_given_first_2", tr("excel_transform_name_given_first_2", self.language)),
            ("name_family_first_2", tr("excel_transform_name_family_first_2", self.language)),
        ]

    def build_excel_llm_settings(self) -> dict[str, Any]:
        if not self.bundle:
            return {}
        settings = self.effective_llm_settings()
        provider = str(settings.get("provider", "ollama")).strip().lower()
        base_url = str(settings.get("base_url", "") or "")
        if provider in {"openai", "openai_compatible", "openrouter"} and is_ollama_base_url(base_url):
            settings["provider"] = "ollama"
            settings["stream"] = True
            settings["think"] = bool(settings.get("think", False))
            settings.setdefault("options", {"num_ctx": 32768})
            settings.pop("use_json_schema", None)
            return settings
        selected_provider = self.runtime.settings.inference.selected_provider or self.runtime.inference_recommendation.mode
        missing_api_key = (
            provider in API_KEY_PROVIDER_NAMES
            and not can_resolve_api_key(settings)
        )
        if missing_api_key and selected_provider in {"local_ollama", "remote_ollama"}:
            return self.build_project_llm_defaults()
        return settings

    def effective_llm_settings(self) -> dict[str, Any]:
        if not self.bundle or not self.show_model_settings:
            return dict(self.runtime.app_config.get("llm", {}) or {})
        return merge_llm_settings(self.runtime.app_config.get("llm", {}), self.bundle.config.llm)

    def add_documents(self) -> None:
        from PySide6.QtWidgets import QFileDialog, QListWidgetItem

        start_dir = self.runtime.settings.ui.last_open_directory or str(Path.cwd())
        file_paths, _ = QFileDialog.getOpenFileNames(
            self.widget,
            tr("select_documents", self.language),
            start_dir,
            "Documents (*.txt *.pdf *.png *.jpg *.jpeg *.docx *.doc *.odt *.rtf)",
        )
        if not file_paths:
            return
        existing_paths = {
            self.document_list.item(index).text()
            for index in range(self.document_list.count())
        }
        for file_path in file_paths:
            if file_path in existing_paths:
                continue
            QListWidgetItem(file_path, self.document_list)
            existing_paths.add(file_path)
        self.runtime.settings.ui.last_open_directory = str(Path(file_paths[0]).resolve().parent)
        self.runtime.settings_store.save(self.runtime.settings)
        self.queue_status.setText(tr("documents_queued", self.language, count=self.document_list.count()))

    def clear_document_draft(self) -> None:
        self.document_list.clear()
        self.queue_status.setText(tr("no_documents", self.language))

    def add_patient_to_queue(self) -> None:
        from PySide6.QtWidgets import (
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QFormLayout,
            QLineEdit,
            QVBoxLayout,
        )

        if not self.bundle:
            return
        documents = [self.document_list.item(index).text() for index in range(self.document_list.count())]
        if not documents:
            self.show_warning(tr("patient_queue", self.language), tr("patient_queue_requires_documents", self.language))
            return

        dialog = QDialog(self.widget)
        dialog.setWindowTitle(tr("add_patient_to_queue", self.language))
        dialog.setMinimumWidth(520)
        layout = QVBoxLayout(dialog)

        info = QLabel(tr("patient_queue_dialog", self.language, count=len(documents)))
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        queue_label_input = QLineEdit("")
        patient_mode_input = QComboBox()
        patient_mode_input.addItem(tr("patient_mode_new", self.language), "new")
        patient_mode_input.addItem(tr("patient_mode_existing", self.language), "existing")

        identifier_type_input = QComboBox()
        identifier_type_input.addItem(tr("patient_identifier_record_id", self.language), "record_id")
        identifier_type_input.addItem(tr("patient_identifier_tc", self.language), "tc_kimlik_no")
        identifier_value_input = QLineEdit("")

        form.addRow(tr("patient_queue_label", self.language), queue_label_input)
        form.addRow(tr("patient_mode_label", self.language), patient_mode_input)
        form.addRow(tr("patient_identifier_type", self.language), identifier_type_input)
        form.addRow(tr("patient_identifier_value", self.language), identifier_value_input)
        layout.addLayout(form)

        identifier_type_label = form.labelForField(identifier_type_input)
        identifier_value_label = form.labelForField(identifier_value_input)

        def update_patient_mode() -> None:
            is_existing = patient_mode_input.currentData() == "existing"
            identifier_type_input.setVisible(is_existing)
            identifier_value_input.setVisible(is_existing)
            if identifier_type_label is not None:
                identifier_type_label.setVisible(is_existing)
            if identifier_value_label is not None:
                identifier_value_label.setVisible(is_existing)

        patient_mode_input.currentIndexChanged.connect(update_patient_mode)
        update_patient_mode()

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.rejected.connect(dialog.reject)
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setAutoDefault(False)
            ok_button.setDefault(False)
        layout.addWidget(button_box)

        def validate_and_accept() -> None:
            patient_mode = str(patient_mode_input.currentData())
            identifier_type = str(identifier_type_input.currentData()) if patient_mode == "existing" else None
            identifier_value = identifier_value_input.text().strip() if patient_mode == "existing" else None
            queue_label = queue_label_input.text().strip()

            if patient_mode == "existing" and not identifier_value:
                self.show_warning(
                    tr("patient_queue", self.language),
                    tr("patient_identifier_required", self.language),
                    dialog,
                )
                return

            if patient_mode == "new":
                self.ensure_tc_identifier_append_field()
                default_label = tr("patient_queue_new_summary", self.language, count=len(documents))
            else:
                default_label = tr(
                    "patient_queue_existing_summary",
                    self.language,
                    identifier_type=identifier_type or "record_id",
                    identifier_value=identifier_value or "",
                    count=len(documents),
                )

            config_snapshot = build_scoped_project_config(self.bundle, self.selected_form_names, self.selected_field_names)
            self.patient_queue_items.append(
                PendingPatientJob(
                    queue_label=queue_label or default_label,
                    patient_mode=patient_mode,
                    identifier_type=identifier_type,
                    identifier_value=identifier_value,
                    documents=list(documents),
                    config_snapshot=config_snapshot,
                )
            )
            self.refresh_patient_queue_list()
            self.clear_document_draft()
            dialog.accept()

        button_box.accepted.connect(validate_and_accept)
        dialog.exec()

    def add_patient_documents_to_queue(self) -> bool:
        from PySide6.QtWidgets import (
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QFileDialog,
            QFormLayout,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QListWidget,
            QListWidgetItem,
            QPushButton,
            QVBoxLayout,
        )

        if not self.bundle:
            self.show_warning(tr("patient_queue", self.language), tr("workspace_no_redcap_projects", self.language))
            return False

        dialog = QDialog(self.widget)
        dialog.setWindowTitle(tr("clinical_add_patient_documents", self.language))
        dialog.setMinimumSize(720, 560)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        info = QLabel(tr("clinical_add_patient_documents_desc", self.language))
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        queue_label_input = QLineEdit("")
        patient_mode_input = QComboBox()
        patient_mode_input.addItem(tr("patient_mode_new", self.language), "new")
        patient_mode_input.addItem(tr("patient_mode_existing", self.language), "existing")

        identifier_type_input = QComboBox()
        identifier_type_input.addItem(tr("patient_identifier_record_id", self.language), "record_id")
        identifier_type_input.addItem(tr("patient_identifier_tc", self.language), "tc_kimlik_no")
        identifier_value_input = QLineEdit("")

        form.addRow(tr("patient_queue_label", self.language), queue_label_input)
        form.addRow(tr("patient_mode_label", self.language), patient_mode_input)
        form.addRow(tr("patient_identifier_type", self.language), identifier_type_input)
        form.addRow(tr("patient_identifier_value", self.language), identifier_value_input)
        layout.addLayout(form)

        identifier_type_label = form.labelForField(identifier_type_input)
        identifier_value_label = form.labelForField(identifier_value_input)

        def update_patient_mode() -> None:
            is_existing = patient_mode_input.currentData() == "existing"
            identifier_type_input.setVisible(is_existing)
            identifier_value_input.setVisible(is_existing)
            if identifier_type_label is not None:
                identifier_type_label.setVisible(is_existing)
            if identifier_value_label is not None:
                identifier_value_label.setVisible(is_existing)

        patient_mode_input.currentIndexChanged.connect(update_patient_mode)
        update_patient_mode()

        documents_label = QLabel(tr("clinical_patient_documents", self.language))
        layout.addWidget(documents_label)
        document_list = QListWidget()
        layout.addWidget(document_list, 1)

        documents_buttons = QHBoxLayout()
        add_documents_button = QPushButton(tr("clinical_add_documents_to_patient", self.language))
        remove_documents_button = QPushButton(tr("clinical_remove_selected_documents", self.language))
        remove_documents_button.setProperty("secondary", True)
        clear_documents_button = QPushButton(tr("clear_documents", self.language))
        clear_documents_button.setProperty("secondary", True)
        documents_buttons.addWidget(add_documents_button)
        documents_buttons.addWidget(remove_documents_button)
        documents_buttons.addWidget(clear_documents_button)
        documents_buttons.addStretch(1)
        layout.addLayout(documents_buttons)

        status = QLabel(tr("patient_queue_requires_documents", self.language))
        status.setWordWrap(True)
        layout.addWidget(status)

        def add_files() -> None:
            start_dir = self.runtime.settings.ui.last_open_directory or str(Path.cwd())
            file_paths, _ = QFileDialog.getOpenFileNames(
                dialog,
                tr("select_documents", self.language),
                start_dir,
                "Documents (*.txt *.pdf *.png *.jpg *.jpeg *.docx *.doc *.odt *.rtf)",
            )
            if not file_paths:
                return
            existing_paths = {
                document_list.item(index).text()
                for index in range(document_list.count())
            }
            for file_path in file_paths:
                if file_path in existing_paths:
                    continue
                QListWidgetItem(file_path, document_list)
                existing_paths.add(file_path)
            self.runtime.settings.ui.last_open_directory = str(Path(file_paths[0]).resolve().parent)
            self.runtime.settings_store.save(self.runtime.settings)
            status.setText(tr("documents_queued", self.language, count=document_list.count()))

        def remove_selected_files() -> None:
            for item in document_list.selectedItems():
                row = document_list.row(item)
                document_list.takeItem(row)
            if document_list.count():
                status.setText(tr("documents_queued", self.language, count=document_list.count()))
            else:
                status.setText(tr("patient_queue_requires_documents", self.language))

        def clear_files() -> None:
            document_list.clear()
            status.setText(tr("patient_queue_requires_documents", self.language))

        add_documents_button.clicked.connect(add_files)
        remove_documents_button.clicked.connect(remove_selected_files)
        clear_documents_button.clicked.connect(clear_files)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.rejected.connect(dialog.reject)
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setAutoDefault(False)
            ok_button.setDefault(False)
        layout.addWidget(button_box)

        accepted = {"value": False}

        def validate_and_accept() -> None:
            documents = [document_list.item(index).text() for index in range(document_list.count())]
            if not documents:
                self.show_warning(
                    tr("patient_queue", self.language),
                    tr("patient_queue_requires_documents", self.language),
                    dialog,
                )
                return
            patient_mode = str(patient_mode_input.currentData())
            identifier_type = str(identifier_type_input.currentData()) if patient_mode == "existing" else None
            identifier_value = identifier_value_input.text().strip() if patient_mode == "existing" else None
            if patient_mode == "existing" and not identifier_value:
                self.show_warning(
                    tr("patient_queue", self.language),
                    tr("patient_identifier_required", self.language),
                    dialog,
                )
                return
            queue_label = queue_label_input.text().strip()
            if patient_mode == "new":
                self.ensure_tc_identifier_append_field()
                default_label = tr("patient_queue_new_summary", self.language, count=len(documents))
            else:
                default_label = tr(
                    "patient_queue_existing_summary",
                    self.language,
                    identifier_type=identifier_type or "record_id",
                    identifier_value=identifier_value or "",
                    count=len(documents),
                )
            config_snapshot = build_scoped_project_config(self.bundle, self.selected_form_names, self.selected_field_names)
            self.patient_queue_items.append(
                PendingPatientJob(
                    queue_label=queue_label or default_label,
                    patient_mode=patient_mode,
                    identifier_type=identifier_type,
                    identifier_value=identifier_value,
                    documents=list(documents),
                    config_snapshot=config_snapshot,
                )
            )
            self.refresh_patient_queue_list()
            accepted["value"] = True
            dialog.accept()

        button_box.accepted.connect(validate_and_accept)
        dialog.exec()
        return accepted["value"]

    def patient_queue_summaries(self) -> list[str]:
        return [
            tr(
                "clinical_patient_queue_item",
                self.language,
                patient=job.queue_label,
                documents=len(job.documents),
            )
            for job in self.patient_queue_items
        ]

    def remove_patient_queue_item(self, index: int) -> bool:
        if index < 0 or index >= len(self.patient_queue_items):
            return False
        self.patient_queue_items.pop(index)
        self.refresh_patient_queue_list()
        return True

    def remove_selected_patient(self) -> None:
        current_row = self.patient_queue_list.currentRow()
        if current_row < 0 or current_row >= len(self.patient_queue_items):
            return
        self.patient_queue_items.pop(current_row)
        self.refresh_patient_queue_list()

    def refresh_patient_queue_list(self) -> None:
        from PySide6.QtWidgets import QListWidgetItem

        self.patient_queue_list.clear()
        for job in self.patient_queue_items:
            item = QListWidgetItem(job.queue_label)
            item.setData(Qt.ItemDataRole.UserRole, job)
            self.patient_queue_list.addItem(item)
        if self.patient_queue_items:
            self.patient_queue_status.setText(
                tr("patient_queue_count", self.language, count=len(self.patient_queue_items))
            )
        else:
            self.patient_queue_status.setText(tr("patient_queue_empty", self.language))

    def run_patient_queue_extraction(self) -> None:
        from gui.progress_dialog import ExtractionProgressDialog

        if not self.bundle:
            return
        if not self.patient_queue_items:
            self.show_warning(tr("patient_queue", self.language), tr("patient_queue_empty", self.language))
            return
        if self._extraction_thread is not None:
            self.show_warning(
                tr("run_patient_queue", self.language),
                tr("extraction_already_running", self.language),
            )
            return

        current_config = build_scoped_project_config(self.bundle, self.selected_form_names, self.selected_field_names)
        current_config.llm = self.effective_llm_settings()
        jobs = [
            PendingPatientJob(
                queue_label=job.queue_label,
                patient_mode=job.patient_mode,
                identifier_type=job.identifier_type,
                identifier_value=job.identifier_value,
                documents=list(job.documents),
                config_snapshot=current_config,
            )
            for job in self.patient_queue_items
        ]
        progress = ExtractionProgressDialog(language=self.language, total=len(jobs), parent=self.widget)
        progress.show()

        thread = QThread(self.widget)
        worker = PatientQueueExtractionWorker(jobs=jobs)
        worker.moveToThread(thread)
        self._extraction_thread = thread
        self._extraction_worker = worker
        bridge = PatientExtractionUiBridge(page=self, progress=progress)
        self._extraction_bridge = bridge

        progress.cancel_button.clicked.connect(lambda checked=False: worker.cancel())
        progress.rejected.connect(worker.cancel, Qt.ConnectionType.DirectConnection)
        thread.started.connect(worker.run)
        worker.progress.connect(bridge.update_progress, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(bridge.handle_finished, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(bridge.handle_failure, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(bridge.cleanup, Qt.ConnectionType.QueuedConnection)
        thread.start()

    def show_extraction_results_dialog(self, results: list[PatientExtractionResult]) -> None:
        from gui.review_dialog import ReviewDialog

        dialog = ReviewDialog(
            language=self.language,
            results=results,
            runtime=self.runtime,
            bundle=self.bundle,
            parent=self.widget,
        )
        dialog.exec()
        self.patient_queue_items = []
        self.latest_extraction_results = []
        self.refresh_patient_queue_list()

    def build_patient_result_summary(self, result: PatientExtractionResult) -> str:
        review_count = sum(1 for item in result.merged_response.results if item.needs_review)
        found_count = sum(1 for item in result.merged_response.results if item.status == "found")
        return tr(
            "extraction_result_summary",
            self.language,
            patient=result.queue_label,
            found=found_count,
            review=review_count,
        )

    def ensure_tc_identifier_append_field(self) -> None:
        if not self.bundle or not self.bundle.form_names:
            return
        if self.find_existing_identifier_field("tc_kimlik_no"):
            return
        first_form = self.bundle.form_names[0]
        payload = self.build_append_field_payload(
            form_name=first_form,
            field_name="tc_kimlik_no",
            field_label="T.C. Kimlik Numarası",
            field_type="text",
            field_note="11 haneli Türkiye Cumhuriyeti kimlik numarasını tarayın.",
            choices="",
            parent=self.widget,
        )
        if not payload:
            return
        legend = self.bundle.config.dictionary_legend
        payload[legend.get("identifier", "Identifier?")] = "y"
        payload[legend.get("text_validation", "Text Validation Type OR Show Slider Number")] = "integer"
        self.bundle.config.append_fields.append(payload)
        save_workspace_bundle(self.bundle)

    def find_existing_identifier_field(self, field_name: str) -> bool:
        if not self.bundle:
            return False
        if field_name in self.bundle.all_field_names:
            return True
        source_field_name = self.bundle.config.dictionary_legend.get("field_name", "Variable / Field Name")
        return any(str(item.get(source_field_name, "")).strip() == field_name for item in self.bundle.config.append_fields)

    def build_project_llm_defaults(self) -> dict[str, Any]:
        inference = self.runtime.settings.inference
        provider = inference.selected_provider or self.runtime.inference_recommendation.mode
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

    def find_append_field(self, field_name: str) -> dict[str, str] | None:
        if not self.bundle:
            return None
        source_field_name = self.bundle.config.dictionary_legend.get("field_name", "Variable / Field Name")
        for item in self.bundle.config.append_fields:
            if str(item.get(source_field_name, "")).strip() == field_name:
                return item
        return None

    def find_field(self, form_name: str | None, field_name: str):
        if not self.bundle or not form_name:
            return None
        for field in self.bundle.grouped_fields.get(form_name, []):
            if field.field_name == field_name:
                return field
        return None

    def current_field_display_name(self) -> str | None:
        form_name = self.current_form_name()
        field_name = self.current_field_name()
        return self.field_display_name(form_name, field_name)

    def field_display_name(self, form_name: str | None, field_name: str | None) -> str | None:
        field = self.find_field(form_name, field_name) if field_name else None
        if field is None:
            return None
        return f"{field.field_label} | {field.field_name}"

    def extract_limit_output_length(self, post_processing: list | None) -> int | None:
        for item in post_processing or []:
            if isinstance(item, (list, tuple)) and len(item) >= 2 and item[0] == "limit_output_length":
                try:
                    return int(item[1])
                except (TypeError, ValueError):
                    return None
        return None

    def merge_post_processing(self, *, existing: list | None, limit_output_length: int | None) -> list:
        merged: list = []
        for item in existing or []:
            if isinstance(item, (list, tuple)) and item and item[0] == "limit_output_length":
                continue
            merged.append(item)
        if limit_output_length is not None:
            merged.append(["limit_output_length", int(limit_output_length)])
        return merged

    def _set_combo_value(self, combo, target_value: str) -> None:
        index = combo.findData(target_value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def resolve_form_rule_target(self) -> str | None:
        if not self.bundle:
            return None
        if self.selected_form_names:
            return sorted(self.selected_form_names)[0]
        if self.selected_field_names:
            for form_name in self.bundle.form_names:
                if any(field_name in self.selected_field_names for field_name in self.bundle.field_names_for_form(form_name)):
                    return form_name
        current_form = self.current_form_name()
        if current_form:
            return current_form
        if self.form_list.count() > 0:
            first_item = self.form_list.item(0)
            if first_item is not None:
                return str(first_item.data(Qt.ItemDataRole.UserRole))
        for form_name in self.bundle.form_names:
            return form_name
        return None

    def resolve_field_rule_target(self, form_name: str | None = None) -> str | None:
        target_form = form_name or self.resolve_form_rule_target()
        if not target_form or not self.bundle:
            return None
        current_field = self.current_field_name()
        if current_field and self.find_field(target_form, current_field) is not None:
            return current_field
        if target_form in self.selected_form_names:
            field_names = self.bundle.field_names_for_form(target_form)
            return field_names[0] if field_names else None
        for field_name in self.bundle.field_names_for_form(target_form):
            if field_name in self.selected_field_names:
                return field_name
        if self.field_list.count() > 0:
            first_item = self.field_list.item(0)
            if first_item is not None:
                return str(first_item.data(Qt.ItemDataRole.UserRole))
        field_names = self.bundle.field_names_for_form(target_form)
        if field_names:
            return field_names[0]
        return None

    def show_info(self, title: str, message: str, parent=None) -> None:
        self.message_box_class.information(parent or self.widget, title, message)

    def show_warning(self, title: str, message: str, parent=None) -> None:
        self.message_box_class.warning(parent or self.widget, title, message)
