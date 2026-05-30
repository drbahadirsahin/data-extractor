from __future__ import annotations

from copy import deepcopy
import json
import logging
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from data_entry_browser import DataEntryRecordBrowser, RecordDetail
from data_entry_form_changes import apply_form_changes
from data_entry_form_model import DESCRIPTION_EDITOR, READONLY_EDITOR, build_form_render_model
from data_entry_store import DataEntryStore
from data_entry_sync_client import DataEntrySyncClient, load_data_entry_sync_config
from data_entry_sync_service import DataEntrySyncService
from gui.data_entry_form import DataEntryFormWidget
from gui.extraction_worker import PendingPatientJob, PatientQueueExtractionWorker
from gui.i18n import tr
from identity_registry_client import IdentityRegistryClient, load_identity_registry_config
from llm_provider import merge_llm_settings
from redcap_client import RedcapClient
from release_profile import show_model_settings
from settings_store import RedcapProjectToken
from submission_service import normalize_tc_identity_no
from workspace_flow import WorkspaceBundle, ensure_server_metadata_in_config, load_workspace_bundle


class DataEntrySyncWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, *, store_path: Path, api_url: str, api_token: str, app_config: dict[str, Any]) -> None:
        super().__init__()
        self.store_path = store_path
        self.api_url = api_url
        self.api_token = api_token
        self.app_config = app_config

    @Slot()
    def run(self) -> None:
        try:
            store = DataEntryStore(self.store_path)
            config = load_data_entry_sync_config(self.app_config, api_url=self.api_url)
            client = DataEntrySyncClient(config, self.api_token)
            report = DataEntrySyncService(store, client).sync_read_only()
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(report)


class DataEntryAIFillBridge(QObject):
    def __init__(self, *, page: "ClinicalDataEntryPage", progress: Any, field_names: set[str]) -> None:
        super().__init__(page.widget)
        self.page = page
        self.progress = progress
        self.field_names = field_names

    @Slot(int, str)
    def update_progress(self, current: int, patient: str) -> None:
        display_patient = tr("extraction_progress_done", self.page.language) if patient == "done" else patient
        self.progress.update_progress(current=current, patient=display_patient)

    @Slot(str)
    def handle_failure(self, error: str) -> None:
        self.progress.close()
        self.page.handle_ai_fill_failure(error)

    @Slot(object)
    def handle_finished(self, payload: dict[str, Any]) -> None:
        self.progress.close()
        if payload.get("canceled"):
            self.page.status_label.setText(tr("data_entry_ai_fill_canceled", self.page.language))
            return
        values: dict[str, Any] = {}
        for result in list(payload.get("results") or []):
            for field_result in result.merged_response.results:
                if field_result.final_value is None or field_result.status == "not_found":
                    continue
                values[field_result.field_name] = field_result.final_value
        self.page.handle_ai_fill_success(values, self.field_names)

    @Slot()
    def cleanup(self) -> None:
        self.page.cleanup_ai_thread()


class ClinicalDataEntryPage:
    def __init__(self, runtime: Any, *, change_dag: Callable[[dict[str, Any]], None] | None = None) -> None:
        from PySide6.QtWidgets import (
            QComboBox,
            QFrame,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QListWidget,
            QProgressBar,
            QPushButton,
            QSplitter,
            QVBoxLayout,
            QWidget,
        )

        self.runtime = runtime
        self.language = runtime.settings.ui.language
        self.change_dag = change_dag
        self.store = DataEntryStore(data_entry_store_path(runtime.app_home))
        self.browser = DataEntryRecordBrowser(self.store)
        self.bundle: WorkspaceBundle | None = None
        self.current_model = None
        self._sync_thread: QThread | None = None
        self._sync_worker: DataEntrySyncWorker | None = None
        self._ai_thread: QThread | None = None
        self._ai_worker: PatientQueueExtractionWorker | None = None
        self._ai_bridge: DataEntryAIFillBridge | None = None

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
        title = QLabel(tr("data_entry_title", self.language))
        title.setObjectName("PageTitle")
        title_group.addWidget(title)
        subtitle = QLabel(tr("data_entry_subtitle", self.language))
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
        project_status_group = QWidget()
        project_status_layout = QVBoxLayout(project_status_group)
        project_status_layout.setContentsMargins(0, 0, 0, 0)
        project_status_layout.setSpacing(5)
        project_status_layout.addWidget(self.project_status)
        project_status_layout.addWidget(self.project_user_context)
        project_status_layout.addWidget(self.dag_combo)
        header_layout.addWidget(project_status_group)
        layout.addWidget(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.sync_button = QPushButton(tr("data_entry_sync", self.language))
        self.sync_button.clicked.connect(lambda: self.start_sync())
        self.refresh_button = QPushButton(tr("data_entry_refresh", self.language))
        self.refresh_button.setProperty("secondary", True)
        self.refresh_button.clicked.connect(self.refresh_records)
        self.new_record_button = QPushButton(tr("data_entry_new_record", self.language))
        self.new_record_button.setProperty("secondary", True)
        self.new_record_button.clicked.connect(lambda: self.open_new_record())
        self.search_input = QLineEdit("")
        self.search_input.setPlaceholderText(tr("data_entry_search_placeholder", self.language))
        self.search_input.returnPressed.connect(self.refresh_records)
        toolbar.addWidget(self.sync_button)
        toolbar.addWidget(self.refresh_button)
        toolbar.addWidget(self.new_record_button)
        toolbar.addWidget(self.search_input, 1)
        layout.addLayout(toolbar)

        self.sync_progress = QProgressBar()
        self.sync_progress.setRange(0, 0)
        self.sync_progress.setTextVisible(False)
        self.sync_progress.setVisible(False)
        layout.addWidget(self.sync_progress)

        self.status_label = QLabel("")
        self.status_label.setObjectName("MutedLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        splitter = QSplitter()
        splitter.setOrientation(Qt.Orientation.Horizontal)
        self.record_list = QListWidget()
        self.record_list.setObjectName("DataEntryRecordList")
        self.record_list.currentItemChanged.connect(lambda current, previous=None: self.open_selected_record())
        splitter.addWidget(self.record_list)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        self.form_widget = DataEntryFormWidget(language=self.language)
        right_layout.addWidget(self.form_widget.widget, 1)
        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.ai_fill_button = QPushButton(tr("data_entry_ai_fill_form", self.language))
        self.ai_fill_button.setProperty("secondary", True)
        self.ai_fill_button.clicked.connect(self.fill_current_form_with_ai)
        self.ai_fill_button.setEnabled(False)
        self.save_button = QPushButton(tr("data_entry_save_local", self.language))
        self.save_button.setProperty("secondary", True)
        self.save_button.clicked.connect(lambda: self.save_current_record(send=False))
        self.save_button.setEnabled(False)
        self.send_button = QPushButton(tr("data_entry_save_and_send", self.language))
        self.send_button.clicked.connect(lambda: self.save_current_record(send=True))
        self.send_button.setEnabled(False)
        action_row.addWidget(self.ai_fill_button)
        action_row.addStretch(1)
        action_row.addWidget(self.save_button)
        action_row.addWidget(self.send_button)
        right_layout.addLayout(action_row)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        self.refresh_project_state()

    def set_form_actions_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self.ai_fill_button.setEnabled(enabled and self._ai_thread is None)
        self.save_button.setEnabled(enabled)
        self.send_button.setEnabled(enabled)

    def on_dag_changed(self) -> None:
        option = self.dag_combo.currentData()
        if self.change_dag is None or not isinstance(option, dict) or option.get("active") or not option.get("switchable"):
            return
        self.change_dag(option)

    def refresh_project_state(self) -> None:
        from gui.clinical_main_window import configure_dag_switch_combo, format_project_user_context

        project = current_redcap_project_token(self.runtime.settings)
        if project is None:
            self.project_status.setObjectName("WarningPill")
            self.project_status.setText(tr("data_entry_project_missing", self.language))
            self.project_user_context.setText(tr("clinical_user_context_missing", self.language))
            self.sync_button.setEnabled(False)
            self.refresh_button.setEnabled(False)
            self.new_record_button.setEnabled(False)
            self.set_form_actions_enabled(False)
            self.record_list.clear()
            self.status_label.setText(tr("data_entry_connect_first", self.language))
        else:
            self.project_status.setObjectName("StatusPill")
            self.project_status.setText(tr("data_entry_project_ready", self.language, project=project.project_name))
            self.project_user_context.setText(format_project_user_context(project, self.language))
            self.sync_button.setEnabled(self._sync_thread is None)
            self.refresh_button.setEnabled(True)
            self.new_record_button.setEnabled(True)
        configure_dag_switch_combo(self.dag_combo, project, self.language)
        self.project_status.style().unpolish(self.project_status)
        self.project_status.style().polish(self.project_status)
        self.project_user_context.style().unpolish(self.project_user_context)
        self.project_user_context.style().polish(self.project_user_context)
        self.bundle = self.load_active_bundle()
        self.refresh_records()

    def load_active_bundle(self) -> WorkspaceBundle | None:
        project = current_redcap_project_token(self.runtime.settings)
        if project is None:
            return None
        for config_path in candidate_project_config_paths(self.runtime, project.project_id):
            if not config_path.exists():
                continue
            try:
                token = self.runtime.secrets_store.get(project.token_secret_name)
                if token and project_config_needs_event_labels(config_path):
                    ensure_server_metadata_in_config(config_path, api_url=project.api_url, api_token=token)
                bundle = load_workspace_bundle(config_path)
            except Exception as exc:
                self.status_label.setText(tr("data_entry_metadata_failed", self.language, error=str(exc)))
                return None
            if bundle.config.project_id and str(bundle.config.project_id) != str(project.project_id):
                continue
            return bundle
        self.status_label.setText(tr("data_entry_metadata_missing", self.language))
        return None

    def refresh_records(self) -> None:
        project = current_redcap_project_token(self.runtime.settings)
        self.record_list.clear()
        self.current_model = None
        self.set_form_actions_enabled(False)
        if project is None:
            return
        try:
            records = self.browser.list_records(
                project.project_id,
                search=self.search_input.text().strip(),
                dag_unique_name=project.data_access_group_unique_name,
                label_fields=data_entry_label_fields(self.runtime.app_config),
                limit=250,
            )
        except Exception as exc:
            self.status_label.setText(tr("data_entry_record_load_failed", self.language, error=str(exc)))
            return
        for record in records:
            item_text = record.record
            if record.label and record.label != record.record:
                item_text = f"{record.label} | {record.record}"
            flags = []
            if record.conflict:
                flags.append(tr("data_entry_conflict_flag", self.language))
            if record.pending_change_count:
                flags.append(tr("data_entry_pending_flag", self.language, count=record.pending_change_count))
            if flags:
                item_text = f"{item_text} ({', '.join(flags)})"
            self.record_list.addItem(item_text)
            self.record_list.item(self.record_list.count() - 1).setData(Qt.ItemDataRole.UserRole, record.record)
        self.status_label.setText(
            tr("data_entry_records_loaded", self.language, count=len(records))
            if records
            else tr("data_entry_no_records", self.language)
        )

    def open_selected_record(self) -> None:
        project = current_redcap_project_token(self.runtime.settings)
        current = self.record_list.currentItem()
        if project is None or current is None:
            return
        if self.bundle is None:
            self.bundle = self.load_active_bundle()
        if self.bundle is None:
            self.status_label.setText(tr("data_entry_metadata_missing", self.language))
            return
        record = str(current.data(Qt.ItemDataRole.UserRole))
        try:
            detail = self.browser.get_record_detail(project.project_id, record)
            model = build_form_render_model(
                detail,
                self.bundle.grouped_fields,
                form_labels=self.bundle.config.form_labels,
                event_labels=self.bundle.config.event_labels,
                form_event_map=self.bundle.config.form_event_map,
                repeating_forms=self.bundle.config.repeating_forms,
                repeating_events=self.bundle.config.repeating_events,
                title=tr("data_entry_record_title", self.language, record=record),
            )
        except Exception as exc:
            self.status_label.setText(tr("data_entry_record_open_failed", self.language, error=str(exc)))
            return
        self.current_model = model
        self.form_widget.set_model(model)
        self.set_form_actions_enabled(True)
        self.status_label.setText(tr("data_entry_record_opened", self.language, record=record))

    def open_new_record(self, tc_identity_no: str | None = None, dag_option: dict[str, Any] | None = None) -> None:
        project = current_redcap_project_token(self.runtime.settings)
        if project is None:
            self.status_label.setText(tr("data_entry_connect_first", self.language))
            return
        if self.bundle is None:
            self.bundle = self.load_active_bundle()
        if self.bundle is None:
            self.status_label.setText(tr("data_entry_metadata_missing", self.language))
            return
        if tc_identity_no is None:
            request = prompt_for_new_record(self.widget, project, self.language)
            if request is None:
                return
            tc_identity_no = request["tc_identity_no"]
            dag_option = request.get("dag_option")
        normalized_tc = normalize_tc_identity_no(tc_identity_no)
        if not normalized_tc:
            self.status_label.setText(tr("data_entry_new_record_missing_tc", self.language))
            return
        if dag_option is not None and not activate_dag_for_new_record(self, dag_option):
            return
        project = current_redcap_project_token(self.runtime.settings)
        if project is None:
            self.status_label.setText(tr("data_entry_connect_first", self.language))
            return
        token = self.runtime.secrets_store.get(project.token_secret_name)
        if not token:
            self.status_label.setText(tr("data_entry_missing_token", self.language))
            return
        try:
            identity_config = load_identity_registry_config(self.runtime.app_config)
            if not identity_config.api_url:
                identity_config.api_url = project.api_url
            identity_client = IdentityRegistryClient(identity_config, token)
            create_result = identity_client.create_record_by_tc(normalized_tc)
        except Exception as exc:
            self.status_label.setText(tr("data_entry_new_record_create_failed", self.language, error=str(exc)))
            return
        record_id = str(create_result.record_id or "").strip()
        if not record_id:
            self.status_label.setText(tr("data_entry_new_record_create_failed", self.language, error="record_id missing"))
            return
        detail = RecordDetail(
            project_id=project.project_id,
            record=record_id,
            dag_unique_name=project.data_access_group_unique_name,
            dirty=True,
        )
        self.current_model = build_form_render_model(
            detail,
            self.bundle.grouped_fields,
            form_labels=self.bundle.config.form_labels,
            event_labels=self.bundle.config.event_labels,
            form_event_map=self.bundle.config.form_event_map,
            repeating_forms=self.bundle.config.repeating_forms,
            repeating_events=self.bundle.config.repeating_events,
            title=tr("data_entry_record_title", self.language, record=record_id),
        )
        self.form_widget.set_model(self.current_model)
        self.record_list.clearSelection()
        self.set_form_actions_enabled(True)
        self.status_label.setText(
            tr(
                "data_entry_new_record_ready",
                self.language,
                record=record_id,
                tc=mask_tc_identity(normalized_tc),
            )
        )

    def save_current_record(self, *, send: bool = False) -> None:
        if self.current_model is None:
            return
        try:
            result = apply_form_changes(self.store, self.current_model, self.form_widget.collect_values())
        except Exception as exc:
            self.status_label.setText(tr("data_entry_save_failed", self.language, error=str(exc)))
            return
        queued_count = result.queued_count
        if send:
            try:
                submitted_count = self.submit_current_record_changes()
            except Exception as exc:
                self.status_label.setText(tr("data_entry_send_failed", self.language, error=str(exc)))
                return
            if queued_count == 0 and submitted_count == 0:
                self.status_label.setText(tr("data_entry_no_local_changes", self.language))
                return
            current_record = self.current_model.record
            self.refresh_records()
            select_record_in_list(self.record_list, current_record)
            self.status_label.setText(
                tr(
                    "data_entry_send_done",
                    self.language,
                    queued=queued_count,
                    submitted=submitted_count,
                )
            )
            return
        if queued_count == 0:
            self.status_label.setText(tr("data_entry_no_local_changes", self.language))
            return
        current_record = self.current_model.record
        self.refresh_records()
        select_record_in_list(self.record_list, current_record)
        self.status_label.setText(tr("data_entry_changes_queued", self.language, count=queued_count))

    def submit_current_record_changes(self) -> int:
        if self.current_model is None:
            return 0
        project = current_redcap_project_token(self.runtime.settings)
        if project is None:
            raise RuntimeError(tr("data_entry_connect_first", self.language))
        token = self.runtime.secrets_store.get(project.token_secret_name)
        if not token:
            raise RuntimeError(tr("data_entry_missing_token", self.language))
        pending = [
            item
            for item in self.store.pending_changes(project.project_id)
            if str(item.get("record")) == str(self.current_model.record)
        ]
        if not pending:
            return 0
        rows, change_ids = build_redcap_import_rows_from_pending(
            pending,
            model=self.current_model,
            bundle=self.bundle,
            app_config=self.runtime.app_config,
        )
        if not rows:
            return 0
        client = RedcapClient(project.api_url, token, timeout_seconds=600)
        client.import_records(rows, overwrite_behavior="normal", return_content="ids")
        for change_id in change_ids:
            self.store.mark_change_status(change_id, "submitted")
        remaining = [
            item
            for item in self.store.pending_changes(project.project_id)
            if str(item.get("record")) == str(self.current_model.record)
        ]
        if not remaining:
            self.store.mark_record_clean(project.project_id, self.current_model.record)
        return len(change_ids)

    def fill_current_form_with_ai(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        if self.current_model is None:
            return
        if self.bundle is None:
            self.status_label.setText(tr("data_entry_metadata_missing", self.language))
            return
        section = self.form_widget.current_section()
        if section is None:
            self.status_label.setText(tr("data_entry_ai_fill_no_form", self.language))
            return
        if self._ai_thread is not None:
            return
        start_dir = self.runtime.settings.ui.last_open_directory or str(Path.cwd())
        documents, _selected_filter = QFileDialog.getOpenFileNames(
            self.widget,
            tr("data_entry_ai_fill_select_documents", self.language),
            start_dir,
            "Documents (*.pdf *.txt *.docx *.doc *.rtf *.png *.jpg *.jpeg *.tif *.tiff);;All files (*)",
        )
        if not documents:
            return
        self.runtime.settings.ui.last_open_directory = str(Path(documents[0]).resolve().parent)
        if getattr(self.runtime, "settings_store", None) is not None:
            self.runtime.settings_store.save(self.runtime.settings)
        fill_options = prompt_ai_fill_options(
            self.widget,
            section=section,
            documents=[str(path) for path in documents],
            language=self.language,
            base_form_override=dict(self.bundle.config.form_overrides.get(section.form_name, {}) or {}),
            base_field_overrides={
                field.field_name: dict(self.bundle.config.field_overrides.get(field.field_name, {}) or {})
                for field in section.fields
            },
        )
        if fill_options is None:
            return
        field_names = set(fill_options["field_names"])
        config_snapshot = build_data_entry_ai_config(
            runtime=self.runtime,
            bundle=self.bundle,
            form_name=section.form_name,
            field_names=list(fill_options["field_names"]),
            form_override=dict(fill_options.get("form_override") or {}),
            field_overrides=dict(fill_options.get("field_overrides") or {}),
        )
        job = PendingPatientJob(
            queue_label=section.title,
            patient_mode="existing",
            identifier_type=None,
            identifier_value=None,
            documents=list(fill_options["documents"]),
            config_snapshot=config_snapshot,
        )
        from gui.progress_dialog import ExtractionProgressDialog

        progress = ExtractionProgressDialog(language=self.language, total=1, parent=self.widget)
        progress.setWindowTitle(tr("data_entry_ai_fill_form", self.language))
        progress.title_label.setText(tr("data_entry_ai_fill_running", self.language, form=section.title))
        progress.show()

        thread = QThread(self.widget)
        worker = PatientQueueExtractionWorker(jobs=[job])
        worker.moveToThread(thread)
        bridge = DataEntryAIFillBridge(page=self, progress=progress, field_names=field_names)
        self._ai_thread = thread
        self._ai_worker = worker
        self._ai_bridge = bridge
        self.ai_fill_button.setEnabled(False)
        self.status_label.setText(tr("data_entry_ai_fill_running", self.language, form=section.title))
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

    @Slot(object, object)
    def handle_ai_fill_success(self, values: dict[str, Any], field_names: set[str]) -> None:
        if not values:
            self.status_label.setText(tr("data_entry_ai_fill_no_values", self.language))
            return
        applied = self.form_widget.apply_values(values, field_names=field_names)
        self.status_label.setText(tr("data_entry_ai_fill_done", self.language, count=applied))

    @Slot(str)
    def handle_ai_fill_failure(self, error: str) -> None:
        self.status_label.setText(tr("data_entry_ai_fill_failed", self.language, error=error))

    @Slot()
    def cleanup_ai_thread(self) -> None:
        self._ai_thread = None
        self._ai_worker = None
        self._ai_bridge = None
        self.set_form_actions_enabled(self.current_model is not None)

    def start_sync(self, *, auto: bool = False) -> bool:
        project = current_redcap_project_token(self.runtime.settings)
        if project is None:
            if not auto:
                self.status_label.setText(tr("data_entry_connect_first", self.language))
            return False
        token = self.runtime.secrets_store.get(project.token_secret_name)
        if not token:
            self.status_label.setText(tr("data_entry_missing_token", self.language))
            return False
        if self._sync_thread is not None:
            return False
        logging.info("Data-entry sync started: project_id=%s auto=%s", project.project_id, auto)
        self.sync_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.sync_progress.setVisible(True)
        sync_config = load_data_entry_sync_config(self.runtime.app_config, api_url=project.api_url)
        self.status_label.setText(
            tr(
                "data_entry_sync_running_detail",
                self.language,
                prefix=sync_config.prefix,
                manifest=sync_config.manifest_action,
                data=sync_config.record_data_action,
                hashes=sync_config.identity_hash_action,
            )
        )
        thread = QThread(self.widget)
        worker = DataEntrySyncWorker(
            store_path=self.store.db_path,
            api_url=project.api_url,
            api_token=token,
            app_config=self.runtime.app_config,
        )
        worker.moveToThread(thread)
        self._sync_thread = thread
        self._sync_worker = worker
        thread.started.connect(worker.run)
        worker.finished.connect(self.handle_sync_success, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(self.handle_sync_failure, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self.cleanup_sync_thread, Qt.ConnectionType.QueuedConnection)
        thread.start()
        return True

    @Slot(object)
    def handle_sync_success(self, report: Any) -> None:
        logging.info(
            "Data-entry sync finished: project_id=%s pulled=%s conflicts=%s values=%s hashes=%s",
            getattr(report, "project_id", None),
            len(getattr(report, "pulled_records", []) or []),
            len(getattr(report, "conflict_records", []) or []),
            getattr(report, "values_updated", 0),
            getattr(report, "identity_hashes_updated", 0),
        )
        self.status_label.setText(
            tr(
                "data_entry_sync_done",
                self.language,
                manifest=getattr(report, "manifest_records", 0),
                pulled=len(getattr(report, "pulled_records", []) or []),
                conflicts=len(getattr(report, "conflict_records", []) or []),
                values=getattr(report, "values_updated", 0),
                hashes=getattr(report, "identity_hashes_updated", 0),
            )
        )
        self.refresh_records()

    @Slot(str)
    def handle_sync_failure(self, error: str) -> None:
        logging.info("Data-entry sync failed: %s", error)
        self.status_label.setText(tr("data_entry_sync_failed", self.language, error=error))

    @Slot()
    def cleanup_sync_thread(self) -> None:
        self._sync_thread = None
        self._sync_worker = None
        self.sync_progress.setVisible(False)
        self.sync_button.setEnabled(current_redcap_project_token(self.runtime.settings) is not None)
        self.refresh_button.setEnabled(current_redcap_project_token(self.runtime.settings) is not None)


def data_entry_store_path(app_home: str | Path) -> Path:
    return Path(app_home).expanduser().resolve() / "data_entry.sqlite3"


def current_redcap_project_token(settings: Any) -> RedcapProjectToken | None:
    redcap = getattr(settings, "redcap", None)
    selected_project_id = getattr(redcap, "selected_project_id", None)
    if not selected_project_id:
        return None
    for project in getattr(redcap, "saved_project_tokens", []) or []:
        if project.project_id == str(selected_project_id):
            return project
    return None


def candidate_project_config_paths(runtime: Any, project_id: str) -> list[Path]:
    candidates: list[Path] = []
    preferred = getattr(runtime.settings, "preferred_project_config_path", None)
    if preferred:
        candidates.append(Path(preferred).expanduser().resolve())
    app_home = Path(runtime.app_home).expanduser().resolve()
    candidates.append(app_home / "projects" / str(project_id) / f"project_config_{project_id}.json")
    deduped: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return deduped


def project_config_needs_event_labels(config_path: Path) -> bool:
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    event_labels = payload.get("event_labels")
    form_event_map = payload.get("form_event_map")
    if event_labels:
        return False
    if not isinstance(form_event_map, dict):
        return False
    return any(bool(events) for events in form_event_map.values())


def data_entry_label_fields(app_config: dict[str, Any]) -> list[str]:
    data_entry_config = app_config.get("data_entry")
    configured = data_entry_config.get("label_fields") if isinstance(data_entry_config, dict) else None
    if isinstance(configured, list) and configured:
        return [str(item) for item in configured if str(item)]
    return ["hasta_ad", "hasta_soyad", "patient_identifier", "record_id"]


def select_record_in_list(record_list: Any, record: str) -> None:
    for index in range(record_list.count()):
        item = record_list.item(index)
        if str(item.data(Qt.ItemDataRole.UserRole)) == str(record):
            record_list.setCurrentRow(index)
            return


def build_redcap_import_rows_from_pending(
    pending: list[dict[str, Any]],
    *,
    model: Any,
    bundle: WorkspaceBundle | None,
    app_config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[int]]:
    record_id_field = data_entry_record_id_field(app_config)
    fields_by_name = {field.field_name: field for field in getattr(model, "fields", [])}
    grouped_rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    change_ids: list[int] = []
    for change in pending:
        field_name = str(change.get("field_name") or "")
        if not field_name:
            continue
        field = fields_by_name.get(field_name) or fields_by_name.get(field_name.split("___", 1)[0])
        event_name = redcap_event_name_for_change(change, field, bundle)
        instance = str(change.get("instance") or "")
        repeat_instrument = redcap_repeat_instrument_for_change(change, field, bundle)
        row_key = (event_name, repeat_instrument, instance)
        row = grouped_rows.setdefault(row_key, {record_id_field: str(change.get("record") or model.record)})
        if event_name:
            row["redcap_event_name"] = event_name
        if repeat_instrument:
            row["redcap_repeat_instrument"] = repeat_instrument
        if instance:
            row["redcap_repeat_instance"] = instance
        row[field_name] = str(change.get("new_value") or "")
        if change.get("id") is not None:
            change_ids.append(int(change["id"]))
    reserved = {record_id_field, "redcap_event_name", "redcap_repeat_instrument", "redcap_repeat_instance"}
    rows = [row for row in grouped_rows.values() if any(key not in reserved for key in row)]
    return rows, change_ids


def data_entry_record_id_field(app_config: dict[str, Any]) -> str:
    payload = app_config.get("data_entry") if isinstance(app_config, dict) else None
    configured = payload.get("record_id_field") if isinstance(payload, dict) else None
    return str(configured or "record_id")


def redcap_event_name_for_change(change: dict[str, Any], field: Any, bundle: WorkspaceBundle | None) -> str:
    event_id = str(change.get("event_id") or "")
    if event_id and not event_id.isdigit():
        return event_id
    if bundle is None or field is None:
        return ""
    events = bundle.config.form_event_map.get(field.form_name) or []
    return str(events[0]).strip() if events else ""


def redcap_repeat_instrument_for_change(change: dict[str, Any], field: Any, bundle: WorkspaceBundle | None) -> str:
    if not str(change.get("instance") or ""):
        return ""
    if bundle is None or field is None:
        return ""
    repeating_forms = set(bundle.config.repeating_forms or [])
    return field.form_name if field.form_name in repeating_forms else ""


def prompt_ai_fill_options(
    parent: Any,
    *,
    section: Any,
    documents: list[str],
    language: str,
    base_form_override: dict[str, Any] | None = None,
    base_field_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    from gui.override_editor import edit_override_payload, override_summary
    from PySide6.QtWidgets import (
        QDialog,
        QDialogButtonBox,
        QFrame,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QPushButton,
        QSplitter,
        QVBoxLayout,
    )

    fields = [field for field in getattr(section, "fields", []) if field_is_ai_fillable(field)]
    if not fields:
        return None

    dialog = QDialog(parent)
    dialog.setWindowTitle(tr("data_entry_ai_fill_options_title", language))
    dialog.setMinimumSize(760, 600)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)

    title = QLabel(tr("data_entry_ai_fill_options_title", language))
    title.setObjectName("TitleLabel")
    layout.addWidget(title)

    body = QLabel(tr("data_entry_ai_fill_options_body", language, form=getattr(section, "title", "")))
    body.setObjectName("MutedLabel")
    body.setWordWrap(True)
    layout.addWidget(body)

    document_label = QLabel(
        tr(
            "data_entry_ai_fill_documents",
            language,
            count=len(documents),
            files=", ".join(Path(path).name for path in documents[:3])
            + ("..." if len(documents) > 3 else ""),
        )
    )
    document_label.setObjectName("MutedLabel")
    document_label.setWordWrap(True)
    layout.addWidget(document_label)

    content_splitter = QSplitter()
    content_splitter.setOrientation(Qt.Orientation.Horizontal)

    left_panel = QFrame()
    left_panel.setObjectName("PanelCard")
    left_layout = QVBoxLayout(left_panel)
    left_layout.setContentsMargins(12, 12, 12, 12)
    left_layout.setSpacing(8)

    fields_title = QLabel(tr("data_entry_ai_fill_fields_title", language))
    fields_title.setObjectName("SectionLabel")
    left_layout.addWidget(fields_title)

    field_list = QListWidget()
    field_list.setObjectName("DataEntryAIFillFieldList")
    field_list.setWordWrap(True)
    field_by_name: dict[str, Any] = {}
    for field in fields:
        field_by_name[field.field_name] = field
        item = QListWidgetItem(ai_fill_field_item_text(field, language))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setData(Qt.ItemDataRole.UserRole, field.field_name)
        item.setToolTip(f"{field.label}\n{field.field_name}")
        item.setCheckState(Qt.CheckState.Unchecked if field_currently_filled(field) else Qt.CheckState.Checked)
        field_list.addItem(item)
    left_layout.addWidget(field_list, 1)

    selection_row = QHBoxLayout()
    select_empty_button = QPushButton(tr("data_entry_ai_fill_select_empty", language))
    select_empty_button.setProperty("secondary", True)
    select_all_button = QPushButton(tr("data_entry_ai_fill_select_all", language))
    select_all_button.setProperty("secondary", True)
    clear_button = QPushButton(tr("data_entry_ai_fill_clear", language))
    clear_button.setProperty("secondary", True)
    selection_row.addWidget(select_empty_button)
    selection_row.addWidget(select_all_button)
    selection_row.addWidget(clear_button)
    left_layout.addLayout(selection_row)

    right_panel = QFrame()
    right_panel.setObjectName("PanelCard")
    right_layout = QVBoxLayout(right_panel)
    right_layout.setContentsMargins(12, 12, 12, 12)
    right_layout.setSpacing(8)

    form_rule_label = QLabel(tr("data_entry_ai_fill_form_rule", language))
    form_rule_label.setObjectName("SectionLabel")
    right_layout.addWidget(form_rule_label)
    form_rule_summary = QLabel("")
    form_rule_summary.setObjectName("MutedLabel")
    form_rule_summary.setWordWrap(True)
    right_layout.addWidget(form_rule_summary)
    edit_form_rule_button = QPushButton(tr("data_entry_ai_fill_edit_form_rule", language))
    edit_form_rule_button.setProperty("secondary", True)
    right_layout.addWidget(edit_form_rule_button)

    field_rule_label = QLabel(tr("data_entry_ai_fill_field_rule", language))
    field_rule_label.setObjectName("SectionLabel")
    right_layout.addWidget(field_rule_label)
    selected_field_label = QLabel(tr("data_entry_ai_fill_no_field_rule_target", language))
    selected_field_label.setObjectName("MutedLabel")
    selected_field_label.setWordWrap(True)
    right_layout.addWidget(selected_field_label)
    field_rule_summary = QLabel("")
    field_rule_summary.setObjectName("MutedLabel")
    field_rule_summary.setWordWrap(True)
    right_layout.addWidget(field_rule_summary)
    edit_field_rule_button = QPushButton(tr("data_entry_ai_fill_edit_field_rule", language))
    edit_field_rule_button.setProperty("secondary", True)
    edit_field_rule_button.setEnabled(False)
    right_layout.addWidget(edit_field_rule_button)
    right_layout.addStretch(1)

    content_splitter.addWidget(left_panel)
    content_splitter.addWidget(right_panel)
    content_splitter.setStretchFactor(0, 1)
    content_splitter.setStretchFactor(1, 1)
    layout.addWidget(content_splitter, 1)

    warning = QLabel("")
    warning.setObjectName("WarningPill")
    warning.setWordWrap(True)
    warning.setVisible(False)
    layout.addWidget(warning)

    base_form_override = dict(base_form_override or {})
    base_field_overrides = {
        str(field_name): dict(payload or {})
        for field_name, payload in (base_field_overrides or {}).items()
    }
    form_rule_payload: dict[str, Any] | None = None
    field_rule_payloads: dict[str, dict[str, Any]] = {}
    current_rule_field: str | None = None

    def current_form_payload() -> dict[str, Any]:
        return form_rule_payload if form_rule_payload is not None else base_form_override

    def load_current_field_rule(current: Any, _previous: Any = None) -> None:
        nonlocal current_rule_field
        if current is None:
            current_rule_field = None
            selected_field_label.setText(tr("data_entry_ai_fill_no_field_rule_target", language))
            field_rule_summary.setText(override_summary({}, language=language))
            edit_field_rule_button.setEnabled(False)
            return
        field_name = str(current.data(Qt.ItemDataRole.UserRole))
        current_rule_field = field_name
        field = field_by_name[field_name]
        selected_field_label.setText(f"{field.label} ({field.field_name})")
        field_rule_summary.setText(override_summary(current_field_payload(field_name), language=language))
        edit_field_rule_button.setEnabled(True)

    def current_field_payload(field_name: str) -> dict[str, Any]:
        if field_name in field_rule_payloads:
            return field_rule_payloads[field_name]
        return base_field_overrides.get(field_name, {})

    def update_form_rule_summary() -> None:
        form_rule_summary.setText(override_summary(current_form_payload(), language=language))

    def edit_form_rule() -> None:
        nonlocal form_rule_payload
        payload = edit_override_payload(
            parent=dialog,
            title=tr("selected_form_rules", language),
            subject_label=str(getattr(section, "title", "")),
            payload=current_form_payload(),
            language=language,
        )
        if payload is None:
            return
        form_rule_payload = payload
        update_form_rule_summary()

    def edit_field_rule() -> None:
        if not current_rule_field:
            return
        field = field_by_name[current_rule_field]
        payload = edit_override_payload(
            parent=dialog,
            title=tr("selected_field_rules", language),
            subject_label=f"{field.label} | {field.field_name}",
            payload=current_field_payload(current_rule_field),
            language=language,
        )
        if payload is None:
            return
        field_rule_payloads[current_rule_field] = payload
        field_rule_summary.setText(override_summary(payload, language=language))

    def set_checked(mode: str) -> None:
        for index in range(field_list.count()):
            item = field_list.item(index)
            field_name = str(item.data(Qt.ItemDataRole.UserRole))
            field = field_by_name[field_name]
            if mode == "all":
                checked = True
            elif mode == "empty":
                checked = not field_currently_filled(field)
            else:
                checked = False
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def selected_field_names() -> list[str]:
        names: list[str] = []
        for index in range(field_list.count()):
            item = field_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                names.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return names

    def accept_if_valid() -> None:
        if not selected_field_names():
            warning.setText(tr("data_entry_ai_fill_no_fields_selected", language))
            warning.setVisible(True)
            return
        dialog.accept()

    field_list.currentItemChanged.connect(load_current_field_rule)
    edit_form_rule_button.clicked.connect(lambda _checked=False: edit_form_rule())
    edit_field_rule_button.clicked.connect(lambda _checked=False: edit_field_rule())
    select_empty_button.clicked.connect(lambda _checked=False: set_checked("empty"))
    select_all_button.clicked.connect(lambda _checked=False: set_checked("all"))
    clear_button.clicked.connect(lambda _checked=False: set_checked("clear"))
    update_form_rule_summary()
    if field_list.count():
        field_list.setCurrentRow(0)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
    if ok_button is not None:
        ok_button.setText(tr("data_entry_ai_fill_start", language))
        ok_button.setAutoDefault(False)
        ok_button.setDefault(False)
    cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
    if cancel_button is not None:
        cancel_button.setText(tr("cancel_button", language))
    buttons.accepted.connect(accept_if_valid)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None

    chosen_fields = selected_field_names()
    return {
        "documents": documents,
        "field_names": chosen_fields,
        "form_override": form_rule_payload or {},
        "field_overrides": {
            field_name: payload
            for field_name, payload in field_rule_payloads.items()
            if field_name in chosen_fields and payload
        },
    }


def field_is_ai_fillable(field: Any) -> bool:
    return not bool(getattr(field, "read_only", False)) and getattr(field, "editor", "") not in {
        DESCRIPTION_EDITOR,
        READONLY_EDITOR,
    }


def field_currently_filled(field: Any) -> bool:
    from gui.data_entry_form import field_value_is_filled

    return field_value_is_filled(getattr(field, "value", ""))


def ai_fill_field_item_text(field: Any, language: str = "tr") -> str:
    status = (
        tr("data_entry_field_state_filled", language)
        if field_currently_filled(field)
        else tr("data_entry_field_state_empty", language)
    )
    required = (
        f" · {tr('data_entry_field_state_required_short', language)}"
        if bool(getattr(field, "required", False))
        else ""
    )
    return f"{field.label}\n{field.field_name} · {status}{required}"


def build_data_entry_ai_config(
    *,
    runtime: Any,
    bundle: WorkspaceBundle,
    form_name: str,
    field_names: list[str],
    form_override: dict[str, Any] | None,
    field_overrides: dict[str, dict[str, Any]] | None,
) -> Any:
    scoped_config = deepcopy(bundle.config)
    scoped_config.dictionary_path = str(bundle.config.dictionary_path)
    scoped_config.target_forms = [form_name]
    scoped_config.target_fields = list(field_names)
    scoped_config.llm = effective_data_entry_llm_settings(runtime, bundle)
    apply_ai_fill_overrides(
        scoped_config,
        form_name=form_name,
        form_override=form_override,
        field_overrides=field_overrides,
    )
    return scoped_config


def effective_data_entry_llm_settings(runtime: Any, bundle: WorkspaceBundle) -> dict[str, Any]:
    app_llm = dict((runtime.app_config or {}).get("llm", {}) or {})
    if not show_model_settings(runtime.app_config):
        return app_llm
    return merge_llm_settings(app_llm, bundle.config.llm)


def apply_ai_fill_overrides(
    config: Any,
    *,
    form_name: str,
    form_override: dict[str, Any] | None,
    field_overrides: dict[str, dict[str, Any]] | None,
) -> None:
    config.form_overrides = dict(getattr(config, "form_overrides", {}) or {})
    config.field_overrides = dict(getattr(config, "field_overrides", {}) or {})
    if form_override:
        config.form_overrides[form_name] = merged_override_payload(
            config.form_overrides.get(form_name, {}),
            form_override,
        )
    for field_name, payload in (field_overrides or {}).items():
        if not payload:
            continue
        config.field_overrides[field_name] = merged_override_payload(
            config.field_overrides.get(field_name, {}),
            payload,
        )


def merged_override_payload(existing: dict[str, Any] | None, override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing or {})
    for key, value in (override or {}).items():
        if value is None or value == "":
            merged.pop(key, None)
            continue
        merged[key] = value
    return merged


def prompt_for_new_record(parent: Any, project: RedcapProjectToken, language: str) -> dict[str, Any] | None:
    from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QVBoxLayout

    from gui.clinical_main_window import dag_option_label, normalize_dag_option

    dialog = QDialog(parent)
    dialog.setWindowTitle(tr("data_entry_new_record_title", language))
    layout = QVBoxLayout(dialog)
    form = QFormLayout()
    tc_input = QLineEdit("")
    tc_input.setPlaceholderText("12345678901")
    form.addRow(tr("data_entry_new_record_tc_label", language), tc_input)

    dag_combo = QComboBox()
    normalized_options = [
        normalize_dag_option(option, project)
        for option in (project.available_data_access_groups or [])
        if isinstance(option, dict)
    ]
    can_choose_dag = bool(project.can_switch_data_access_group) and len(normalized_options) > 1
    if can_choose_dag:
        for option in normalized_options:
            if not option.get("switchable") and not option.get("active"):
                continue
            dag_combo.addItem(dag_option_label(option, language), option)
        form.addRow(tr("data_entry_new_record_dag_label", language), dag_combo)
    layout.addLayout(form)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return {
        "tc_identity_no": tc_input.text().strip(),
        "dag_option": dag_combo.currentData() if can_choose_dag else None,
    }


def activate_dag_for_new_record(page: ClinicalDataEntryPage, option: dict[str, Any]) -> bool:
    if option.get("active"):
        return True
    if not option.get("switchable"):
        page.status_label.setText(tr("data_entry_new_record_dag_not_switchable", page.language))
        return False
    if page.change_dag is None:
        page.status_label.setText(tr("data_entry_new_record_dag_switch_failed", page.language))
        return False
    before = current_redcap_project_token(page.runtime.settings)
    page.change_dag(option)
    after = current_redcap_project_token(page.runtime.settings)
    if dag_option_matches_project(option, after) and not dag_option_matches_project(option, before):
        return True
    if dag_option_matches_project(option, after):
        return True
    page.status_label.setText(tr("data_entry_new_record_dag_switch_failed", page.language))
    return False


def dag_option_matches_project(option: dict[str, Any], project: RedcapProjectToken | None) -> bool:
    if project is None:
        return False
    if option.get("no_assignment"):
        return not project.data_access_group_unique_name and not project.data_access_group_id
    unique_name = option.get("data_access_group_unique_name")
    dag_id = option.get("data_access_group_id")
    return bool(
        (unique_name and unique_name == project.data_access_group_unique_name)
        or (dag_id and dag_id == project.data_access_group_id)
    )


def mask_tc_identity(value: str) -> str:
    cleaned = "".join(ch for ch in str(value) if ch.isdigit())
    if len(cleaned) < 4:
        return "***"
    return f"{cleaned[:2]}*******{cleaned[-2:]}"
