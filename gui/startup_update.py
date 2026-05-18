from __future__ import annotations

from typing import Any

from gui.i18n import tr
from release_profile import startup_updates_enabled
from updater import check_for_update, download_update, is_frozen_app, stage_update_and_restart


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
