import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from release_profile import is_user_profile, show_advanced_ui, show_model_settings
from scripts.generate_update_manifest import add_generic_platform_aliases
from settings_store import PORTABLE_DIRNAME, PORTABLE_MARKER, resolve_app_home
from updater import (
    UpdateError,
    build_posix_apply_update_script,
    build_windows_apply_update_script,
    build_windows_update_launcher_script,
    cache_busted_url,
    is_macos_app_translocated,
    macos_needs_portable_repair,
    macos_portable_app_bundle,
    normalize_macos_portable_root,
    packaged_platform_key,
    platform_keys,
    platform_update_payload,
    remove_macos_quarantine,
    repair_macos_portable_and_relaunch,
    validate_self_update_target,
    version_is_newer,
    windows_update_launcher_command,
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
        self.assertTrue(version_is_newer("0.1.0-early.10", "0.1.0-early.9"))
        self.assertTrue(version_is_newer("0.1.0", "0.1.0-early.10"))
        self.assertFalse(version_is_newer("0.1.0-early.9", "0.1.0-early.10"))
        self.assertTrue(version_is_newer("0.1.1-early.2", "0.1.1-early.1"))
        self.assertTrue(version_is_newer("0.1.1-early.3", "0.1.1-early.2"))
        self.assertTrue(version_is_newer("0.1.1-early.4", "0.1.1-early.3"))
        self.assertTrue(version_is_newer("0.1.1-early.5", "0.1.1-early.4"))
        self.assertTrue(version_is_newer("0.1.1-early.6", "0.1.1-early.5"))
        self.assertTrue(version_is_newer("0.1.1-early.10", "0.1.1-early.9"))
        self.assertTrue(version_is_newer("0.1.1-early.11", "0.1.1-early.10"))
        self.assertTrue(version_is_newer("0.1.1-early.12", "0.1.1-early.11"))
        self.assertTrue(version_is_newer("0.1.1-early.13", "0.1.1-early.12"))
        self.assertTrue(version_is_newer("0.1.1-early.14", "0.1.1-early.13"))
        self.assertTrue(version_is_newer("0.1.1-early.15", "0.1.1-early.14"))
        self.assertTrue(version_is_newer("0.1.1-early.16", "0.1.1-early.15"))
        self.assertTrue(version_is_newer("0.1.1-early.17", "0.1.1-early.16"))
        self.assertTrue(version_is_newer("0.1.1-early.18", "0.1.1-early.17"))
        self.assertTrue(version_is_newer("0.1.1-early.19", "0.1.1-early.18"))
        self.assertTrue(version_is_newer("0.1.1-early.20", "0.1.1-early.19"))
        self.assertTrue(version_is_newer("0.1.1-early.21", "0.1.1-early.20"))
        self.assertTrue(version_is_newer("0.1.1-early.22", "0.1.1-early.21"))
        self.assertTrue(version_is_newer("0.1.1-early.23", "0.1.1-early.22"))
        self.assertTrue(version_is_newer("0.1.1-early.24", "0.1.1-early.23"))

    def test_cache_busted_url_preserves_existing_query(self):
        with patch("updater.time.time", return_value=1234.567):
            result = cache_busted_url("https://example.test/update_manifest.json?channel=early")

        self.assertIn("channel=early", result)
        self.assertIn("_llm_extractor_cache_bust=1234567", result)

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

    def test_platform_keys_prefer_packaged_windows_x64_on_arm_windows(self):
        package_root = Path("C:/fld/LLMExtractor-0.1.1-early.5-windows-x64")
        with patch("updater.current_app_root", return_value=package_root), patch(
            "updater.platform.system", return_value="Windows"
        ), patch("updater.platform.machine", return_value="ARM64"):
            self.assertEqual(platform_keys()[:3], ["windows-x64", "windows-arm64", "windows"])
            self.assertEqual(packaged_platform_key(), "windows-x64")

    def test_platform_payload_falls_back_to_windows_x64_on_arm_windows(self):
        manifest = {"platforms": {"windows-x64": {"url": "x64"}}}
        with patch("updater.current_app_root", return_value=Path("C:/plain")), patch(
            "updater.platform.system", return_value="Windows"
        ), patch("updater.platform.machine", return_value="ARM64"):
            self.assertEqual(platform_update_payload(manifest)["url"], "x64")

    def test_manifest_adds_generic_windows_alias_for_single_windows_package(self):
        platforms = {"windows-x64": {"url": "x64", "sha256": "abc"}}
        add_generic_platform_aliases(platforms)

        self.assertEqual(platforms["windows"]["url"], "x64")

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
        self.assertIn('open -n "$APP_BUNDLE"', script)
        self.assertIn("nohup \"$NEW_EXECUTABLE\"", script)

    def test_windows_apply_update_replaces_app_root_after_parent_exits(self):
        script = build_windows_apply_update_script(
            archive_path=Path("C:/Temp/update.zip"),
            app_root=Path("C:/fld/LLMExtractor-0.1.1-early.5-windows-x64"),
            executable=Path("C:/fld/LLMExtractor-0.1.1-early.5-windows-x64/LLMExtractor.exe"),
            parent_pid=123,
        )

        self.assertIn("$PersistentLog = Join-Path $OldDataDir \"apply_update.log\"", script)
        self.assertIn("Copy current app root to backup", script)
        self.assertIn("Remove current app root", script)
        self.assertIn("function Copy-DirectoryChildren", script)
        self.assertIn("Copy-DirectoryChildren $AppRoot $BackupRoot", script)
        self.assertNotIn("Move-Item -LiteralPath $AppRoot -Destination $BackupRoot", script)
        self.assertIn("Move-Item -LiteralPath $SourceRoot -Destination $AppRoot", script)
        self.assertIn("Copy-Item -LiteralPath $PreservedDataDir -Destination $NewDataDir", script)
        self.assertIn("Start-Process -FilePath $NewExecutable -WorkingDirectory $AppRoot", script)
        self.assertIn("Restored backup after failed update", script)

    def test_windows_update_launcher_writes_temp_diagnostics_then_copies_back(self):
        script = build_windows_update_launcher_script(
            script_path=Path("C:/Temp/apply_update.ps1"),
            app_root=Path("C:/fld/LLMExtractor-0.1.1-early.14-windows-x64"),
        )

        self.assertIn('set "LOG=%~dp0apply_update_launcher.log"', script)
        self.assertIn("apply_update_launcher.log", script)
        self.assertIn('copy /Y "%LOG%" "%DATA_DIR%\\apply_update_launcher.log"', script)
        self.assertNotIn('set "LOG=%DATA_DIR%\\apply_update_launcher.log"', script)
        self.assertIn("WindowsPowerShell\\v1.0\\powershell.exe", script)
        self.assertIn("-ExecutionPolicy Bypass -File", script)
        self.assertIn("PowerShell exited with", script)

    def test_windows_update_launcher_command_runs_cmd_file_directly(self):
        launcher = Path("C:/Users/Test User/AppData/Local/Temp/llm/apply_update.cmd")

        command = windows_update_launcher_command(launcher)

        self.assertEqual(command, ["cmd.exe", "/d", "/c", str(launcher)])
        self.assertNotIn("start", [part.lower() for part in command])

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
