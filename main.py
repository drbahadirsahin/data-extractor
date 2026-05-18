from __future__ import annotations

import sys

from gui.app import launch_gui


def main() -> int:
    try:
        return launch_gui(sys.argv)
    except RuntimeError as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
