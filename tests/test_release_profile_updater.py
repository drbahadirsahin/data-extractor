import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from release_profile import is_user_profile, show_advanced_ui, show_model_settings
from settings_store import PORTABLE_DIRNAME, PORTABLE_MARKER, resolve_app_home
from updater import platform_update_payload, version_is_newer


class ReleaseProfileUpdaterTests(unittest.TestCase):
    def test_user_profile_hides_advanced_and_model_settings(self):
        config = {
            "release": {
                "profile": "user",
                "features": {
                    "show_advanced_ui": False,
                    "show_model_settings": False,
                },
            }
        }

        self.assertTrue(is_user_profile(config))
        self.assertFalse(show_advanced_ui(config))
        self.assertFalse(show_model_settings(config))

    def test_dev_override_shows_advanced_and_model_settings(self):
        config = {"release": {"profile": "user"}}

        with patch.dict("os.environ", {"LLM_EXTRACTOR_DEV_MODE": "1"}, clear=False):
            self.assertFalse(is_user_profile(config))
            self.assertTrue(show_advanced_ui(config))
            self.assertTrue(show_model_settings(config))

    def test_version_comparison_handles_early_release_suffix(self):
        self.assertTrue(version_is_newer("0.1.1", "0.1.0-early.1"))
        self.assertFalse(version_is_newer("0.1.0-early.1", "0.1.0-early.1"))

    def test_platform_payload_uses_specific_platform_first(self):
        manifest = {
            "platforms": {
                "macos": {"url": "generic"},
                "macos-arm64": {"url": "specific"},
            }
        }
        with patch("updater.platform.system", return_value="Darwin"), patch(
            "updater.platform.machine", return_value="arm64"
        ):
            self.assertEqual(platform_update_payload(manifest)["url"], "specific")

    def test_frozen_app_home_defaults_next_to_executable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "PortableApp"
            root.mkdir()
            (root / PORTABLE_MARKER).write_text("portable\n", encoding="utf-8")
            exe = root / "LLMExtractor.exe"
            exe.write_text("", encoding="utf-8")
            with patch("settings_store.sys.executable", str(exe)), patch(
                "settings_store.sys.frozen", True, create=True
            ):
                self.assertEqual(resolve_app_home(), (root / PORTABLE_DIRNAME).resolve())


if __name__ == "__main__":
    unittest.main()
