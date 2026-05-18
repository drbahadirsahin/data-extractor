import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui.app import resolve_ui_mode
from gui.clinical_main_window import ClinicalImportPage, build_default_llm_settings


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

    def test_build_default_llm_settings_keeps_api_secret_indirect(self):
        runtime = SimpleNamespace(
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


if __name__ == "__main__":
    unittest.main()
