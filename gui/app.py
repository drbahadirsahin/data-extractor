from __future__ import annotations

import sys
import os

from release_profile import app_version
from runtime_context import bootstrap_runtime


def launch_gui(argv: list[str] | None = None) -> int:
    try:
        from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise RuntimeError(
            "PySide6 is not installed. Install PySide6 to run the desktop GUI."
        ) from exc

    runtime = bootstrap_runtime()
    app = QApplication(argv or sys.argv)
    install_qt_translations(app, runtime.settings.ui.language, QLibraryInfo, QLocale, QTranslator)
    app.setApplicationName("LLM Extractor")
    app.setApplicationVersion(app_version(runtime.app_config))

    from gui.startup_update import run_startup_update_check

    if run_startup_update_check(app, runtime):
        return 0

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
