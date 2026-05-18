from __future__ import annotations

import sys
import traceback

from startup_logging import install_startup_logging, log_exception

from gui.app import launch_gui


def main() -> int:
    try:
        return launch_gui(sys.argv)
    except RuntimeError as exc:
        log_exception("Runtime startup failure", exc)
        print(str(exc))
        return 1
    except Exception as exc:
        try:
            install_startup_logging()
            log_exception("Unhandled startup failure", exc)
        finally:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
