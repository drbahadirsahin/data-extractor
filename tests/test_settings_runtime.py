import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from runtime_context import bootstrap_runtime
from secrets_store import SecretsStore
from settings_store import (
    AppSettings,
    PORTABLE_DIRNAME,
    RedcapProjectToken,
    SettingsStore,
    fallback_app_home,
    resolve_app_home,
)
from system_profile import GPUInfo, SystemProfile, recommend_inference_mode


class SettingsAndRuntimeTests(unittest.TestCase):
    def test_settings_store_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SettingsStore(temp_dir)
            settings = AppSettings()
            settings.first_run_completed = True
            settings.inference.mode = "remote_ollama"
            settings.inference.remote_ollama_base_url = "https://example.com"
            settings.redcap.selected_project_id = "42"
            settings.redcap.selected_project_name = "Proje 42"
            settings.redcap.selected_project_token_secret_name = "redcap_api_token_42"
            settings.redcap.saved_project_tokens = [
                RedcapProjectToken(
                    api_url="https://redcap.example/api/",
                    project_id="42",
                    project_name="Proje 42",
                    token_secret_name="redcap_api_token_42",
                    username="bahadir2",
                    data_access_group_id="42",
                    data_access_group="Marmara",
                    data_access_group_unique_name="marmara",
                    can_switch_data_access_group=True,
                    available_data_access_groups=[
                        {
                            "data_access_group_id": "42",
                            "data_access_group": "Marmara",
                            "data_access_group_unique_name": "marmara",
                            "active": True,
                            "switchable": True,
                            "no_assignment": False,
                        }
                    ],
                )
            ]
            settings.ui.language = "en"

            store.save(settings)
            loaded = store.load()

            self.assertTrue(loaded.first_run_completed)
            self.assertEqual(loaded.inference.mode, "remote_ollama")
            self.assertEqual(loaded.inference.remote_ollama_base_url, "https://example.com")
            self.assertEqual(loaded.redcap.selected_project_id, "42")
            self.assertEqual(loaded.redcap.selected_project_name, "Proje 42")
            self.assertEqual(loaded.redcap.selected_project_token_secret_name, "redcap_api_token_42")
            self.assertEqual(len(loaded.redcap.saved_project_tokens), 1)
            self.assertEqual(loaded.redcap.saved_project_tokens[0].username, "bahadir2")
            self.assertEqual(loaded.redcap.saved_project_tokens[0].data_access_group_id, "42")
            self.assertEqual(loaded.redcap.saved_project_tokens[0].data_access_group, "Marmara")
            self.assertEqual(loaded.redcap.saved_project_tokens[0].data_access_group_unique_name, "marmara")
            self.assertTrue(loaded.redcap.saved_project_tokens[0].can_switch_data_access_group)
            self.assertEqual(
                loaded.redcap.saved_project_tokens[0].available_data_access_groups[0]["data_access_group"],
                "Marmara",
            )
            self.assertEqual(loaded.ui.language, "en")

    def test_secrets_store_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SecretsStore(temp_dir)
            store.set("openrouter_api_key", "secret-value")
            self.assertTrue(store.has("openrouter_api_key"))
            self.assertEqual(store.get("openrouter_api_key"), "secret-value")

            store.delete("openrouter_api_key")
            self.assertFalse(store.has("openrouter_api_key"))

    def test_recommend_inference_mode_prefers_api_without_gpu(self) -> None:
        profile = SystemProfile(
            os_name="Linux",
            os_version="test",
            machine="x86_64",
            python_version="3.12",
            cpu_count=8,
            total_memory_gb=8.0,
            available_memory_gb=4.0,
            gpus=[],
        )

        recommendation = recommend_inference_mode(profile)

        self.assertEqual(recommendation.mode, "openai_compatible")
        self.assertEqual(recommendation.confidence, "high")

    def test_recommend_inference_mode_prefers_local_for_strong_gpu(self) -> None:
        profile = SystemProfile(
            os_name="Linux",
            os_version="test",
            machine="x86_64",
            python_version="3.12",
            cpu_count=16,
            total_memory_gb=32.0,
            available_memory_gb=24.0,
            gpus=[GPUInfo(vendor="NVIDIA", name="RTX", memory_gb=12.0)],
        )

        recommendation = recommend_inference_mode(profile)

        self.assertEqual(recommendation.mode, "local_ollama")
        self.assertEqual(recommendation.confidence, "high")

    def test_bootstrap_runtime_applies_recommendation_for_auto_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
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
            with patch("runtime_context.collect_system_profile", return_value=fake_profile):
                context = bootstrap_runtime(temp_dir)

            self.assertEqual(context.inference_recommendation.mode, "openai_compatible")
            self.assertEqual(context.settings.inference.selected_provider, "llm_gateway")
            self.assertEqual(
                context.settings.inference.openai_compatible_base_url,
                "https://llm-extractor-gateway.drbahadirsahin.workers.dev/v1",
            )
            self.assertTrue((Path(temp_dir) / "settings.json").exists())

    def test_resolve_app_home_defaults_to_workspace_local_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            try:
                os.chdir(temp_dir)
                self.assertEqual(
                    resolve_app_home(),
                    (Path(temp_dir) / PORTABLE_DIRNAME).resolve(),
                )
            finally:
                os.chdir(original_cwd)

    def test_frozen_app_without_portable_marker_uses_fallback_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("settings_store.sys.frozen", True, create=True):
                with patch("settings_store.frozen_app_roots", return_value=[Path(temp_dir) / "LLMExtractor.app"]):
                    with patch("settings_store.Path.cwd", return_value=Path(temp_dir)):
                        self.assertEqual(
                            resolve_app_home(),
                            fallback_app_home(),
                        )

    def test_fallback_app_home_is_user_owned_location(self) -> None:
        self.assertTrue(str(fallback_app_home()).startswith(str(Path.home())))


if __name__ == "__main__":
    unittest.main()
