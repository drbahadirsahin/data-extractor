from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from gui.i18n import tr
from release_profile import app_version, startup_updates_enabled
from updater import (
    check_for_update,
    download_update,
    is_frozen_app,
    stage_update_and_restart,
    validate_self_update_target,
)


def run_startup_update_check(app, runtime: Any) -> bool:
    if not startup_updates_enabled(runtime.app_config):
        return False
    if not is_frozen_app():
        return False

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox, QProgressDialog

    language = runtime.settings.ui.language
    progress = QProgressDialog(
        tr("update_checking", language),
        "",
        0,
        0,
    )
    progress.setWindowTitle(tr("update_title", language))
    progress.setCancelButton(None)
    progress.setMinimumDuration(0)
    progress.setWindowModality(Qt.WindowModality.ApplicationModal)
    progress.show()
    app.processEvents()

    try:
        update = check_for_update(runtime.app_config)
        if not update:
            return False
        validate_self_update_target()
        progress.setLabelText(tr("update_downloading", language, version=update["version"]))

        def update_download_progress(current: int, total: int) -> None:
            if total > 0:
                progress.setRange(0, total)
                progress.setValue(max(0, min(current, total)))
            else:
                progress.setRange(0, 0)
            app.processEvents()

        archive_path = download_update(update["payload"], progress_callback=update_download_progress)
        progress.setLabelText(tr("update_installing", language))
        app.processEvents()
        stage_update_and_restart(archive_path)
        QMessageBox.information(
            None,
            tr("update_title", language),
            tr("update_restart_now", language),
        )
        app.quit()
        return True
    except Exception as exc:
        QMessageBox.warning(
            None,
            tr("update_title", language),
            tr("update_failed", language, error=str(exc)),
        )
        return False
    finally:
        progress.close()


def run_startup_update_check_async(app, runtime: Any) -> bool:
    if not startup_updates_enabled(runtime.app_config):
        return False
    if not is_frozen_app():
        return False

    from PySide6.QtCore import QObject, QThread, Signal, Slot

    class Worker(QObject):
        status_changed = Signal(str, object)
        progress_changed = Signal(int, int)
        archive_ready = Signal(str, str)
        no_update = Signal()
        failed = Signal(str)
        finished = Signal()

        def __init__(self, app_config: dict[str, Any]) -> None:
            super().__init__()
            self._app_config = app_config

        @Slot()
        def run(self) -> None:
            try:
                logging.info("Startup update check started: current=%s", app_version(self._app_config))
                self.status_changed.emit("checking", None)
                update = check_for_update(self._app_config)
                if not update:
                    self.no_update.emit()
                    return
                validate_self_update_target()
                version = str(update.get("version") or "")
                self.status_changed.emit("downloading", version)
                archive_path = download_update(
                    update["payload"],
                    progress_callback=lambda current, total: self.progress_changed.emit(current, total),
                )
                self.archive_ready.emit(str(archive_path), version)
            except Exception as exc:
                self.failed.emit(str(exc))
            finally:
                self.finished.emit()

    class Controller(QObject):
        def __init__(self) -> None:
            super().__init__(app)
            self._language = runtime.settings.ui.language
            self._progress = None
            self._thread = QThread(self)
            self._worker = Worker(runtime.app_config)
            self._worker.moveToThread(self._thread)
            self._thread.started.connect(self._worker.run)
            self._worker.status_changed.connect(self._on_status_changed)
            self._worker.progress_changed.connect(self._on_progress_changed)
            self._worker.archive_ready.connect(self._on_archive_ready)
            self._worker.no_update.connect(self._on_no_update)
            self._worker.failed.connect(self._on_failed)
            self._worker.finished.connect(self._thread.quit)
            self._worker.finished.connect(self._worker.deleteLater)
            self._thread.finished.connect(self._thread.deleteLater)
            self._thread.finished.connect(self._on_thread_finished)

        def start(self) -> None:
            self._thread.start()

        def _ensure_progress(self, label_text: str | None = None):
            if self._progress is not None:
                if label_text is not None:
                    self._progress.setLabelText(label_text)
                return self._progress
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QProgressDialog

            self._progress = QProgressDialog(
                label_text or tr("update_checking", self._language),
                "",
                0,
                0,
            )
            self._progress.setWindowTitle(tr("update_title", self._language))
            self._progress.setCancelButton(None)
            self._progress.setMinimumDuration(0)
            self._progress.setWindowModality(Qt.WindowModality.ApplicationModal)
            self._progress.show()
            return self._progress

        def _on_status_changed(self, status: str, payload: object) -> None:
            logging.info("Startup update status: %s", status)
            if status == "checking":
                self._ensure_progress(tr("update_checking", self._language))
            if status == "downloading":
                progress = self._ensure_progress(
                    tr("update_downloading", self._language, version=str(payload or ""))
                )
                progress.setLabelText(
                    tr("update_downloading", self._language, version=str(payload or ""))
                )

        def _on_progress_changed(self, current: int, total: int) -> None:
            progress = self._ensure_progress()
            if total > 0:
                progress.setRange(0, total)
                progress.setValue(max(0, min(current, total)))
            else:
                progress.setRange(0, 0)

        def _on_archive_ready(self, archive_path: str, _version: str) -> None:
            from PySide6.QtWidgets import QMessageBox

            progress = self._ensure_progress()
            progress.setLabelText(tr("update_installing", self._language))
            try:
                stage_update_and_restart(Path(archive_path))
            except Exception as exc:
                self._on_failed(str(exc))
                return
            QMessageBox.information(
                None,
                tr("update_title", self._language),
                tr("update_restart_now", self._language),
            )
            app.quit()

        def _on_no_update(self) -> None:
            logging.info("No startup update available")
            if self._progress is not None:
                self._progress.close()
                self._progress = None

        def _on_failed(self, error: str) -> None:
            from PySide6.QtWidgets import QMessageBox

            logging.warning("Startup update check failed: %s", error)
            if self._progress is not None:
                self._progress.close()
                self._progress = None
            QMessageBox.warning(
                None,
                tr("update_title", self._language),
                tr("update_failed", self._language, error=error),
            )

        def _on_thread_finished(self) -> None:
            if self._progress is not None:
                self._progress.close()
            controllers = getattr(app, "_startup_update_controllers", [])
            if self in controllers:
                controllers.remove(self)

    controller = Controller()
    controllers = getattr(app, "_startup_update_controllers", [])
    controllers.append(controller)
    app._startup_update_controllers = controllers
    controller.start()
    return True
