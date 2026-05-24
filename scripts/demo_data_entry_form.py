from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_entry_browser import DataEntryRecordBrowser
from data_entry_form_model import build_form_render_model
from data_entry_store import DataEntryStore, RedcapDataValue
from dictionary_parser import FieldSpec
from gui.clinical_styles import CLINICAL_STYLE
from gui.data_entry_form import DataEntryFormWidget


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication, QMainWindow, QScrollArea
    except ImportError:
        print("PySide6 is required for the data-entry form demo.")
        return 1

    temp_dir = tempfile.TemporaryDirectory()
    store = DataEntryStore(Path(temp_dir.name) / "data_entry_demo.sqlite3")
    store.initialize()
    store.upsert_remote_values(
        [
            RedcapDataValue("17", "", "1", "hasta_ad", "AB", remote_updated_at="2026-05-24T10:00:00Z"),
            RedcapDataValue("17", "", "1", "hasta_soyad", "CD", remote_updated_at="2026-05-24T10:00:00Z"),
            RedcapDataValue("17", "", "1", "cinsiyet", "1", remote_updated_at="2026-05-24T10:00:00Z"),
            RedcapDataValue("17", "", "1", "tanida_yas", "64", remote_updated_at="2026-05-24T10:00:00Z"),
            RedcapDataValue("17", "", "1", "risk___1", "1", remote_updated_at="2026-05-24T10:00:00Z"),
            RedcapDataValue("17", "", "1", "risk___2", "0", remote_updated_at="2026-05-24T10:00:00Z"),
            RedcapDataValue("17", "", "1", "notlar", "Demo not alani", remote_updated_at="2026-05-24T10:00:00Z"),
        ]
    )
    store.queue_local_change(
        project_id="17",
        record="1",
        field_name="hasta_ad",
        new_value="EF",
        base_remote_updated_at="2026-05-24T10:00:00Z",
    )
    fields = {
        "hasta_bilgileri": [
            FieldSpec("hasta_ad", "hasta_bilgileri", "text", "Hasta adi", required="y"),
            FieldSpec("hasta_soyad", "hasta_bilgileri", "text", "Hasta soyadi"),
            FieldSpec(
                "cinsiyet",
                "hasta_bilgileri",
                "radio",
                "Cinsiyet",
                "1, Erkek | 2, Kadin",
            ),
            FieldSpec(
                "tanida_yas",
                "hasta_bilgileri",
                "text",
                "Tanida yas",
                text_validation="integer",
                text_validation_min="0",
                text_validation_max="120",
            ),
            FieldSpec(
                "risk",
                "hasta_bilgileri",
                "checkbox",
                "Risk faktorleri",
                "1, Sigara | 2, Diyabet",
            ),
            FieldSpec("notlar", "hasta_bilgileri", "notes", "Notlar"),
            FieldSpec(
                "yardim_metni",
                "hasta_bilgileri",
                "descriptive",
                "Bu pencere veri giris renderer iskeletini gostermek icin uretilmistir.",
            ),
        ]
    }
    detail = DataEntryRecordBrowser(store).get_record_detail("17", "1")
    model = build_form_render_model(
        detail,
        fields,
        form_labels={"hasta_bilgileri": "Hasta Bilgileri"},
        title="Demo kayit 1",
    )

    app = QApplication(sys.argv)
    app.setStyleSheet(CLINICAL_STYLE)
    rendered = DataEntryFormWidget(model)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(rendered.widget)
    window = QMainWindow()
    window.setWindowTitle("Data Entry Form Demo")
    window.resize(920, 760)
    window.setCentralWidget(scroll)
    window.show()
    try:
        return app.exec()
    finally:
        temp_dir.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
