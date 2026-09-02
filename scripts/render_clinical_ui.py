from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from gui.clinical_main_window import ClinicalMainWindow
from gui.clinical_styles import CLINICAL_STYLE
from runtime_context import bootstrap_runtime
from settings_store import RedcapProjectToken


def build_preview_runtime(app_home: Path):
    runtime = bootstrap_runtime(app_home)
    project = RedcapProjectToken(
        api_url="https://preview.invalid/redcap/api/",
        project_id="101",
        project_name="Örnek Klinik Veri Projesi",
        token_secret_name="preview_token",
        username="demo-kullanici",
        data_access_group_id="1",
        data_access_group="Merkez Grubu",
        data_access_group_unique_name="merkez_grubu",
        can_switch_data_access_group=True,
        available_data_access_groups=[
            {
                "data_access_group_id": "1",
                "data_access_group": "Merkez Grubu",
                "data_access_group_unique_name": "merkez_grubu",
                "active": True,
                "switchable": True,
            },
            {
                "data_access_group_id": "2",
                "data_access_group": "Şube Grubu",
                "data_access_group_unique_name": "sube_grubu",
                "active": False,
                "switchable": True,
            },
        ],
    )
    secondary_project = RedcapProjectToken(
        api_url="https://preview.invalid/redcap/api/",
        project_id="102",
        project_name="Örnek İkinci Proje",
        token_secret_name="preview_token_secondary",
        username="preview-user",
    )
    runtime.settings.redcap.saved_project_tokens = [project, secondary_project]
    runtime.settings.redcap.selected_project_id = project.project_id
    runtime.settings.redcap.selected_project_name = project.project_name
    runtime.settings.redcap.selected_project_token_secret_name = project.token_secret_name
    return runtime


def render_pages(output_dir: Path, width: int, height: int) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(CLINICAL_STYLE)
    rendered: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="llm-extractor-ui-") as temp_dir:
        runtime = build_preview_runtime(Path(temp_dir))
        for page_key in ("home", "redcap", "import", "data_entry"):
            window = ClinicalMainWindow(runtime)
            target = window._window
            target.resize(width, height)
            target.show()
            app.processEvents()
            window.set_page(page_key)
            target.repaint()
            app.processEvents()
            image = QPixmap(target.size())
            image.fill()
            target.render(image)
            output_path = output_dir / f"{page_key}-{width}x{height}.png"
            if not image.save(str(output_path)):
                raise RuntimeError(f"Could not save preview: {output_path}")
            rendered.append(output_path)
            target.close()
            target.deleteLater()
            app.processEvents()
    return rendered


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render PHI-free clinical UI previews.")
    parser.add_argument("--output", type=Path, default=Path("build/ui-preview"))
    parser.add_argument("--width", type=int, default=1366)
    parser.add_argument("--height", type=int, default=768)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for path in render_pages(args.output.resolve(), args.width, args.height):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
