from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from gui.i18n import tr
from updater import macos_needs_portable_repair, repair_macos_portable_and_relaunch


def run_macos_portable_repair_check(app, runtime: Any) -> bool:
    if not macos_needs_portable_repair():
        return False
    if getattr(app, "_macos_portable_repair_prompted", False):
        return False

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

    app._macos_portable_repair_prompted = True
    app._macos_portable_repair_required = True
    language = runtime.settings.ui.language

    dialog = QMessageBox()
    dialog.setIcon(QMessageBox.Icon.Warning)
    dialog.setWindowTitle(tr("macos_repair_title", language))
    dialog.setText(tr("macos_repair_body", language))
    choose_button = dialog.addButton(
        tr("macos_repair_choose_folder", language),
        QMessageBox.ButtonRole.AcceptRole,
    )
    dialog.addButton(
        tr("macos_repair_later", language),
        QMessageBox.ButtonRole.RejectRole,
    )
    dialog.exec()
    if dialog.clickedButton() is not choose_button:
        logging.info("User skipped macOS portable repair")
        return False

    folder = QFileDialog.getExistingDirectory(
        None,
        tr("macos_repair_select_folder", language),
        str(Path.home() / "Downloads"),
    )
    if not folder:
        logging.info("User cancelled macOS portable repair folder selection")
        return False

    try:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        app_bundle = repair_macos_portable_and_relaunch(Path(folder))
        logging.info("macOS portable repair completed; relaunching %s", app_bundle)
    except Exception as exc:
        logging.warning("macOS portable repair failed: %s", exc)
        QMessageBox.warning(
            None,
            tr("macos_repair_title", language),
            tr("macos_repair_failed", language, error=str(exc)),
        )
        return False
    finally:
        QApplication.restoreOverrideCursor()

    QMessageBox.information(
        None,
        tr("macos_repair_title", language),
        tr("macos_repair_relaunch", language),
    )
    app.quit()
    return True
