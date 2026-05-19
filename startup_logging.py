from __future__ import annotations

import faulthandler
import logging
from pathlib import Path
import sys
import traceback

from settings_store import ensure_app_home, fallback_app_home

_LOG_HANDLE = None


def install_startup_logging() -> Path:
    log_path = startup_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_path),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    global _LOG_HANDLE
    try:
        _LOG_HANDLE = log_path.open("a", encoding="utf-8")
        faulthandler.enable(_LOG_HANDLE)
    except OSError:
        _LOG_HANDLE = None
    sys.excepthook = log_uncaught_exception
    logging.info("Startup logging initialized: %s", log_path)
    return log_path


def startup_log_path() -> Path:
    try:
        return ensure_app_home() / "llm_extractor.log"
    except Exception:
        fallback = fallback_app_home()
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback / "llm_extractor.log"


def log_uncaught_exception(exc_type, exc_value, exc_traceback) -> None:
    logging.critical(
        "Uncaught exception",
        exc_info=(exc_type, exc_value, exc_traceback),
    )
    if _LOG_HANDLE is not None:
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=_LOG_HANDLE)
        _LOG_HANDLE.flush()


def log_exception(message: str, exc: BaseException) -> None:
    logging.exception("%s: %s", message, exc)
