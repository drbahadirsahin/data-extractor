import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui.app import resolve_ui_mode
from gui.clinical_main_window import (
    ClinicalImportPage,
    ClinicalRedcapPage,
    build_default_llm_settings,
    current_redcap_project_token,
    upsert_project_token,
)
from gui.workspace_page import fit_dialog_size_to_available_area
from redcap_client import RedcapProject
from secrets_store import SecretsStore
from settings_store import AppSettings, RedcapProjectToken, SettingsStore


def get_qapplication():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class GuiAppTests(unittest.TestCase):
    def test_resolve_ui_mode_defaults_to_clinical(self):
        self.assertEqual(resolve_ui_mode({}, ["app"]), "clinical")

    def test_resolve_ui_mode_supports_legacy_override(self):
        self.assertEqual(resolve_ui_mode({"ui": {"mode": "clinical"}}, ["app", "--legacy-ui"]), "legacy")
        with patch.dict("os.environ", {"LLM_EXTRACTOR_UI_MODE": "dev"}, clear=False):
            self.assertEqual(resolve_ui_mode({}, ["app"]), "legacy")

    def test_dialog_size_is_bounded_by_available_screen(self):
        width, height, min_width, min_height = fit_dialog_size_to_available_area(
            available_width=1147,
            available_height=697,
            preferred_width=1120,
            preferred_height=720,
            minimum_width=900,
            minimum_height=520,
        )

        self.assertEqual(width, 1075)
        self.assertEqual(height, 625)
        self.assertEqual(min_width, 900)
        self.assertEqual(min_height, 520)

    def test_build_default_llm_settings_keeps_api_secret_indirect(self):
        runtime = SimpleNamespace(
            app_config={},
            settings=SimpleNamespace(
                inference=SimpleNamespace(
                    selected_provider="openai_compatible",
                    openai_compatible_base_url="https://openrouter.ai/api/v1",
                    openai_compatible_model="model-x",
                    timeout_seconds=600,
                    api_key_secret_name="llm_api_key",
                    local_ollama_base_url="http://127.0.0.1:11434",
                    remote_ollama_base_url=None,
                )
            ),
            inference_recommendation=SimpleNamespace(mode="openai_compatible"),
        )

        settings = build_default_llm_settings(runtime)

        self.assertEqual(settings["provider"], "openai_compatible")
        self.assertEqual(settings["api_key_secret_name"], "llm_api_key")
        self.assertNotIn("api_key", settings)

    def test_build_default_llm_settings_uses_managed_gateway_without_direct_secret(self):
        runtime = SimpleNamespace(
            app_config={
                "llm": {
                    "provider": "llm_gateway",
                    "base_url": "https://gateway.example/v1",
                    "model": "qwen/qwen3.5-9b",
                    "gateway_client_token_secret_name": "llm_gateway_client_token",
                    "gateway_client_token": "do-not-copy",
                    "api_key": "do-not-copy",
                    "use_json_schema": True,
                }
            },
            settings=SimpleNamespace(inference=SimpleNamespace()),
            inference_recommendation=SimpleNamespace(mode="openai_compatible"),
        )

        settings = build_default_llm_settings(runtime)

        self.assertEqual(settings["provider"], "llm_gateway")
        self.assertEqual(settings["base_url"], "https://gateway.example/v1")
        self.assertEqual(settings["gateway_client_token_secret_name"], "llm_gateway_client_token")
        self.assertNotIn("gateway_client_token", settings)
        self.assertNotIn("api_key", settings)

    def test_upsert_project_token_replaces_same_project(self):
        tokens = [
            RedcapProjectToken(
                api_url="https://redcap.example/api/",
                project_id="42",
                project_name="Old",
                token_secret_name="old_secret",
            )
        ]

        upsert_project_token(
            tokens,
            RedcapProjectToken(
                api_url="https://redcap.example/api/",
                project_id="42",
                project_name="New",
                token_secret_name="new_secret",
                username="bahadir2",
            ),
        )

        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].project_name, "New")
        self.assertEqual(tokens[0].token_secret_name, "new_secret")
        self.assertEqual(tokens[0].username, "bahadir2")

    def test_current_redcap_project_token_uses_active_project(self):
        settings = SimpleNamespace(
            redcap=SimpleNamespace(
                selected_project_id="43",
                saved_project_tokens=[
                    RedcapProjectToken(
                        api_url="https://redcap.example/api/",
                        project_id="42",
                        project_name="A",
                        token_secret_name="a",
                    ),
                    RedcapProjectToken(
                        api_url="https://redcap.example/api/",
                        project_id="43",
                        project_name="B",
                        token_secret_name="b",
                        username="user-b",
                    ),
                ],
            )
        )

        self.assertEqual(current_redcap_project_token(settings).username, "user-b")

    def test_clinical_import_page_gates_document_steps(self):
        get_qapplication()
        state = {"patients": 0}
        runtime = SimpleNamespace(
            settings=SimpleNamespace(
                ui=SimpleNamespace(language="tr"),
                redcap=SimpleNamespace(selected_project_name="Demo"),
            )
        )
        page = ClinicalImportPage(
            runtime=runtime,
            add_patient_documents=lambda: True,
            remove_patient_at=lambda index: False,
            run_queue=lambda: None,
            import_excel=lambda on_success=None: True,
            configure_scope=lambda: None,
            manage_extra_fields=lambda: None,
            edit_rules=lambda: None,
            open_advanced=lambda: None,
            get_patient_count=lambda: state["patients"],
            get_patient_summaries=lambda: [f"patient {index}" for index in range(state["patients"])],
            get_scope_summary=lambda: "scope",
        )

        self.assertEqual(page.document_step, 0)
        self.assertFalse(page.document_next_button.isEnabled())

        state["patients"] = 1
        page.refresh()
        self.assertTrue(page.document_next_button.isEnabled())
        page.next_document_step()
        self.assertEqual(page.document_step, 1)
        page.next_document_step()
        self.assertEqual(page.document_step, 2)
        self.assertTrue(page.document_step_labels[0].isEnabled())
        page.document_step_labels[0].click()
        self.assertEqual(page.document_step, 0)

    def test_clinical_import_page_keeps_excel_step_on_failed_import(self):
        get_qapplication()
        state = {"import_ok": False}
        runtime = SimpleNamespace(
            settings=SimpleNamespace(
                ui=SimpleNamespace(language="tr"),
                redcap=SimpleNamespace(selected_project_name="Demo"),
            )
        )

        def import_excel(on_success=None):
            if state["import_ok"] and on_success is not None:
                on_success()
            return state["import_ok"]

        page = ClinicalImportPage(
            runtime=runtime,
            add_patient_documents=lambda: True,
            remove_patient_at=lambda index: False,
            run_queue=lambda: None,
            import_excel=import_excel,
            configure_scope=lambda: None,
            manage_extra_fields=lambda: None,
            edit_rules=lambda: None,
            open_advanced=lambda: None,
            get_patient_count=lambda: 0,
            get_patient_summaries=lambda: [],
            get_scope_summary=lambda: "scope",
        )

        page.set_flow("excel")
        self.assertEqual(page.excel_stack.count(), 2)
        page.set_excel_step(0)
        page.next_excel_step()
        self.assertEqual(page.excel_step, 0)

        state["import_ok"] = True
        page.next_excel_step()
        self.assertEqual(page.excel_step, 1)

    def test_clinical_redcap_validate_persists_project_and_locks_configured_url(self):
        get_qapplication()
        with patch("gui.clinical_main_window.ensure_project_config", return_value="/tmp/project_config.json"):
            import tempfile

            with tempfile.TemporaryDirectory() as temp_dir:
                settings_store = SettingsStore(temp_dir)
                settings = AppSettings()
                settings.redcap.api_url = "https://marmarauroloji.com/redcap/api/"
                runtime = SimpleNamespace(
                    app_home=temp_dir,
                    app_config={
                        "redcap": {
                            "api_url": "https://marmarauroloji.com/redcap/api/",
                            "allow_api_url_edit": False,
                        },
                        "llm": {
                            "provider": "llm_gateway",
                            "base_url": "https://gateway.example/v1",
                            "model": "qwen/qwen3.5-9b",
                        },
                    },
                    settings=settings,
                    settings_store=settings_store,
                    secrets_store=SecretsStore(temp_dir),
                    inference_recommendation=SimpleNamespace(mode="openai_compatible"),
                )
                saved = {"called": False}
                page = ClinicalRedcapPage(runtime=runtime, on_saved=lambda: saved.__setitem__("called", True))

                class FakeClient:
                    def __init__(self, api_url, api_token):
                        self.api_url = api_url
                        self.api_token = api_token

                    def get_project(self):
                        return RedcapProject(project_id="42", project_title="Demo Project")

                page.RedcapClient = FakeClient
                page.token_input.setText("secret-token")
                page.validate_token()

                loaded = settings_store.load()
                self.assertTrue(page.api_url_input.isReadOnly())
                self.assertTrue(saved["called"])
                self.assertEqual(loaded.redcap.selected_project_id, "42")
                self.assertEqual(loaded.redcap.selected_project_name, "Demo Project")
                self.assertEqual(len(loaded.redcap.saved_project_tokens), 1)
                self.assertEqual(page.saved_projects.findData("42") >= 0, True)
                self.assertEqual(runtime.secrets_store.get("redcap_api_token_42"), "secret-token")


if __name__ == "__main__":
    unittest.main()
