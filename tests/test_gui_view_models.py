import tempfile
import unittest
from unittest.mock import patch

from gui.view_models import (
    build_recommendation_text,
    build_system_summary,
    get_initial_page_index,
    provider_label_for_key,
)
from runtime_context import bootstrap_runtime
from system_profile import GPUInfo, SystemProfile


class GuiViewModelTests(unittest.TestCase):
    def test_provider_label_for_key(self) -> None:
        self.assertEqual(provider_label_for_key("local_ollama"), "Yerel Ollama")
        self.assertEqual(provider_label_for_key("missing"), "Secilmedi")
        self.assertEqual(provider_label_for_key("local_ollama", "en"), "Local Ollama")

    def test_runtime_summary_and_recommendation_text(self) -> None:
        fake_profile = SystemProfile(
            os_name="Linux",
            os_version="test",
            machine="x86_64",
            python_version="3.12",
            cpu_count=12,
            total_memory_gb=32.0,
            available_memory_gb=20.0,
            gpus=[GPUInfo(vendor="NVIDIA", name="RTX 4090", memory_gb=24.0)],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("runtime_context.collect_system_profile", return_value=fake_profile):
                context = bootstrap_runtime(temp_dir)

            summary = build_system_summary(context)
            recommendation = build_recommendation_text(context)

        self.assertTrue(any("RTX 4090" in line for line in summary))
        self.assertIn("Onerilen mod: Yerel Ollama", recommendation)

    def test_initial_page_index_skips_onboarding_after_first_run(self) -> None:
        fake_profile = SystemProfile(
            os_name="Linux",
            os_version="test",
            machine="x86_64",
            python_version="3.12",
            cpu_count=8,
            total_memory_gb=8.0,
            available_memory_gb=4.0,
            gpus=[],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("runtime_context.collect_system_profile", return_value=fake_profile):
                context = bootstrap_runtime(temp_dir)
            context.settings.first_run_completed = True
            context.settings.redcap.api_url = "https://redcap.example/api/"
            context.secrets_store.set(context.settings.redcap.api_token_secret_name, "token")

            self.assertEqual(get_initial_page_index(context), 1)


if __name__ == "__main__":
    unittest.main()
