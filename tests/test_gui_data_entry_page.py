import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from data_entry_store import DataEntryStore, RedcapDataValue
from gui.data_entry_page import ClinicalDataEntryPage, data_entry_store_path
from settings_store import AppSettings, RedcapProjectToken


def get_qapplication():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class FakeSecretsStore:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, key):
        return self.values.get(key)


class GuiDataEntryPageTests(unittest.TestCase):
    def test_page_lists_local_records_and_queues_form_changes(self) -> None:
        get_qapplication()
        with tempfile.TemporaryDirectory() as temp_dir:
            app_home = Path(temp_dir)
            config_path = write_project_config(app_home)
            store = DataEntryStore(data_entry_store_path(app_home))
            store.initialize()
            store.upsert_remote_values(
                [
                    RedcapDataValue(
                        project_id="17",
                        event_id="",
                        record="1",
                        field_name="hasta_ad",
                        value="AB",
                        remote_updated_at="2026-05-24T10:00:00Z",
                    ),
                    RedcapDataValue(
                        project_id="17",
                        event_id="",
                        record="1",
                        field_name="hasta_soyad",
                        value="CD",
                        remote_updated_at="2026-05-24T10:00:00Z",
                    ),
                ]
            )
            runtime = build_runtime(app_home, config_path)

            page = ClinicalDataEntryPage(runtime)

            self.assertEqual(page.record_list.count(), 1)
            page.record_list.setCurrentRow(0)
            self.assertIsNotNone(page.current_model)
            self.assertEqual(page.current_model.record, "1")
            page.form_widget.editor_widgets["hasta_ad"].setText("EF")

            page.save_current_record()

            pending = store.pending_changes("17")
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["field_name"], "hasta_ad")
            self.assertEqual(pending[0]["new_value"], "EF")

    def test_page_requires_active_redcap_project(self) -> None:
        get_qapplication()
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = AppSettings()
            runtime = SimpleNamespace(
                app_home=Path(temp_dir),
                settings=settings,
                app_config={},
                secrets_store=FakeSecretsStore(),
            )

            page = ClinicalDataEntryPage(runtime)

            self.assertFalse(page.sync_button.isEnabled())
            self.assertEqual(page.record_list.count(), 0)


def build_runtime(app_home: Path, config_path: Path):
    settings = AppSettings()
    settings.ui.language = "tr"
    settings.preferred_project_config_path = str(config_path)
    settings.redcap.selected_project_id = "17"
    settings.redcap.selected_project_name = "Demo"
    settings.redcap.selected_project_token_secret_name = "redcap_api_token_17"
    settings.redcap.saved_project_tokens = [
        RedcapProjectToken(
            api_url="https://redcap.example/api/",
            project_id="17",
            project_name="Demo",
            token_secret_name="redcap_api_token_17",
        )
    ]
    return SimpleNamespace(
        app_home=app_home,
        settings=settings,
        app_config={},
        secrets_store=FakeSecretsStore({"redcap_api_token_17": "secret"}),
    )


def write_project_config(app_home: Path) -> Path:
    project_dir = app_home / "projects" / "17"
    project_dir.mkdir(parents=True, exist_ok=True)
    dictionary_path = project_dir / "dictionary.csv"
    headers = [
        "field_name",
        "form_name",
        "field_type",
        "field_label",
        "select_choices_or_calculations",
    ]
    rows = [
        {
            "field_name": "hasta_ad",
            "form_name": "hasta_bilgileri",
            "field_type": "text",
            "field_label": "Hasta adi",
            "select_choices_or_calculations": "",
        },
        {
            "field_name": "hasta_soyad",
            "form_name": "hasta_bilgileri",
            "field_type": "text",
            "field_label": "Hasta soyadi",
            "select_choices_or_calculations": "",
        },
    ]
    with dictionary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    config_path = project_dir / "project_config_17.json"
    config_path.write_text(
        json.dumps(
            {
                "project_name": "Demo",
                "project_id": "17",
                "dictionary_path": "dictionary.csv",
                "target_forms": ["hasta_bilgileri"],
                "target_fields": [],
                "form_labels": {"hasta_bilgileri": "Hasta Bilgileri"},
                "dictionary_legend": {
                    "field_name": "field_name",
                    "form_name": "form_name",
                    "field_type": "field_type",
                    "field_label": "field_label",
                    "choices": "select_choices_or_calculations",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return config_path


if __name__ == "__main__":
    unittest.main()
