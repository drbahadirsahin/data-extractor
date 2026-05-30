import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workspace_flow import (
    build_scoped_project_config,
    default_search_roots,
    ensure_project_defaults_in_config,
    ensure_server_metadata_in_config,
    ensure_project_config,
    find_project_config_by_project_id,
    get_fields_for_forms,
    load_workspace_bundle,
    summarize_selection,
)


class WorkspaceFlowTests(unittest.TestCase):
    def test_load_workspace_bundle_and_scope_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dictionary_path = root / "dictionary.csv"
            config_path = root / "project_config.json"

            headers = [
                "Variable / Field Name",
                "Form Name",
                "Field Type",
                "Field Label",
                "Choices, Calculations, OR Slider Labels",
                "Field Note",
                "Text Validation Type OR Show Slider Number",
                "Text Validation Min",
                "Text Validation Max",
                "Field Annotation",
            ]
            rows = [
                {
                    "Variable / Field Name": "hasta_ad",
                    "Form Name": "hasta_bilgileri",
                    "Field Type": "text",
                    "Field Label": "Hasta Adi",
                    "Choices, Calculations, OR Slider Labels": "",
                    "Field Note": "",
                    "Text Validation Type OR Show Slider Number": "",
                    "Text Validation Min": "",
                    "Text Validation Max": "",
                    "Field Annotation": "",
                },
                {
                    "Variable / Field Name": "gizli_alan",
                    "Form Name": "hasta_bilgileri",
                    "Field Type": "text",
                    "Field Label": "Gizli Alan",
                    "Choices, Calculations, OR Slider Labels": "",
                    "Field Note": "",
                    "Text Validation Type OR Show Slider Number": "",
                    "Text Validation Min": "",
                    "Text Validation Max": "",
                    "Field Annotation": "@HIDDEN",
                },
                {
                    "Variable / Field Name": "lab_psa",
                    "Form Name": "laboratuvar",
                    "Field Type": "text",
                    "Field Label": "PSA",
                    "Choices, Calculations, OR Slider Labels": "",
                    "Field Note": "",
                    "Text Validation Type OR Show Slider Number": "",
                    "Text Validation Min": "",
                    "Text Validation Max": "",
                    "Field Annotation": "",
                },
                {
                    "Variable / Field Name": "vki",
                    "Form Name": "hasta_bilgileri",
                    "Field Type": "calc",
                    "Field Label": "VKİ",
                    "Choices, Calculations, OR Slider Labels": "round(([kilo]/(([boy]/100)^2)),1)",
                    "Field Note": "",
                    "Text Validation Type OR Show Slider Number": "",
                    "Text Validation Min": "",
                    "Text Validation Max": "",
                    "Field Annotation": "",
                },
            ]
            with dictionary_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows)

            config_payload = {
                "project_name": "Test Workspace",
                "project_id": "16",
                "dictionary_path": "dictionary.csv",
                "target_forms": [],
                "target_fields": ["hasta_ad", "lab_psa"],
                "llm": {},
                "dictionary_legend": {
                    "field_name": "Variable / Field Name",
                    "form_name": "Form Name",
                    "field_type": "Field Type",
                    "field_label": "Field Label",
                    "choices": "Choices, Calculations, OR Slider Labels",
                    "field_note": "Field Note",
                    "text_validation": "Text Validation Type OR Show Slider Number",
                    "text_validation_min": "Text Validation Min",
                    "text_validation_max": "Text Validation Max",
                    "field_annotation": "Field Annotation",
                },
                "prompting": {},
                "batch_size": 5,
                "append_fields": [
                    {
                        "Variable / Field Name": "tc_no",
                        "Form Name": "hasta_bilgileri",
                        "Field Type": "text",
                        "Field Label": "TC No",
                        "Choices, Calculations, OR Slider Labels": "",
                        "Field Note": "",
                        "Text Validation Type OR Show Slider Number": "",
                        "Text Validation Min": "",
                        "Text Validation Max": "",
                        "Field Annotation": "",
                    }
                ],
                "field_overrides": {
                    "hasta_ad": {
                        "post_processing": [["limit_output_length", 2]],
                        "max_candidates": 7,
                    }
                },
                "form_overrides": {},
                "repeating_forms": [],
            }
            config_path.write_text(json.dumps(config_payload), encoding="utf-8")

            bundle = load_workspace_bundle(config_path)
            self.assertEqual(bundle.form_names, ["hasta_bilgileri", "laboratuvar"])
            self.assertEqual(bundle.all_field_names, ["hasta_ad", "lab_psa"])
            self.assertEqual(bundle.config.dictionary_path, str(dictionary_path.resolve()))
            self.assertNotIn("tc_no", bundle.all_field_names)
            self.assertNotIn("gizli_alan", bundle.all_field_names)
            self.assertNotIn("vki", bundle.all_field_names)
            self.assertEqual(bundle.grouped_fields["hasta_bilgileri"][0].post_processing, [["limit_output_length", 2]])
            self.assertEqual(bundle.grouped_fields["hasta_bilgileri"][0].max_candidates, 7)

            data_entry_bundle = load_workspace_bundle(config_path, data_entry=True)
            self.assertIn("vki", data_entry_bundle.all_field_names)
            self.assertNotIn("gizli_alan", data_entry_bundle.all_field_names)

            fields = get_fields_for_forms(bundle, {"laboratuvar"})
            self.assertEqual([field.field_name for field in fields], ["lab_psa"])

            scoped = build_scoped_project_config(bundle, {"laboratuvar"}, {"lab_psa"})
            self.assertEqual(scoped.target_forms, ["laboratuvar"])
            self.assertEqual(scoped.target_fields, ["lab_psa"])

            summary = summarize_selection(bundle, {"laboratuvar"}, {"lab_psa"})
            self.assertEqual(summary, (1, 2, 1, 2))

    def test_ensure_project_config_uses_existing_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dictionary_path = root / "dictionary.csv"
            dictionary_path.write_text("Variable / Field Name,Form Name\n", encoding="utf-8")
            config_path = root / "project_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "project_name": "Existing",
                        "project_id": "77",
                        "dictionary_path": "dictionary.csv",
                        "target_forms": [],
                        "target_fields": [],
                        "llm": {},
                        "dictionary_legend": {},
                        "prompting": {},
                        "batch_size": 5,
                        "append_fields": [],
                        "field_overrides": {},
                        "form_overrides": {},
                        "repeating_forms": [],
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(find_project_config_by_project_id("77", root), config_path.resolve())

            with (
                patch("workspace_flow.RedcapClient.export_metadata_csv") as export_mock,
                patch("workspace_flow.RedcapClient.export_instruments", return_value={}),
                patch("workspace_flow.RedcapClient.export_repeating_forms", return_value=[]),
            ):
                resolved = ensure_project_config(
                    app_home=root / ".app",
                    project_id="77",
                    project_name="Existing",
                    api_url="https://redcap.example/api/",
                    api_token="secret",
                    search_roots=[root],
                )

            self.assertEqual(resolved, config_path.resolve())
            export_mock.assert_not_called()

    def test_ensure_project_config_skips_incompatible_existing_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            broken_dir = root / "broken"
            broken_dir.mkdir()
            (broken_dir / "dictionary.csv").write_text("wrong,header\n1,2\n", encoding="utf-8")
            broken_config = broken_dir / "project_config.json"
            broken_config.write_text(
                json.dumps(
                    {
                        "project_name": "Broken",
                        "project_id": "88",
                        "dictionary_path": "dictionary.csv",
                        "target_forms": [],
                        "target_fields": [],
                        "llm": {},
                        "dictionary_legend": {"field_name": "Variable / Field Name"},
                        "prompting": {},
                        "batch_size": 5,
                        "append_fields": [],
                        "field_overrides": {},
                        "form_overrides": {},
                        "repeating_forms": [],
                    }
                ),
                encoding="utf-8",
            )

            blank_path = root / "project_config_blank.json"
            blank_path.write_text(
                json.dumps(
                    {
                        "project_name": "",
                        "project_id": "",
                        "dictionary_path": "",
                        "target_forms": [],
                        "target_fields": [],
                        "llm": {},
                        "dictionary_legend": {"field_name": "Variable / Field Name"},
                        "prompting": {},
                        "batch_size": 5,
                        "append_fields": [{"Variable / Field Name": "demo"}],
                        "field_overrides": {"a": {"b": 1}},
                        "form_overrides": {"x": {"y": 2}},
                        "repeating_forms": [],
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("workspace_flow.RedcapClient.export_metadata_csv", return_value="field_name,form_name,field_type,field_label\nf1,form1,text,Label\n"),
                patch("workspace_flow.RedcapClient.export_instruments", return_value={}),
                patch("workspace_flow.RedcapClient.export_repeating_forms", return_value=[]),
            ):
                original_cwd = Path.cwd()
                try:
                    os.chdir(root)
                    resolved = ensure_project_config(
                        app_home=root / ".app",
                        project_id="88",
                        project_name="Recovered",
                        api_url="https://redcap.example/api/",
                        api_token="secret",
                        search_roots=[root],
                    )
                finally:
                    os.chdir(original_cwd)

            self.assertNotEqual(resolved, broken_config.resolve())
            payload = json.loads(resolved.read_text(encoding="utf-8"))
            self.assertEqual(payload["project_name"], "Recovered")

    def test_ensure_project_config_creates_blank_and_dictionary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app_home = root / ".app"
            app_home.mkdir()
            blank_path = root / "project_config_blank.json"
            blank_path.write_text(
                json.dumps(
                    {
                        "project_name": "",
                        "project_id": "",
                        "dictionary_path": "",
                        "target_forms": [],
                        "target_fields": [],
                        "llm": {},
                        "dictionary_legend": {"field_name": "Variable / Field Name"},
                        "prompting": {},
                        "batch_size": 5,
                        "append_fields": [],
                        "field_overrides": {},
                        "form_overrides": {},
                        "repeating_forms": [],
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("workspace_flow.RedcapClient.export_metadata_csv", return_value="a,b\n1,2\n"),
                patch("workspace_flow.RedcapClient.export_instruments", return_value={"form_a": "Form A"}),
                patch("workspace_flow.RedcapClient.export_repeating_forms", return_value=["form_a"]),
            ):
                original_cwd = Path.cwd()
                try:
                    os.chdir(root)
                    config_path = ensure_project_config(
                        app_home=app_home,
                        project_id="99",
                        project_name="New Project",
                        api_url="https://redcap.example/api/",
                        api_token="secret",
                        default_llm_settings={
                            "provider": "openai_compatible",
                            "base_url": "https://example.com",
                            "model": "model-x",
                        },
                        search_roots=[root],
                    )
                finally:
                    os.chdir(original_cwd)

            payload = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["project_id"], "99")
            self.assertEqual(payload["project_name"], "New Project")
            self.assertEqual(payload["dictionary_path"], "dictionary.csv")
            self.assertEqual(config_path.name, "project_config_99.json")
            self.assertEqual(payload["append_fields"], [])
            self.assertEqual(payload["form_labels"], {"form_a": "Form A"})
            self.assertEqual(payload["repeating_forms"], ["form_a"])
            self.assertEqual(
                payload["dictionary_legend"]["field_name"],
                "field_name",
            )
            self.assertEqual(payload["llm"]["provider"], "openai_compatible")
            self.assertEqual(payload["llm"]["model"], "model-x")
            self.assertTrue((config_path.parent / "dictionary.csv").exists())

    def test_ensure_project_config_applies_developer_project_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app_home = root / ".app"
            app_home.mkdir()

            with (
                patch("workspace_flow.RedcapClient.export_metadata_csv", return_value="field_name,form_name,field_type,field_label\nhasta_ad,hasta_bilgileri,text,Hasta Adı\n"),
                patch("workspace_flow.RedcapClient.export_instruments", return_value={}),
                patch("workspace_flow.RedcapClient.export_repeating_forms", return_value=[]),
            ):
                config_path = ensure_project_config(
                    app_home=app_home,
                    project_id="17",
                    project_name="Defaults",
                    api_url="https://redcap.example/api/",
                    api_token="secret",
                    default_llm_settings={
                        "provider": "llm_gateway",
                        "base_url": "https://gateway.example/v1",
                        "model": "qwen/qwen3.5-9b",
                        "timeout_seconds": 600,
                    },
                    project_defaults={
                        "projects": {
                            "17": {
                                "field_overrides": {
                                    "hasta_ad": {
                                        "post_processing": [["limit_output_length", 2]],
                                        "max_candidates": 3,
                                    }
                                }
                            }
                        }
                    },
                    search_roots=[root / "missing"],
                )

            payload = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["llm"]["timeout_seconds"], 600)
            self.assertEqual(
                payload["field_overrides"]["hasta_ad"]["post_processing"],
                [["limit_output_length", 2]],
            )
            self.assertEqual(payload["field_overrides"]["hasta_ad"]["max_candidates"], 3)

    def test_ensure_project_defaults_updates_existing_managed_llm_without_clobbering_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "project_config_17.json"
            config_path.write_text(
                json.dumps(
                    {
                        "project_name": "Existing",
                        "project_id": "17",
                        "dictionary_path": "dictionary.csv",
                        "target_forms": [],
                        "target_fields": [],
                        "llm": {"provider": "llm_gateway", "timeout_seconds": 120},
                        "dictionary_legend": {},
                        "prompting": {},
                        "batch_size": 5,
                        "append_fields": [],
                        "field_overrides": {
                            "hasta_ad": {"prompt_append": "Mevcut kural korunur."}
                        },
                        "form_overrides": {},
                        "repeating_forms": [],
                    }
                ),
                encoding="utf-8",
            )

            ensure_project_defaults_in_config(
                config_path,
                project_id="17",
                default_llm_settings={
                    "provider": "llm_gateway",
                    "base_url": "https://gateway.example/v1",
                    "model": "qwen/qwen3.5-9b",
                    "timeout_seconds": 600,
                },
                project_defaults={
                    "projects": {
                        "17": {
                            "field_overrides": {
                                "hasta_ad": {
                                    "post_processing": [["limit_output_length", 2]],
                                    "max_candidates": 3,
                                }
                            }
                        }
                    }
                },
            )

            payload = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["llm"]["timeout_seconds"], 600)
            self.assertEqual(payload["field_overrides"]["hasta_ad"]["prompt_append"], "Mevcut kural korunur.")
            self.assertEqual(
                payload["field_overrides"]["hasta_ad"]["post_processing"],
                [["limit_output_length", 2]],
            )

    def test_ensure_server_metadata_in_config_updates_form_labels_and_repeating_forms(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dictionary_path = root / "dictionary.csv"
            dictionary_path.write_text(
                "field_name,form_name,field_type,field_label\nhasta_ad,demographics,text,Hasta Adı\n",
                encoding="utf-8",
            )
            config_path = root / "project_config_1.json"
            config_path.write_text(
                json.dumps(
                    {
                        "project_name": "Demo",
                        "project_id": "1",
                        "dictionary_path": "dictionary.csv",
                        "form_labels": {"demographics": "demographics"},
                        "repeating_forms": [],
                        "target_forms": [],
                        "target_fields": [],
                        "llm": {},
                        "dictionary_legend": {
                            "field_name": "field_name",
                            "form_name": "form_name",
                            "field_type": "field_type",
                            "field_label": "field_label",
                        },
                        "prompting": {},
                        "batch_size": 5,
                        "append_fields": [],
                        "field_overrides": {},
                        "form_overrides": {},
                        "repeating_forms": [],
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("workspace_flow.RedcapClient.export_instruments", return_value={"demographics": "Demografi"}),
                patch("workspace_flow.RedcapClient.export_repeating_forms", return_value=["demographics"]),
            ):
                ensure_server_metadata_in_config(
                    config_path,
                    api_url="https://redcap.example/api/",
                    api_token="secret",
                )

            payload = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["form_labels"]["demographics"], "Demografi")
            self.assertEqual(payload["repeating_forms"], ["demographics"])

    def test_default_search_roots_do_not_scan_cwd_in_packaged_app(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app_home = root / ".llm_extractor_data"
            projects = app_home / "projects"
            projects.mkdir(parents=True)
            (root / "app_config.json").write_text("{}", encoding="utf-8")

            original_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch("workspace_flow.is_packaged_app", return_value=True):
                    roots = default_search_roots(app_home)
            finally:
                os.chdir(original_cwd)

            self.assertEqual(roots, [projects.resolve()])

    def test_default_search_roots_allow_project_cwd_for_dev(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app_home = root / ".llm_extractor_data"
            projects = app_home / "projects"
            projects.mkdir(parents=True)
            (root / "app_config.json").write_text("{}", encoding="utf-8")

            original_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch("workspace_flow.is_packaged_app", return_value=False):
                    roots = default_search_roots(app_home)
            finally:
                os.chdir(original_cwd)

            self.assertEqual(roots, [projects.resolve(), root.resolve()])


if __name__ == "__main__":
    unittest.main()
