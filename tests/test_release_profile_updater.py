import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from release_profile import is_user_profile, show_advanced_ui, show_model_settings
from settings_store import PORTABLE_DIRNAME, PORTABLE_MARKER, resolve_app_home
from updater import (
    UpdateError,
    build_posix_apply_update_script,
    is_macos_app_translocated,
    macos_needs_portable_repair,
    macos_portable_app_bundle,
    normalize_macos_portable_root,
    platform_update_payload,
    remove_macos_quarantine,
    repair_macos_portable_and_relaunch,
    validate_self_update_target,
    version_is_newer,
)


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

    def test_macos_app_translocation_detection(self):
        translocated = Path(
            "/private/var/folders/x/y/T/AppTranslocation/ABCDEF/d/LLMExtractor.app/Contents/MacOS/LLMExtractor"
        )
        normal = Path("/Applications/LLMExtractor.app/Contents/MacOS/LLMExtractor")

        with patch("updater.sys.platform", "darwin"):
            self.assertTrue(is_macos_app_translocated(translocated))
            self.assertFalse(is_macos_app_translocated(normal))

        with patch("updater.sys.platform", "linux"):
            self.assertFalse(is_macos_app_translocated(translocated))

    def test_validate_self_update_target_blocks_translocated_macos_app(self):
        translocated = Path(
            "/private/var/folders/x/y/T/AppTranslocation/ABCDEF/d/LLMExtractor.app/Contents/MacOS/LLMExtractor"
        )

        with patch("updater.sys.platform", "darwin"), patch(
            "updater.current_executable", return_value=translocated
        ):
            with self.assertRaisesRegex(UpdateError, "App Translocation"):
                validate_self_update_target()

    def test_validate_self_update_target_requires_macos_portable_root_marker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app_root = Path(temp_dir) / "LLMExtractor.app"
            executable = app_root / "Contents" / "MacOS" / "LLMExtractor"
            executable.parent.mkdir(parents=True)
            executable.write_text("", encoding="utf-8")

            with patch("updater.sys.platform", "darwin"), patch(
                "updater.current_executable", return_value=executable
            ):
                with self.assertRaisesRegex(UpdateError, "üst klasörüyle birlikte"):
                    validate_self_update_target()

            (Path(temp_dir) / ".llm_extractor_portable").write_text("portable\n", encoding="utf-8")
            with patch("updater.sys.platform", "darwin"), patch(
                "updater.current_executable", return_value=executable
            ):
                validate_self_update_target()

    def test_macos_portable_root_accepts_root_or_app_bundle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "LLMExtractor-0.1.0-early.9-macos-arm64"
            bundle = root / "LLMExtractor.app"
            bundle.mkdir(parents=True)
            (root / ".llm_extractor_portable").write_text("portable\n", encoding="utf-8")

            self.assertEqual(normalize_macos_portable_root(root), root.resolve())
            self.assertEqual(normalize_macos_portable_root(bundle), root.resolve())
            self.assertEqual(macos_portable_app_bundle(root), bundle.resolve())

    def test_macos_portable_root_rejects_invalid_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(UpdateError, "geçerli bir LLMExtractor"):
                normalize_macos_portable_root(Path(temp_dir))

    def test_macos_needs_portable_repair_requires_frozen_translocated_app(self):
        translocated = Path(
            "/private/var/folders/x/y/T/AppTranslocation/ABCDEF/d/LLMExtractor.app/Contents/MacOS/LLMExtractor"
        )
        with patch("updater.sys.platform", "darwin"), patch(
            "updater.current_executable", return_value=translocated
        ), patch("updater.is_frozen_app", return_value=True):
            self.assertTrue(macos_needs_portable_repair())

        with patch("updater.sys.platform", "darwin"), patch(
            "updater.current_executable", return_value=translocated
        ), patch("updater.is_frozen_app", return_value=False):
            self.assertFalse(macos_needs_portable_repair())

    def test_remove_macos_quarantine_runs_xattr_on_portable_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "LLMExtractor-0.1.0-early.9-macos-arm64"
            (root / "LLMExtractor.app").mkdir(parents=True)
            (root / ".llm_extractor_portable").write_text("portable\n", encoding="utf-8")

            with patch("updater.subprocess.run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = ""
                run.return_value.stderr = ""
                remove_macos_quarantine(root)

            run.assert_called_once()
            self.assertEqual(
                run.call_args.args[0],
                ["/usr/bin/xattr", "-dr", "com.apple.quarantine", str(root.resolve())],
            )

    def test_repair_macos_portable_relaunches_selected_app_bundle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "LLMExtractor-0.1.0-early.9-macos-arm64"
            app_bundle = root / "LLMExtractor.app"
            app_bundle.mkdir(parents=True)
            (root / ".llm_extractor_portable").write_text("portable\n", encoding="utf-8")

            with patch("updater.subprocess.run") as run, patch("updater.subprocess.Popen") as popen:
                run.return_value.returncode = 0
                run.return_value.stdout = ""
                run.return_value.stderr = ""
                self.assertEqual(repair_macos_portable_and_relaunch(root), app_bundle.resolve())

            popen.assert_called_once_with(["/usr/bin/open", "-n", str(app_bundle.resolve())], close_fds=True)

    def test_posix_apply_update_script_writes_debug_log(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "update.zip"
            app_root = Path(temp_dir) / "LLMExtractor-0.1.0-early.8-macos-arm64"
            executable = app_root / "LLMExtractor.app" / "Contents" / "MacOS" / "LLMExtractor"

            script = build_posix_apply_update_script(
                archive_path=archive,
                app_root=app_root,
                executable=executable,
                parent_pid=123,
            )

        self.assertIn("apply_update.log", script)
        self.assertIn('exec >> "$LOG" 2>&1', script)
        self.assertIn("APP_ROOT=", script)
        self.assertIn('open "$APP_BUNDLE"', script)

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
