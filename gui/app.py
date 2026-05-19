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
    show_main_window(window)
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


def show_main_window(window) -> None:
    target = getattr(window, "_window", window)
    target.showMaximized()


def activate_window(window) -> None:
    target = getattr(window, "_window", window)
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        screen = window_screen(target, QApplication)
        target.setWindowState(
            target.windowState()
            & ~Qt.WindowState.WindowMinimized
            & ~Qt.WindowState.WindowFullScreen
        )
        if not target.isMaximized():
            target.showMaximized()
        if screen is not None:
            if not target.isMaximized():
                available = screen.availableGeometry()
                constrain_window_to_screen(target, available)
                QApplication.processEvents()
                place_window_within_screen(target, available)
        target.setWindowState(
            (target.windowState() & ~Qt.WindowState.WindowMinimized)
            | Qt.WindowState.WindowActive
        )
        target.raise_()
        target.activateWindow()
        geometry = target.geometry()
        frame = target.frameGeometry()
        logging.info(
            "Window activation requested: visible=%s active=%s geometry=%s,%s %sx%s frame=%s,%s %sx%s",
            target.isVisible(),
            target.isActiveWindow(),
            geometry.x(),
            geometry.y(),
            geometry.width(),
            geometry.height(),
            frame.x(),
            frame.y(),
            frame.width(),
            frame.height(),
        )
    except RuntimeError:
        logging.exception("Could not activate main window")


def window_screen(target, q_application):
    handle = target.windowHandle()
    if handle is not None and handle.screen() is not None:
        return handle.screen()
    frame = target.frameGeometry()
    screen = q_application.screenAt(frame.center())
    return screen or q_application.primaryScreen()


def constrain_window_to_screen(target, available_geometry) -> None:
    margin = 32
    frame = target.frameGeometry()
    geometry = target.geometry()
    frame_extra_width = max(0, frame.width() - geometry.width())
    frame_extra_height = max(0, frame.height() - geometry.height())
    max_width = max(420, available_geometry.width() - margin - frame_extra_width)
    max_height = max(360, available_geometry.height() - margin - frame_extra_height)
    width = min(target.width(), max_width)
    height = min(target.height(), max_height)
    if width != target.width() or height != target.height():
        target.resize(width, height)
        logging.info(
            "Window resized to fit screen: %sx%s available=%sx%s frame_extra=%sx%s",
            width,
            height,
            available_geometry.width(),
            available_geometry.height(),
            frame_extra_width,
            frame_extra_height,
        )


def place_window_within_screen(target, available_geometry) -> None:
    from PySide6.QtCore import QPoint

    edge_margin = 8
    frame = target.frameGeometry()
    frame.moveCenter(available_geometry.center())

    if frame.width() <= available_geometry.width():
        left = max(available_geometry.left(), min(frame.left(), available_geometry.right() - frame.width() + 1))
    else:
        left = available_geometry.left() + edge_margin
    if frame.height() <= available_geometry.height():
        top = max(available_geometry.top(), min(frame.top(), available_geometry.bottom() - frame.height() + 1))
    else:
        top = available_geometry.top() + edge_margin

    geometry = target.geometry()
    offset = geometry.topLeft() - target.frameGeometry().topLeft()
    target.move(QPoint(left, top) + offset)


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
