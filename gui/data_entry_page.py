from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from data_entry_browser import DataEntryRecordBrowser
from data_entry_form_changes import apply_form_changes
from data_entry_form_model import build_form_render_model
from data_entry_store import DataEntryStore
from data_entry_sync_client import DataEntrySyncClient, load_data_entry_sync_config
from data_entry_sync_service import DataEntrySyncService
from gui.data_entry_form import DataEntryFormWidget
from gui.i18n import tr
from settings_store import RedcapProjectToken
from workspace_flow import WorkspaceBundle, load_workspace_bundle


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


class ClinicalDataEntryPage:
    def __init__(self, runtime: Any) -> None:
        from PySide6.QtWidgets import (
            QFrame,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QListWidget,
            QPushButton,
            QScrollArea,
            QSplitter,
            QVBoxLayout,
            QWidget,
        )

        self.runtime = runtime
        self.language = runtime.settings.ui.language
        self.store = DataEntryStore(data_entry_store_path(runtime.app_home))
        self.browser = DataEntryRecordBrowser(self.store)
        self.bundle: WorkspaceBundle | None = None
        self.current_model = None
        self._sync_thread: QThread | None = None
        self._sync_worker: DataEntrySyncWorker | None = None

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
        header_layout.addWidget(self.project_status)
        layout.addWidget(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.sync_button = QPushButton(tr("data_entry_sync", self.language))
        self.sync_button.clicked.connect(self.start_sync)
        self.refresh_button = QPushButton(tr("data_entry_refresh", self.language))
        self.refresh_button.setProperty("secondary", True)
        self.refresh_button.clicked.connect(self.refresh_records)
        self.search_input = QLineEdit("")
        self.search_input.setPlaceholderText(tr("data_entry_search_placeholder", self.language))
        self.search_input.returnPressed.connect(self.refresh_records)
        toolbar.addWidget(self.sync_button)
        toolbar.addWidget(self.refresh_button)
        toolbar.addWidget(self.search_input, 1)
        layout.addLayout(toolbar)

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
        self.form_widget = DataEntryFormWidget()
        self.form_scroll = QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setWidget(self.form_widget.widget)
        right_layout.addWidget(self.form_scroll, 1)
        self.save_button = QPushButton(tr("data_entry_save_local", self.language))
        self.save_button.clicked.connect(self.save_current_record)
        self.save_button.setEnabled(False)
        right_layout.addWidget(self.save_button, 0, Qt.AlignmentFlag.AlignRight)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("MutedLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.refresh_project_state()

    def refresh_project_state(self) -> None:
        project = current_redcap_project_token(self.runtime.settings)
        if project is None:
            self.project_status.setObjectName("WarningPill")
            self.project_status.setText(tr("data_entry_project_missing", self.language))
            self.sync_button.setEnabled(False)
            self.refresh_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self.record_list.clear()
            self.status_label.setText(tr("data_entry_connect_first", self.language))
        else:
            self.project_status.setObjectName("StatusPill")
            self.project_status.setText(tr("data_entry_project_ready", self.language, project=project.project_name))
            self.sync_button.setEnabled(self._sync_thread is None)
            self.refresh_button.setEnabled(True)
        self.project_status.style().unpolish(self.project_status)
        self.project_status.style().polish(self.project_status)
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
        self.save_button.setEnabled(False)
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
                title=tr("data_entry_record_title", self.language, record=record),
            )
        except Exception as exc:
            self.status_label.setText(tr("data_entry_record_open_failed", self.language, error=str(exc)))
            return
        self.current_model = model
        self.form_widget.set_model(model)
        self.save_button.setEnabled(True)
        self.status_label.setText(tr("data_entry_record_opened", self.language, record=record))

    def save_current_record(self) -> None:
        if self.current_model is None:
            return
        try:
            result = apply_form_changes(self.store, self.current_model, self.form_widget.collect_values())
        except Exception as exc:
            self.status_label.setText(tr("data_entry_save_failed", self.language, error=str(exc)))
            return
        if result.queued_count == 0:
            self.status_label.setText(tr("data_entry_no_local_changes", self.language))
            return
        current_record = self.current_model.record
        self.refresh_records()
        select_record_in_list(self.record_list, current_record)
        self.status_label.setText(tr("data_entry_changes_queued", self.language, count=result.queued_count))

    def start_sync(self) -> None:
        project = current_redcap_project_token(self.runtime.settings)
        if project is None:
            self.status_label.setText(tr("data_entry_connect_first", self.language))
            return
        token = self.runtime.secrets_store.get(project.token_secret_name)
        if not token:
            self.status_label.setText(tr("data_entry_missing_token", self.language))
            return
        if self._sync_thread is not None:
            return
        self.sync_button.setEnabled(False)
        self.status_label.setText(tr("data_entry_sync_running", self.language))
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

    @Slot(object)
    def handle_sync_success(self, report: Any) -> None:
        self.status_label.setText(
            tr(
                "data_entry_sync_done",
                self.language,
                pulled=len(getattr(report, "pulled_records", []) or []),
                conflicts=len(getattr(report, "conflict_records", []) or []),
                hashes=getattr(report, "identity_hashes_updated", 0),
            )
        )
        self.refresh_records()

    @Slot(str)
    def handle_sync_failure(self, error: str) -> None:
        self.status_label.setText(tr("data_entry_sync_failed", self.language, error=error))

    @Slot()
    def cleanup_sync_thread(self) -> None:
        self._sync_thread = None
        self._sync_worker = None
        self.sync_button.setEnabled(current_redcap_project_token(self.runtime.settings) is not None)


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
