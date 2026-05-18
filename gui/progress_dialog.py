from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QPushButton, QVBoxLayout

from gui.i18n import tr


class ExtractionProgressDialog(QDialog):
    def __init__(self, *, language: str, total: int, parent=None) -> None:
        super().__init__(parent)
        self.language = language
        self._canceled = False
        self.total = total

        self.setWindowTitle(tr("run_patient_queue", self.language))
        self.setModal(True)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.title_label = QLabel(tr("extraction_progress_title", self.language))
        self.title_label.setObjectName("SectionLabel")
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(tr("extraction_progress_subtitle", self.language))
        self.subtitle_label.setObjectName("MutedLabel")
        self.subtitle_label.setWordWrap(True)
        layout.addWidget(self.subtitle_label)

        self.current_label = QLabel("")
        self.current_label.setWordWrap(True)
        layout.addWidget(self.current_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.cancel_button = QPushButton(tr("cancel_button", self.language))
        self.cancel_button.setProperty("secondary", True)
        self.cancel_button.clicked.connect(self.cancel)
        layout.addWidget(self.cancel_button, 0, Qt.AlignmentFlag.AlignRight)

    def update_progress(self, *, current: int, patient: str) -> None:
        self.progress_bar.setValue(current)
        display_current = self.total if current >= self.total else min(current + 1, self.total)
        self.current_label.setText(
            tr(
                "extraction_progress_item",
                self.language,
                current=display_current,
                total=self.total,
                patient=patient,
            )
        )

    def cancel(self) -> None:
        self._canceled = True
        self.reject()

    def was_canceled(self) -> bool:
        return self._canceled
