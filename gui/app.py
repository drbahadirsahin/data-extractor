from __future__ import annotations

import sys
import os
import logging

from release_profile import app_version
from runtime_context import bootstrap_runtime
from startup_logging import install_startup_logging, log_exception


def launch_gui(argv: list[str] | None = None) -> int:
    try:
        from PySide6.QtCore import QLibraryInfo, QLocale, QTimer, QTranslator
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise RuntimeError(
            "PySide6 is not installed. Install PySide6 to run the desktop GUI."
        ) from exc

    log_path = install_startup_logging()
    logging.info("Launching LLM Extractor")
    runtime = bootstrap_runtime()
    app = QApplication(argv or sys.argv)
    logging.info("Qt platform: %s", app.platformName())
    install_qt_translations(app, runtime.settings.ui.language, QLibraryInfo, QLocale, QTranslator)
    app.setApplicationName("LLM Extractor")
    app.setApplicationVersion(app_version(runtime.app_config))

    if resolve_ui_mode(runtime.app_config, argv or sys.argv) == "legacy":
        from gui.main_window import MainWindow
        from gui.styles import APP_STYLE

        app.setStyleSheet(APP_STYLE)
        window = MainWindow(runtime)
    else:
        from gui.clinical_main_window import ClinicalMainWindow
        from gui.clinical_styles import CLINICAL_STYLE

        app.setStyleSheet(CLINICAL_STYLE)
        window = ClinicalMainWindow(runtime)
    window.show()
    activate_window(window)
    app.processEvents()
    QTimer.singleShot(250, lambda: activate_window(window))
    QTimer.singleShot(750, lambda: activate_window(window))
    QTimer.singleShot(1500, lambda: run_deferred_macos_repair_check(app, runtime))
    QTimer.singleShot(3200, lambda: run_deferred_update_check(app, runtime))
    logging.info("Main window shown; log file: %s", log_path)
    return app.exec()


def install_qt_translations(app, language: str, q_library_info, q_locale, q_translator) -> None:
    if language != "tr":
        return
    translations_path = q_library_info.path(q_library_info.LibraryPath.TranslationsPath)
    translators = []
    q_locale.setDefault(q_locale("tr_TR"))
    for catalog in ["qtbase_tr", "qt_tr"]:
        translator = q_translator(app)
        if translator.load(catalog, translations_path):
            app.installTranslator(translator)
            translators.append(translator)
    app._llm_extractor_translators = translators


def resolve_ui_mode(app_config: dict, argv: list[str] | None = None) -> str:
    argv = argv or []
    if "--legacy-ui" in argv or "--dev-ui" in argv:
        return "legacy"
    env_mode = os.getenv("LLM_EXTRACTOR_UI_MODE")
    if env_mode:
        return normalize_ui_mode(env_mode)
    configured = app_config.get("ui", {}).get("mode") if isinstance(app_config.get("ui"), dict) else None
    return normalize_ui_mode(configured or "clinical")


def normalize_ui_mode(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized in {"legacy", "dev", "developer", "advanced"}:
        return "legacy"
    return "clinical"


def activate_window(window) -> None:
    target = getattr(window, "_window", window)
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            frame = target.frameGeometry()
            frame.moveCenter(available.center())
            target.move(frame.topLeft())
        target.setWindowState(
            (target.windowState() & ~Qt.WindowState.WindowMinimized)
            | Qt.WindowState.WindowActive
        )
        target.showNormal()
        target.raise_()
        target.activateWindow()
        geometry = target.geometry()
        logging.info(
            "Window activation requested: visible=%s active=%s geometry=%s,%s %sx%s",
            target.isVisible(),
            target.isActiveWindow(),
            geometry.x(),
            geometry.y(),
            geometry.width(),
            geometry.height(),
        )
    except RuntimeError:
        logging.exception("Could not activate main window")


def run_deferred_update_check(app, runtime) -> None:
    try:
        from updater import macos_needs_portable_repair

        if macos_needs_portable_repair():
            logging.info("Skipping update check until macOS portable repair is completed")
            return
        from gui.startup_update import run_startup_update_check_async

        run_startup_update_check_async(app, runtime)
    except Exception as exc:
        log_exception("Deferred update check failed", exc)


def run_deferred_macos_repair_check(app, runtime) -> None:
    try:
        from gui.macos_repair import run_macos_portable_repair_check

        run_macos_portable_repair_check(app, runtime)
    except Exception as exc:
        log_exception("Deferred macOS portable repair check failed", exc)
