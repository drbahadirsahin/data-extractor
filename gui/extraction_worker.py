from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from project_config import ProjectConfig
from workspace_extraction import PatientExtractionResult, extract_patient_documents


@dataclass
class PendingPatientJob:
    queue_label: str
    patient_mode: str
    identifier_type: str | None
    identifier_value: str | None
    documents: list[str]
    config_snapshot: ProjectConfig


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
