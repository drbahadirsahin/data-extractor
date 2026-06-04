import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from data_entry_store import DataEntryStore, RedcapDataValue
from gui.data_entry_page import (
    ClinicalDataEntryPage,
    apply_ai_fill_overrides,
    build_data_entry_ai_config,
    data_entry_store_path,
    merged_override_payload,
    repeat_context_options,
)
from data_entry_form_model import FormFieldModel, FormRenderModel, FormSectionModel
from project_config import ProjectConfig
from settings_store import AppSettings, RedcapProjectToken


def get_qapplication():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class FakeSecretsStore:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, key):
        return self.values.get(key)


class FakeIdentityRegistryClient:
    def __init__(self, config, api_token):
        self.config = config
        self.api_token = api_token

    def create_record_by_tc(self, tc_identity_no: str):
        return SimpleNamespace(record_id="9001", created=True, raw={})


class FakeRedcapClient:
    calls = []

    def __init__(self, api_url, api_token, timeout_seconds=60):
        self.api_url = api_url
        self.api_token = api_token
        self.timeout_seconds = timeout_seconds

    def import_records(self, records, *, overwrite_behavior="normal", return_content="ids", force_auto_number=False):
        self.calls.append(
            {
                "records": records,
                "overwrite_behavior": overwrite_behavior,
                "return_content": return_content,
                "force_auto_number": force_auto_number,
            }
        )
        return [str(record.get("record_id", "")) for record in records]


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

    def test_local_save_preserves_active_form_section(self) -> None:
        get_qapplication()
        with tempfile.TemporaryDirectory() as temp_dir:
            app_home = Path(temp_dir)
            config_path = write_project_config(app_home, include_laboratory=True)
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
                    ),
                    RedcapDataValue(
                        project_id="17",
                        event_id="",
                        record="1",
                        field_name="psa",
                        value="4.2",
                    ),
                ]
            )
            runtime = build_runtime(app_home, config_path)
            page = ClinicalDataEntryPage(runtime)
            page.record_list.setCurrentRow(0)

            page.form_widget.select_section(1)
            self.assertEqual(page.form_widget.current_section().form_name, "tan_laboratuvar_sonucu")
            page.form_widget.editor_widgets["psa"].setText("5.1")

            page.save_current_record()

            self.assertEqual(page.current_model.record, "1")
            self.assertEqual(page.form_widget.current_section().form_name, "tan_laboratuvar_sonucu")
            self.assertEqual(page.form_widget.collect_values()["psa"], "5.1")

    def test_save_and_send_imports_pending_changes(self) -> None:
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
                    )
                ]
            )
            runtime = build_runtime(app_home, config_path)
            page = ClinicalDataEntryPage(runtime)
            page.record_list.setCurrentRow(0)
            page.form_widget.editor_widgets["hasta_ad"].setText("EF")
            FakeRedcapClient.calls = []

            with patch("gui.data_entry_page.RedcapClient", FakeRedcapClient):
                page.save_current_record(send=True)

            self.assertEqual(len(FakeRedcapClient.calls), 1)
            self.assertEqual(FakeRedcapClient.calls[0]["records"], [{"record_id": "1", "hasta_ad": "EF"}])
            self.assertEqual(store.pending_changes("17"), [])

    def test_page_shows_project_context_and_dag_switcher(self) -> None:
        get_qapplication()
        with tempfile.TemporaryDirectory() as temp_dir:
            app_home = Path(temp_dir)
            config_path = write_project_config(app_home)
            runtime = build_runtime(app_home, config_path)
            runtime.settings.redcap.saved_project_tokens[0].username = "bahadir2"
            runtime.settings.redcap.saved_project_tokens[0].data_access_group = "Marmara"
            runtime.settings.redcap.saved_project_tokens[0].data_access_group_unique_name = "marmara"
            runtime.settings.redcap.saved_project_tokens[0].can_switch_data_access_group = True
            runtime.settings.redcap.saved_project_tokens[0].available_data_access_groups = [
                {
                    "data_access_group_id": "42",
                    "data_access_group": "Marmara",
                    "data_access_group_unique_name": "marmara",
                    "active": True,
                    "switchable": True,
                    "no_assignment": False,
                },
                {
                    "data_access_group_id": "43",
                    "data_access_group": "Pendik",
                    "data_access_group_unique_name": "pendik",
                    "active": False,
                    "switchable": True,
                    "no_assignment": False,
                },
            ]

            page = ClinicalDataEntryPage(runtime)

            self.assertIn("bahadir2", page.project_user_context.text())
            self.assertIn("Marmara", page.project_user_context.text())
            self.assertFalse(page.dag_combo.isHidden())
            self.assertEqual(page.dag_combo.count(), 2)

    def test_dynamic_sql_field_options_are_evaluated_from_local_redcap_data(self) -> None:
        get_qapplication()
        with tempfile.TemporaryDirectory() as temp_dir:
            app_home = Path(temp_dir)
            config_path = write_project_config(app_home, include_dynamic_sql=True)
            store = DataEntryStore(data_entry_store_path(app_home))
            store.initialize()
            store.upsert_remote_values(
                [
                    RedcapDataValue(
                        project_id="17",
                        event_id="",
                        record="1",
                        field_name="mr_tarihi",
                        value="2026-05-28",
                    ),
                    RedcapDataValue(
                        project_id="17",
                        event_id="",
                        record="2",
                        field_name="mr_tarihi",
                        value="2099-01-01",
                    ),
                ]
            )
            runtime = build_runtime(app_home, config_path)

            page = ClinicalDataEntryPage(runtime)
            page.record_list.setCurrentRow(0)
            combo = page.form_widget.editor_widgets["mr_secimi"]

            self.assertEqual(combo.count(), 2)
            self.assertEqual(combo.itemData(1), "2026-05-28")
            self.assertEqual(combo.itemText(1), "2026-05-28")
            self.assertNotIn("select", combo.itemText(1).lower())

    def test_new_record_creates_record_by_tc_then_queues_changes(self) -> None:
        get_qapplication()
        with tempfile.TemporaryDirectory() as temp_dir:
            app_home = Path(temp_dir)
            config_path = write_project_config(app_home)
            store = DataEntryStore(data_entry_store_path(app_home))
            store.initialize()
            runtime = build_runtime(app_home, config_path)
            page = ClinicalDataEntryPage(runtime)

            with patch("gui.data_entry_page.IdentityRegistryClient", FakeIdentityRegistryClient):
                page.open_new_record("19226637242")

            self.assertIsNotNone(page.current_model)
            self.assertEqual(page.current_model.record, "9001")
            page.form_widget.editor_widgets["hasta_ad"].setText("Yeni")
            page.save_current_record()

            pending = store.pending_changes("17")
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["record"], "9001")
            self.assertEqual(pending[0]["field_name"], "hasta_ad")
            self.assertEqual(pending[0]["new_value"], "Yeni")

    def test_new_record_switches_selected_dag_before_server_create(self) -> None:
        get_qapplication()
        with tempfile.TemporaryDirectory() as temp_dir:
            app_home = Path(temp_dir)
            config_path = write_project_config(app_home)
            runtime = build_runtime(app_home, config_path)
            project = runtime.settings.redcap.saved_project_tokens[0]
            project.data_access_group_id = "42"
            project.data_access_group = "Marmara"
            project.data_access_group_unique_name = "marmara"
            project.can_switch_data_access_group = True
            target_dag = {
                "data_access_group_id": "43",
                "data_access_group": "Pendik",
                "data_access_group_unique_name": "pendik",
                "active": False,
                "switchable": True,
                "no_assignment": False,
            }

            def change_dag(option):
                project.data_access_group_id = option["data_access_group_id"]
                project.data_access_group = option["data_access_group"]
                project.data_access_group_unique_name = option["data_access_group_unique_name"]

            page = ClinicalDataEntryPage(runtime, change_dag=change_dag)

            with patch("gui.data_entry_page.IdentityRegistryClient", FakeIdentityRegistryClient):
                page.open_new_record("19226637242", dag_option=target_dag)

            self.assertEqual(project.data_access_group_unique_name, "pendik")
            self.assertIsNotNone(page.current_model)
            self.assertEqual(page.current_model.record, "9001")

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

    def test_ai_fill_overrides_merge_temporary_form_and_field_rules(self) -> None:
        config = SimpleNamespace(
            form_overrides={"hasta_bilgileri": {"prompt_append": "Mevcut form kuralı"}},
            field_overrides={"hasta_ad": {"max_candidates": 2}},
        )

        apply_ai_fill_overrides(
            config,
            form_name="hasta_bilgileri",
            form_override={
                "prompt_append": "Sadece resmi rapordaki değeri kullan.",
                "cardinality": "single",
            },
            field_overrides={
                "hasta_ad": {
                    "prompt_append": "İlk iki harfi al.",
                    "post_processing": [["limit_output_length", 2]],
                }
            },
        )

        self.assertEqual(
            config.form_overrides["hasta_bilgileri"]["prompt_append"],
            "Sadece resmi rapordaki değeri kullan.",
        )
        self.assertEqual(config.form_overrides["hasta_bilgileri"]["cardinality"], "single")
        self.assertEqual(config.field_overrides["hasta_ad"]["max_candidates"], 2)
        self.assertEqual(config.field_overrides["hasta_ad"]["prompt_append"], "İlk iki harfi al.")
        self.assertEqual(config.field_overrides["hasta_ad"]["post_processing"], [["limit_output_length", 2]])

    def test_merged_override_payload_can_replace_and_clear_values(self) -> None:
        payload = merged_override_payload(
            {"prompt_append": "A", "max_candidates": 3, "selection_rule": "latest"},
            {"prompt_append": "B", "max_candidates": None},
        )

        self.assertEqual(payload["prompt_append"], "B")
        self.assertEqual(payload["selection_rule"], "latest")
        self.assertNotIn("max_candidates", payload)

    def test_build_data_entry_ai_config_uses_release_llm_and_scopes_fields(self) -> None:
        project_config = ProjectConfig(
            project_name="Demo",
            project_id="17",
            dictionary_path="dictionary.csv",
            llm={"provider": "ollama", "model": "local"},
            form_overrides={},
            field_overrides={},
        )
        bundle = SimpleNamespace(config=project_config)
        runtime = SimpleNamespace(
            app_config={
                "llm": {
                    "provider": "llm_gateway",
                    "base_url": "https://gateway.example",
                    "model": "qwen/qwen3.5-9b",
                },
                "release": {"profile": "user"},
            }
        )

        scoped = build_data_entry_ai_config(
            runtime=runtime,
            bundle=bundle,
            form_name="hasta_bilgileri",
            field_names=["hasta_ad"],
            form_override={"selection_rule": "latest"},
            field_overrides={"hasta_ad": {"max_candidates": 1}},
        )

        self.assertEqual(scoped.target_forms, ["hasta_bilgileri"])
        self.assertEqual(scoped.target_fields, ["hasta_ad"])
        self.assertEqual(scoped.llm["provider"], "llm_gateway")
        self.assertEqual(scoped.form_overrides["hasta_bilgileri"]["selection_rule"], "latest")
        self.assertEqual(scoped.field_overrides["hasta_ad"]["max_candidates"], 1)

    def test_repeat_context_options_include_repeating_events_and_forms(self) -> None:
        config = ProjectConfig(
            project_name="Demo",
            project_id="17",
            dictionary_path="dictionary.csv",
            form_labels={
                "hasta_bilgileri": "Hasta Bilgileri",
                "tan_laboratuvar_sonucu": "Tanı Laboratuvar Sonucu",
            },
            event_labels={
                "klasik_biyopsi_arm_1": "Klasik Biyopsi",
                "tbbi_bilgiler__tan_arm_1": "Tıbbi Bilgiler & Tanı",
            },
            form_event_map={
                "hasta_bilgileri": ["klasik_biyopsi_arm_1"],
                "tan_laboratuvar_sonucu": ["tbbi_bilgiler__tan_arm_1"],
            },
            repeating_events=["klasik_biyopsi_arm_1"],
            repeating_form_event_map={"tan_laboratuvar_sonucu": ["tbbi_bilgiler__tan_arm_1"]},
        )
        bundle = SimpleNamespace(
            config=config,
            grouped_fields={
                "hasta_bilgileri": [SimpleNamespace(field_name="hasta_ad")],
                "tan_laboratuvar_sonucu": [SimpleNamespace(field_name="psa")],
            },
        )
        model = FormRenderModel(
            project_id="17",
            record="1",
            title="Record 1",
            sections=[
                FormSectionModel(
                    form_name="hasta_bilgileri",
                    title="Hasta Bilgileri",
                    event_id="klasik_biyopsi_arm_1",
                    instance="1",
                    fields=[FormFieldModel("hasta_ad", "hasta_bilgileri", "Hasta Adı", "text")],
                ),
                FormSectionModel(
                    form_name="tan_laboratuvar_sonucu",
                    title="Tanı Laboratuvar Sonucu",
                    event_id="tbbi_bilgiler__tan_arm_1",
                    repeat_instrument="tan_laboratuvar_sonucu",
                    instance="2",
                    fields=[FormFieldModel("psa", "tan_laboratuvar_sonucu", "PSA", "text")],
                ),
            ],
        )

        labels = [option["label"] for option in repeat_context_options(model, bundle, "tr")]

        self.assertIn("Event: Klasik Biyopsi #2", labels)
        self.assertIn("Form: Tıbbi Bilgiler & Tanı / Tanı Laboratuvar Sonucu #3", labels)


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


def write_project_config(
    app_home: Path,
    *,
    include_laboratory: bool = False,
    include_dynamic_sql: bool = False,
) -> Path:
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
    form_labels = {"hasta_bilgileri": "Hasta Bilgileri"}
    target_forms = ["hasta_bilgileri"]
    if include_laboratory:
        rows.append(
            {
                "field_name": "psa",
                "form_name": "tan_laboratuvar_sonucu",
                "field_type": "text",
                "field_label": "PSA",
                "select_choices_or_calculations": "",
            }
        )
        form_labels["tan_laboratuvar_sonucu"] = "Tanı Laboratuvar Sonucu"
        target_forms.append("tan_laboratuvar_sonucu")
    if include_dynamic_sql:
        rows.extend(
            [
                {
                    "field_name": "mr_tarihi",
                    "form_name": "multiparametrik_mr",
                    "field_type": "text",
                    "field_label": "MR tarihi",
                    "select_choices_or_calculations": "",
                },
                {
                    "field_name": "mr_secimi",
                    "form_name": "multiparametrik_mr",
                    "field_type": "sql",
                    "field_label": "MR seçimi",
                    "select_choices_or_calculations": (
                        "select value from redcap_data "
                        "where project_id='17' and field_name='mr_tarihi' and record=[record-name]"
                    ),
                },
            ]
        )
        form_labels["multiparametrik_mr"] = "Multiparametrik MR"
        target_forms.append("multiparametrik_mr")
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
                "target_forms": target_forms,
                "target_fields": [],
                "form_labels": form_labels,
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
