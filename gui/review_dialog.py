from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QApplication,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.i18n import tr
from identity_registry_client import IdentityRegistryClient, IdentityRegistryError, load_identity_registry_config
from llm_provider import merge_llm_settings
from release_profile import show_model_settings
from redcap_client import RedcapClient, RedcapAPIError
from run_extraction import ExtractionFieldResult
from submission_service import (
    build_append_field_name_set,
    SubmissionValidationError,
    UnsubmittableFieldIssue,
    build_field_specs_by_name,
    collect_unsubmittable_review_fields,
    extract_record_id,
    export_review_results_to_excel,
    normalize_tc_identity_no,
    repair_unsubmittable_fields_for_submission,
    resolve_patient_submission_plan,
    submit_patient_plan,
)
from workspace_extraction import PatientExtractionResult
from workspace_flow import ensure_server_metadata_in_config, reload_workspace_bundle
from workspace_review import (
    count_patient_result_status,
    get_result_row_severity,
    parse_review_value,
    serialize_review_value,
)


class ReviewDialog(QDialog):
    def __init__(
        self,
        *,
        language: str,
        results: list[PatientExtractionResult],
        runtime=None,
        bundle=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.language = language
        self.results = results
        self.runtime = runtime
        self.bundle = bundle
        self.current_patient_index = 0
        self.current_field_index = 0
        self.field_specs_by_name = (
            build_field_specs_by_name(
                bundle.grouped_fields,
                append_fields=bundle.config.append_fields,
                dictionary_legend=bundle.config.dictionary_legend,
            )
            if bundle is not None
            else {}
        )
        self.append_field_names = (
            build_append_field_name_set(
                bundle.config.append_fields,
                bundle.config.dictionary_legend,
            )
            if bundle is not None
            else set()
        )
        self.repeating_form_names = set(bundle.config.repeating_forms or []) if bundle is not None else set()
        self.repeating_event_names = set(bundle.config.repeating_events or []) if bundle is not None else set()
        self.form_event_map = dict(bundle.config.form_event_map or {}) if bundle is not None else {}

        self.setWindowTitle(tr("review_dialog_title", self.language))
        self.setMinimumSize(900, 560)
        self.resize_for_available_screen()

        root = QVBoxLayout(self)
        root.setSpacing(16)

        header_card = QFrame()
        header_card.setObjectName("HeroCard")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(20, 20, 20, 20)
        header_layout.setSpacing(8)

        title = QLabel(tr("review_dialog_title", self.language))
        title.setObjectName("TitleLabel")
        header_layout.addWidget(title)

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("MutedLabel")
        self.summary_label.setWordWrap(True)
        header_layout.addWidget(self.summary_label)
        root.addWidget(header_card)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        patient_panel = self.build_patient_panel()
        field_panel = self.build_field_panel()
        detail_panel = self.build_detail_panel()
        splitter.addWidget(patient_panel)
        splitter.addWidget(field_panel)
        splitter.addWidget(detail_panel)
        splitter.setSizes([230, 650, 430])
        root.addWidget(splitter, 1)

        footer = QHBoxLayout()
        footer.setSpacing(12)
        self.export_button = QPushButton(tr("review_export_excel", self.language))
        self.export_button.clicked.connect(self.export_to_excel)
        self.submit_button = QPushButton(tr("review_submit_redcap", self.language))
        self.submit_button.clicked.connect(self.submit_to_redcap)
        self.approve_patient_button = QPushButton(tr("approve_selected_patient", self.language))
        self.approve_patient_button.clicked.connect(self.approve_current_patient)
        self.approve_all_button = QPushButton(tr("approve_all_patients", self.language))
        self.approve_all_button.clicked.connect(self.approve_all_patients)
        self.close_button = QPushButton(tr("close_button", self.language))
        self.close_button.setProperty("secondary", True)
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.export_button)
        footer.addWidget(self.submit_button)
        footer.addWidget(self.approve_patient_button)
        footer.addWidget(self.approve_all_button)
        footer.addStretch(1)
        footer.addWidget(self.close_button)
        root.addLayout(footer)

        self.populate_patient_list()
        self.refresh_summary()
        self.refresh_patient_action_state()

    def resize_for_available_screen(self) -> None:
        screen = None
        if self.parentWidget() is not None and self.parentWidget().windowHandle() is not None:
            screen = self.parentWidget().windowHandle().screen()
        screen = screen or QApplication.primaryScreen()
        if screen is None:
            self.resize(1180, 720)
            return
        available = screen.availableGeometry()
        margin = 48
        target_width = min(1180, max(self.minimumWidth(), available.width() - margin))
        target_height = min(720, max(self.minimumHeight(), available.height() - margin))
        self.resize(target_width, target_height)

    def refresh_submission_metadata(self, *, api_url: str, api_token: str) -> None:
        if self.bundle is None:
            return
        ensure_server_metadata_in_config(self.bundle.config_path, api_url=api_url, api_token=api_token)
        self.bundle = reload_workspace_bundle(self.bundle)
        self.field_specs_by_name = build_field_specs_by_name(
            self.bundle.grouped_fields,
            append_fields=self.bundle.config.append_fields,
            dictionary_legend=self.bundle.config.dictionary_legend,
        )
        self.append_field_names = build_append_field_name_set(
            self.bundle.config.append_fields,
            self.bundle.config.dictionary_legend,
        )
        self.repeating_form_names = set(self.bundle.config.repeating_forms or [])
        self.repeating_event_names = set(self.bundle.config.repeating_events or [])
        self.form_event_map = dict(self.bundle.config.form_event_map or {})

    def build_patient_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("PanelCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        title = QLabel(tr("review_patient_queue", self.language))
        title.setObjectName("SectionLabel")
        layout.addWidget(title)
        self.patient_list = QListWidget()
        self.patient_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.patient_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.patient_list.currentRowChanged.connect(self.on_patient_changed)
        layout.addWidget(self.patient_list, 1)
        return panel

    def build_field_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("PanelCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        self.field_title = QLabel(tr("review_field_results", self.language))
        self.field_title.setObjectName("SectionLabel")
        layout.addWidget(self.field_title)
        self.field_table = QTableWidget(0, 6)
        self.field_table.setHorizontalHeaderLabels(
            [
                tr("review_col_form", self.language),
                tr("review_col_field", self.language),
                tr("review_col_value", self.language),
                tr("review_col_status", self.language),
                tr("review_col_confidence", self.language),
                tr("review_col_review", self.language),
            ]
        )
        self.field_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.field_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.field_table.itemSelectionChanged.connect(self.on_field_selection_changed)
        self.field_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self.field_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.field_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.field_table.verticalHeader().setVisible(False)
        layout.addWidget(self.field_table, 1)
        return panel

    def build_detail_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("PanelCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        title = QLabel(tr("review_detail_title", self.language))
        title.setObjectName("SectionLabel")
        layout.addWidget(title)
        self.detail_lock_note = QLabel("")
        self.detail_lock_note.setObjectName("MutedLabel")
        self.detail_lock_note.setWordWrap(True)
        self.detail_lock_note.hide()
        layout.addWidget(self.detail_lock_note)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setColumnStretch(0, 0)
        form.setColumnStretch(1, 1)
        self.detail_field_name = QLabel("-")
        self.detail_form_name = QLabel("-")
        self.detail_value = QPlainTextEdit()
        self.detail_value.setMinimumHeight(72)
        self.detail_value_code = QLineEdit()
        self.detail_status = QLineEdit()
        self.detail_confidence = QDoubleSpinBox()
        self.detail_confidence.setRange(0.0, 1.0)
        self.detail_confidence.setDecimals(2)
        self.detail_confidence.setSingleStep(0.05)
        self.detail_needs_review = QCheckBox(tr("review_needs_review", self.language))
        self.detail_selection_reason = QPlainTextEdit()
        self.detail_selection_reason.setMinimumHeight(64)
        self.detail_review_reasons = QPlainTextEdit()
        self.detail_review_reasons.setMinimumHeight(64)
        self.candidate_list = QListWidget()
        self.candidate_list.setMinimumHeight(150)
        self.candidate_list.itemSelectionChanged.connect(self.on_candidate_changed)
        self.candidate_detail = QPlainTextEdit()
        self.candidate_detail.setMinimumHeight(100)
        self.candidate_detail.setReadOnly(True)
        self.use_candidate_button = QPushButton(tr("review_use_selected_candidate", self.language))
        self.use_candidate_button.clicked.connect(self.use_selected_candidate)

        row = 0
        form.addWidget(self.make_detail_label("review_detail_field"), row, 0)
        form.addWidget(self.detail_field_name, row, 1)
        row += 1
        form.addWidget(self.make_detail_label("review_detail_form"), row, 0)
        form.addWidget(self.detail_form_name, row, 1)
        row += 1
        form.addWidget(self.make_detail_label("review_detail_value"), row, 0, Qt.AlignmentFlag.AlignTop)
        form.addWidget(self.detail_value, row, 1)
        row += 1
        form.addWidget(self.make_detail_label("review_detail_value_code"), row, 0)
        form.addWidget(self.detail_value_code, row, 1)
        row += 1
        form.addWidget(self.make_detail_label("review_detail_status"), row, 0)
        form.addWidget(self.detail_status, row, 1)
        row += 1
        form.addWidget(self.make_detail_label("review_detail_confidence"), row, 0)
        form.addWidget(self.detail_confidence, row, 1)
        row += 1
        form.addWidget(QWidget(), row, 0)
        form.addWidget(self.detail_needs_review, row, 1)
        row += 1
        form.addWidget(self.make_detail_label("review_detail_selection_reason"), row, 0, Qt.AlignmentFlag.AlignTop)
        form.addWidget(self.detail_selection_reason, row, 1)
        row += 1
        form.addWidget(self.make_detail_label("review_detail_review_reasons"), row, 0, Qt.AlignmentFlag.AlignTop)
        form.addWidget(self.detail_review_reasons, row, 1)
        row += 1
        form.addWidget(self.make_detail_label("review_detail_candidates"), row, 0, Qt.AlignmentFlag.AlignTop)
        candidate_box = QVBoxLayout()
        candidate_box.setSpacing(8)
        candidate_box.addWidget(self.candidate_list)
        candidate_box.addWidget(self.candidate_detail)
        candidate_actions = QHBoxLayout()
        candidate_actions.addWidget(self.use_candidate_button)
        candidate_actions.addStretch(1)
        candidate_box.addLayout(candidate_actions)
        candidate_container = QWidget()
        candidate_container.setLayout(candidate_box)
        form.addWidget(candidate_container, row, 1)
        content_layout.addLayout(form)
        layout.addWidget(scroll, 1)

        action_row = QHBoxLayout()
        self.save_field_button = QPushButton(tr("review_save_field", self.language))
        self.save_field_button.clicked.connect(self.save_current_field)
        action_row.addWidget(self.save_field_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)
        return panel

    def refresh_summary(self) -> None:
        patient_count = len(self.results)
        found_count = 0
        review_count = 0
        approved_count = 0
        for result in self.results:
            found, review, _ = count_patient_result_status(result)
            found_count += found
            review_count += review
            if result.approved:
                approved_count += 1
        self.summary_label.setText(
            tr(
                "review_summary",
                self.language,
                patients=patient_count,
                found=found_count,
                review=review_count,
                approved=approved_count,
            )
        )

    def populate_patient_list(self, preserve_index: int | None = None, preserve_field_index: int | None = None) -> None:
        target_index = self.current_patient_index if preserve_index is None else preserve_index
        with QSignalBlocker(self.patient_list):
            self.patient_list.clear()
            for result in self.results:
                item = QListWidgetItem(self.patient_list_label(result))
                item.setData(Qt.ItemDataRole.UserRole, result)
                self.apply_patient_item_style(item, result)
                self.patient_list.addItem(item)
            if self.patient_list.count() > 0:
                target_index = max(0, min(target_index, self.patient_list.count() - 1))
                self.patient_list.setCurrentRow(target_index)
                self.current_patient_index = target_index
            else:
                self.current_patient_index = 0
        self.populate_field_table(preserve_row=preserve_field_index)

    def on_patient_changed(self, index: int) -> None:
        self.current_patient_index = max(0, index)
        self.populate_field_table()
        self.refresh_patient_action_state()

    def populate_field_table(self, preserve_row: int | None = None) -> None:
        patient = self.current_patient()
        self.field_table.setRowCount(0)
        if patient is None:
            self.clear_detail_panel()
            return
        self.field_title.setText(tr("review_field_results_for", self.language, patient=patient.queue_label))
        for row_index, result in enumerate(patient.merged_response.results):
            self.field_table.insertRow(row_index)
            values = [
                result.form_name or "",
                result.field_name,
                serialize_review_value(result.final_value),
                result.status,
                f"{(result.confidence or 0.0):.2f}" if result.confidence is not None else "-",
                tr("yes_short", self.language) if result.needs_review else tr("no_short", self.language),
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                self.field_table.setItem(row_index, column_index, item)
            self.apply_row_style(row_index, result)
        self.field_table.resizeColumnsToContents()
        if self.field_table.rowCount() > 0:
            target_row = 0 if preserve_row is None else max(0, min(preserve_row, self.field_table.rowCount() - 1))
            with QSignalBlocker(self.field_table):
                self.field_table.selectRow(target_row)
            self.current_field_index = target_row
            self.populate_detail_panel(target_row)
        else:
            self.clear_detail_panel()

    def apply_row_style(self, row_index: int, result: ExtractionFieldResult) -> None:
        severity = get_result_row_severity(result)
        if severity == "critical":
            color = QColor("#f8d7da")
        elif severity == "warning":
            color = QColor("#fff2cc")
        else:
            color = QColor("#eef8f4")
        for column_index in range(self.field_table.columnCount()):
            item = self.field_table.item(row_index, column_index)
            if item is not None:
                item.setBackground(QBrush(color))

    def on_field_selection_changed(self) -> None:
        selected = self.field_table.selectionModel().selectedRows()
        if not selected:
            return
        row_index = selected[0].row()
        self.current_field_index = row_index
        self.populate_detail_panel(row_index)

    def populate_detail_panel(self, row_index: int) -> None:
        result = self.current_field_result(row_index)
        if result is None:
            self.clear_detail_panel()
            return
        self.detail_field_name.setText(result.field_name)
        self.detail_form_name.setText(result.form_name or "-")
        self.detail_value.setPlainText(serialize_review_value(result.final_value))
        self.detail_value_code.setText(result.final_value_code or "")
        self.detail_status.setText(result.status)
        self.detail_confidence.setValue(float(result.confidence or 0.0))
        self.detail_needs_review.setChecked(bool(result.needs_review))
        self.detail_selection_reason.setPlainText(result.selection_reason or "")
        self.detail_review_reasons.setPlainText("\n".join(result.review_reasons or []))
        self.populate_candidates(result)
        self.refresh_patient_action_state()

    def save_current_field(self) -> None:
        patient = self.current_patient()
        if patient is not None and patient.approved:
            QMessageBox.information(
                self,
                tr("review_dialog_title", self.language),
                tr("review_edit_locked", self.language),
            )
            return
        result = self.current_field_result(self.current_field_index)
        if result is None:
            return
        result.final_value = parse_review_value(self.detail_value.toPlainText())
        result.final_value_code = self.detail_value_code.text().strip() or None
        result.status = self.detail_status.text().strip() or "found"
        result.confidence = float(self.detail_confidence.value())
        result.needs_review = bool(self.detail_needs_review.isChecked())
        result.selection_reason = self.detail_selection_reason.toPlainText().strip() or None
        review_reasons = [line.strip() for line in self.detail_review_reasons.toPlainText().splitlines() if line.strip()]
        result.review_reasons = review_reasons
        current_patient_index = self.current_patient_index
        current_field_index = self.current_field_index
        self.refresh_summary()
        self.populate_patient_list(preserve_index=current_patient_index, preserve_field_index=current_field_index)

    def approve_current_patient(self) -> None:
        patient = self.current_patient()
        if patient is None:
            return
        patient.approved = not patient.approved
        current_patient_index = self.current_patient_index
        self.refresh_summary()
        self.populate_patient_list(preserve_index=current_patient_index, preserve_field_index=self.current_field_index)

    def approve_all_patients(self) -> None:
        for patient in self.results:
            patient.approved = True
        self.refresh_summary()
        self.populate_patient_list(
            preserve_index=self.current_patient_index,
            preserve_field_index=self.current_field_index,
        )

    def current_patient(self) -> PatientExtractionResult | None:
        if self.current_patient_index < 0 or self.current_patient_index >= len(self.results):
            return None
        return self.results[self.current_patient_index]

    def current_field_result(self, row_index: int) -> ExtractionFieldResult | None:
        patient = self.current_patient()
        if patient is None:
            return None
        if row_index < 0 or row_index >= len(patient.merged_response.results):
            return None
        return patient.merged_response.results[row_index]

    def patient_list_label(self, result: PatientExtractionResult) -> str:
        found_count, review_count, total_count = count_patient_result_status(result)
        if result.approved:
            status = tr("review_patient_approved", self.language)
        elif review_count > 0:
            status = tr("review_patient_needs_review_short", self.language)
        else:
            status = tr("review_patient_ready_short", self.language)
        return tr(
            "review_patient_label_compact",
            self.language,
            patient=result.queue_label,
            found=found_count,
            total=total_count,
            status=status,
        )

    def apply_patient_item_style(self, item: QListWidgetItem, result: PatientExtractionResult) -> None:
        found_count, review_count, total_count = count_patient_result_status(result)
        if result.approved:
            color = QColor("#d9f2e3")
        elif review_count > 0:
            color = QColor("#fff2cc")
        else:
            color = QColor("#e7f1fb")
        item.setBackground(QBrush(color))
        approval = tr("review_patient_approved", self.language) if result.approved else tr("review_patient_pending", self.language)
        item.setToolTip(
            tr(
                "review_patient_tooltip",
                self.language,
                patient=result.queue_label,
                found=found_count,
                total=total_count,
                review=review_count,
                approval=approval,
            )
        )

    def populate_candidates(self, result: ExtractionFieldResult) -> None:
        with QSignalBlocker(self.candidate_list):
            self.candidate_list.clear()
        self.candidate_detail.setPlainText("")
        for candidate in result.candidates or []:
            item = QListWidgetItem(self.candidate_summary(candidate))
            item.setData(Qt.ItemDataRole.UserRole, candidate)
            self.candidate_list.addItem(item)
        if self.candidate_list.count() > 0:
            self.candidate_list.setCurrentRow(0)
        else:
            self.candidate_detail.setPlainText("-")
        self.refresh_patient_action_state()

    def on_candidate_changed(self) -> None:
        item = self.candidate_list.currentItem()
        if item is None:
            self.candidate_detail.setPlainText("")
            self.use_candidate_button.setEnabled(False)
            return
        candidate = item.data(Qt.ItemDataRole.UserRole) or {}
        lines = [
            f"{tr('review_candidate_value', self.language)}: {serialize_review_value(candidate.get('value_normalized')) or '-'}",
            f"{tr('review_candidate_code', self.language)}: {candidate.get('value_code') or '-'}",
            f"{tr('review_candidate_confidence', self.language)}: {candidate.get('confidence') if candidate.get('confidence') is not None else '-'}",
            f"{tr('review_candidate_evidence', self.language)}: {candidate.get('evidence') or '-'}",
            f"{tr('review_candidate_date', self.language)}: {candidate.get('context_date') or '-'}",
            f"{tr('review_candidate_context', self.language)}: {candidate.get('context_label') or '-'}",
        ]
        self.candidate_detail.setPlainText("\n".join(lines))
        patient = self.current_patient()
        self.use_candidate_button.setEnabled(patient is not None and not patient.approved)

    def use_selected_candidate(self) -> None:
        patient = self.current_patient()
        if patient is not None and patient.approved:
            return
        item = self.candidate_list.currentItem()
        if item is None:
            return
        candidate = item.data(Qt.ItemDataRole.UserRole) or {}
        self.detail_value.setPlainText(serialize_review_value(candidate.get("value_normalized")))
        self.detail_value_code.setText(str(candidate.get("value_code") or ""))
        confidence = candidate.get("confidence")
        self.detail_confidence.setValue(float(confidence or 0.0))
        evidence = candidate.get("evidence") or ""
        context_date = candidate.get("context_date") or ""
        if evidence or context_date:
            reason = tr(
                "review_candidate_applied_reason",
                self.language,
                evidence=evidence or "-",
                date=context_date or "-",
            )
            self.detail_selection_reason.setPlainText(reason)
        self.detail_needs_review.setChecked(False)

    def candidate_summary(self, candidate: dict[str, Any]) -> str:
        value = serialize_review_value(candidate.get("value_normalized")) or "-"
        code = candidate.get("value_code") or "-"
        confidence = candidate.get("confidence")
        confidence_text = "-" if confidence is None else f"{float(confidence):.2f}"
        context_date = candidate.get("context_date") or "-"
        return f"{value} | kod: {code} | guven: {confidence_text} | tarih: {context_date}"

    def clear_detail_panel(self) -> None:
        self.detail_field_name.setText("-")
        self.detail_form_name.setText("-")
        self.detail_value.setPlainText("")
        self.detail_value_code.setText("")
        self.detail_status.setText("")
        self.detail_confidence.setValue(0.0)
        self.detail_needs_review.setChecked(False)
        self.detail_selection_reason.setPlainText("")
        self.detail_review_reasons.setPlainText("")
        with QSignalBlocker(self.candidate_list):
            self.candidate_list.clear()
        self.candidate_detail.setPlainText("")
        self.refresh_patient_action_state()

    def refresh_patient_action_state(self) -> None:
        patient = self.current_patient()
        is_approved = bool(patient.approved) if patient is not None else False
        self.approve_patient_button.setText(
            tr("unapprove_selected_patient", self.language)
            if is_approved
            else tr("approve_selected_patient", self.language)
        )
        self.detail_lock_note.setVisible(is_approved)
        self.detail_lock_note.setText(tr("review_locked_notice", self.language) if is_approved else "")
        editable = patient is not None and not is_approved
        for widget in [
            self.detail_value,
            self.detail_value_code,
            self.detail_status,
            self.detail_confidence,
            self.detail_needs_review,
            self.detail_selection_reason,
            self.detail_review_reasons,
            self.candidate_list,
        ]:
            widget.setEnabled(editable)
        self.save_field_button.setEnabled(editable)
        self.use_candidate_button.setEnabled(editable and self.candidate_list.count() > 0)

    def export_to_excel(self) -> None:
        start_dir = str(self.runtime.app_home) if self.runtime is not None else ""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            tr("review_export_excel", self.language),
            str(start_dir or ""),
            "Excel Workbook (*.xlsx)",
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".xlsx"):
            file_path = f"{file_path}.xlsx"
        try:
            destination = export_review_results_to_excel(file_path, self.results, self.field_specs_by_name)
        except Exception as exc:
            QMessageBox.warning(
                self,
                tr("review_export_excel", self.language),
                tr("review_export_failed", self.language, error=str(exc)),
            )
            return
        QMessageBox.information(
            self,
            tr("review_export_excel", self.language),
            tr("review_export_success", self.language, path=str(destination)),
        )

    def submit_to_redcap(self) -> None:
        approved_results = [result for result in self.results if result.approved]
        if not approved_results:
            QMessageBox.warning(
                self,
                tr("review_submit_redcap", self.language),
                tr("review_no_approved_patients", self.language),
            )
            return
        if self.runtime is None:
            QMessageBox.warning(
                self,
                tr("review_submit_redcap", self.language),
                tr("review_submit_failed", self.language, error="runtime_missing"),
            )
            return

        token_secret_name = self.runtime.settings.redcap.selected_project_token_secret_name
        api_url = self.runtime.settings.redcap.api_url
        api_token = self.runtime.secrets_store.get(token_secret_name or "") if token_secret_name else None
        if not api_url or not api_token:
            QMessageBox.warning(
                self,
                tr("review_submit_redcap", self.language),
                tr("review_missing_redcap_token", self.language),
            )
            return

        identity_config = load_identity_registry_config(self.runtime.app_config)
        if not identity_config.api_url:
            identity_config.api_url = api_url or ""
        identity_client = IdentityRegistryClient(identity_config, api_token) if identity_config.enabled else None
        redcap_client = RedcapClient(api_url=api_url, api_token=api_token)
        self.refresh_submission_metadata(api_url=api_url, api_token=api_token)

        repaired_count, repair_warnings = self.repair_values_before_submission(approved_results)
        if repaired_count:
            self.populate_patient_list()
            self.populate_field_table()
            self.refresh_summary()

        unsubmittable_issues = collect_unsubmittable_review_fields(approved_results, self.field_specs_by_name)
        skipped_fields_by_patient: dict[int, set[str]] = {}
        pre_submit_warnings: list[str] = list(repair_warnings)
        if repaired_count:
            pre_submit_warnings.append(
                tr("review_value_repair_summary", self.language, count=repaired_count)
            )
        if unsubmittable_issues:
            answer = QMessageBox.warning(
                self,
                tr("review_submit_redcap", self.language),
                tr(
                    "review_unsubmittable_field_warning",
                    self.language,
                    count=len(unsubmittable_issues),
                    issues=self.format_unsubmittable_field_issues(unsubmittable_issues),
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            for issue in unsubmittable_issues:
                skipped_fields_by_patient.setdefault(issue.result_index, set()).add(issue.field_name)
                pre_submit_warnings.append(
                    f"{issue.queue_label}: {issue.field_name}: {self.format_unsubmittable_warning_code(issue)}"
                )

        plans = []
        blocking_errors: list[str] = []
        for patient_index, patient_result in enumerate(approved_results):
            manual_tc = None
            if patient_result.patient_mode in {"new", "auto"} and not (
                patient_result.patient_mode == "auto"
                and (patient_result.identifier_type == "record_id" or extract_record_id(patient_result))
            ):
                tc_from_result = normalize_tc_identity_no(
                    next(
                        (
                            item.final_value
                            for item in patient_result.merged_response.results
                            if item.field_name == "tc_kimlik_no"
                        ),
                        None,
                    )
                ) or (
                    normalize_tc_identity_no(patient_result.identifier_value)
                    if patient_result.identifier_type == "tc_kimlik_no"
                    else None
                )
                if tc_from_result is None:
                    manual_tc = self.prompt_for_tc_identity(patient_result.queue_label)
                    if not manual_tc:
                        blocking_errors.append(
                            f"{patient_result.queue_label}: {tr('review_error_missing_tc_identity', self.language)}"
                        )
                        continue
            try:
                excluded_field_names = set(self.append_field_names)
                excluded_field_names.update(skipped_fields_by_patient.get(patient_index, set()))
                plan = resolve_patient_submission_plan(
                    result=patient_result,
                    field_specs_by_name=self.field_specs_by_name,
                    append_field_names=excluded_field_names,
                    repeating_forms=self.repeating_form_names,
                    repeating_events=self.repeating_event_names,
                    form_event_map=self.form_event_map,
                    identity_client=identity_client,
                    manual_tc_identity_no=manual_tc,
                )
            except (SubmissionValidationError, IdentityRegistryError) as exc:
                blocking_errors.append(
                    f"{patient_result.queue_label}: {self.format_submission_error(str(exc))}"
                )
                continue
            plans.append(plan)

        if blocking_errors:
            QMessageBox.warning(
                self,
                tr("review_submit_redcap", self.language),
                tr("review_submission_blocked", self.language, errors="\n".join(blocking_errors)),
            )
            return

        submitted: list[str] = []
        warnings: list[str] = list(pre_submit_warnings)
        try:
            for plan in plans:
                if not plan.payload_rows:
                    warnings.append(f"{plan.queue_label}: {self.format_submission_error('no_submittable_fields')}")
                record_id = submit_patient_plan(
                    plan=plan,
                    redcap_client=redcap_client,
                    identity_client=identity_client,
                )
                submitted.append(f"{plan.queue_label} -> {record_id}")
                warnings.extend(f"{plan.queue_label}: {item}" for item in plan.warnings)
        except (SubmissionValidationError, RedcapAPIError, IdentityRegistryError) as exc:
            QMessageBox.warning(
                self,
                tr("review_submit_redcap", self.language),
                tr("review_submit_failed", self.language, error=self.format_submission_error(str(exc))),
            )
            return

        summary_lines = [tr("review_submit_success", self.language, count=len(submitted))]
        if submitted:
            summary_lines.append("\n".join(submitted))
        if warnings:
            summary_lines.append(tr("review_submit_warnings", self.language, warnings="\n".join(warnings)))
        QMessageBox.information(
            self,
            tr("review_submit_redcap", self.language),
            "\n\n".join(summary_lines),
        )

    def repair_values_before_submission(self, approved_results: list[PatientExtractionResult]) -> tuple[int, list[str]]:
        if not approved_results:
            return 0, []
        issues = collect_unsubmittable_review_fields(approved_results, self.field_specs_by_name)
        if not issues:
            return repair_unsubmittable_fields_for_submission(
                approved_results,
                self.field_specs_by_name,
                llm_settings=None,
                progress_callback=None,
            )

        progress = QProgressDialog(
            tr("review_value_repair_progress", self.language),
            "",
            0,
            0,
            self,
        )
        progress.setWindowTitle(tr("review_submit_redcap", self.language))
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.show()

        def update_progress(current: int, total: int, stage: str) -> None:
            if total > 0:
                progress.setRange(0, total)
                progress.setValue(max(0, min(current, total)))
            else:
                progress.setRange(0, 0)
            progress.setLabelText(
                tr("review_value_repair_progress_item", self.language, current=current, total=total)
            )
            QApplication.processEvents()

        try:
            return repair_unsubmittable_fields_for_submission(
                approved_results,
                self.field_specs_by_name,
                llm_settings=self.build_submission_llm_settings(),
                progress_callback=update_progress,
            )
        finally:
            progress.close()

    def build_submission_llm_settings(self) -> dict[str, Any] | None:
        if self.runtime is None or self.bundle is None:
            return None
        if not show_model_settings(self.runtime.app_config):
            return dict(self.runtime.app_config.get("llm", {}) or {})
        return merge_llm_settings(self.runtime.app_config.get("llm", {}), self.bundle.config.llm)

    def prompt_for_tc_identity(self, patient_label: str) -> str | None:
        while True:
            text, accepted = QInputDialog.getText(
                self,
                tr("review_tc_prompt_title", self.language),
                tr("review_tc_prompt_label", self.language, patient=patient_label),
            )
            if not accepted:
                return None
            normalized = normalize_tc_identity_no(text.strip())
            if normalized:
                return normalized
            QMessageBox.warning(
                self,
                tr("review_tc_prompt_title", self.language),
                tr("review_error_invalid_tc_identity", self.language),
            )

    def format_submission_error(self, error_text: str) -> str:
        if error_text == "missing_tc_identity":
            return tr("review_error_missing_tc_identity", self.language)
        if error_text == "identity_registry_required":
            return tr("review_error_identity_registry_required", self.language)
        if error_text == "identity_registry_create_failed":
            return tr("review_error_identity_registry_create_failed", self.language)
        if error_text == "record_id_not_found_for_tc":
            return tr("review_error_record_id_not_found_for_tc", self.language)
        if error_text == "missing_record_id":
            return tr("review_error_missing_record_id", self.language)
        if error_text == "unsupported_patient_identifier":
            return tr("review_error_unsupported_identifier", self.language)
        if error_text == "redcap_auto_id_not_returned":
            return tr("review_error_redcap_auto_id_not_returned", self.language)
        if error_text == "no_submittable_fields":
            return tr("review_error_no_submittable_fields", self.language)
        if error_text.startswith("duplicate_tc_identity:"):
            record_id = error_text.split(":", 1)[1].strip()
            return tr("review_error_duplicate_tc_identity", self.language, record_id=record_id or "-")
        if (
            error_text.startswith("Identity registry request failed with HTTP 403")
            and "API" in error_text
            and ("import" in error_text.lower() or "içe aktarma" in error_text.lower())
        ):
            return tr("review_error_identity_registry_api_import_forbidden", self.language)
        return error_text

    def format_unsubmittable_field_issues(self, issues: list[UnsubmittableFieldIssue], limit: int = 20) -> str:
        lines = []
        for issue in issues[:limit]:
            field_label = f" ({issue.field_label})" if issue.field_label and issue.field_label != issue.field_name else ""
            lines.append(
                f"- {issue.queue_label}: {issue.field_name}{field_label} = "
                f"{serialize_review_value(issue.value) or '-'}"
            )
        if len(issues) > limit:
            lines.append(tr("review_unsubmittable_choice_more", self.language, count=len(issues) - limit))
        return "\n".join(lines)

    def format_unsubmittable_warning_code(self, issue: UnsubmittableFieldIssue) -> str:
        if issue.reason == "invalid_date_format":
            return "skipped_invalid_date_format"
        if issue.reason == "invalid_number_format":
            return "skipped_invalid_number_format"
        if issue.reason == "number_out_of_range":
            return "skipped_number_out_of_range"
        return "skipped_choice_code_unmapped"

    def make_detail_label(self, key: str) -> QLabel:
        label = QLabel(tr(key, self.language))
        label.setObjectName("MutedLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        return label
