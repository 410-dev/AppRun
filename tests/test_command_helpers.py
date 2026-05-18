import contextlib
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apprun_cli import command


class CommandHelperTests(unittest.TestCase):
    def test_meta_option_list_accepts_strings_and_lists(self):
        self.assertEqual(command._meta_option_list({"EnforcePortable": "mount"}, "EnforcePortable", {"mount"}), ["mount"])
        self.assertEqual(
            command._meta_option_list({"EnforcePortable": ["mount", "BOX"]}, "EnforcePortable", {"mount", "box"}),
            ["mount", "box"],
        )
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(command._meta_option_list({"EnforcePortable": 3}, "EnforcePortable", {"mount"}), [])
            self.assertEqual(command._meta_option_list({"EnforcePortable": ["bad"]}, "EnforcePortable", {"mount"}), [])

    def test_normalize_inherit_modes_expands_full(self):
        self.assertEqual(command._normalize_inherit_modes(["full"]), {"venv", "data"})
        self.assertEqual(command._normalize_inherit_modes(["venv"]), {"venv"})

    def test_resolve_runtime_paths_combines_flags_and_metadata(self):
        with patch("apprun_cli.command.libapprun.get_bundle_id", return_value="me.hysong.AppRun"), \
             patch("apprun_cli.command.libapprun.get_bundle_meta", return_value={
                 "EnforcePortable": ["mount"],
                 "EnforceInherit": ["data"],
             }), \
             patch("apprun_cli.command.libapprun.get_portable_mount_path", return_value=Path("/portable/mount")), \
             patch("apprun_cli.command.libapprun.get_portable_box_path", return_value=Path("/portable/box")):
            app_id, mount_path, box_path, portable, inherit = command._resolve_runtime_paths("demo.apprunx", {})

        self.assertEqual(app_id, "me.hysong.AppRun")
        self.assertEqual(mount_path, Path("/portable/mount"))
        self.assertEqual(box_path, Path("/portable/box"))
        self.assertEqual(portable, {"mount", "box"})
        self.assertEqual(inherit, {"data"})

    def test_pkg_names_only_strips_version_constraints(self):
        self.assertEqual(
            command._pkg_names_only(["python3-venv>=3.11", "curl"]),
            ["python3-venv", "curl"],
        )

    def test_build_cmd_selects_entry_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp)
            box = bundle / "box"
            box.mkdir()

            with patch("apprun_cli.command.libapprun.get_bundle_meta", return_value={}):
                (bundle / "main.py").write_text("print('hi')")
                cmd = command._build_cmd(str(bundle), "me.hysong.AppRun", {}, box)
                self.assertEqual(cmd[1], str(bundle / "main.py"))
                self.assertTrue(Path(cmd[0]).is_symlink())

                shutil.rmtree(command._tmp_symlink_dir)
                command._tmp_symlink_dir = None
                (bundle / "main.py").unlink()

            (bundle / "main.sh").write_text("echo hi")
            cmd = command._build_cmd(str(bundle), "me.hysong.AppRun", {}, box)
            self.assertEqual(cmd[1], str(bundle / "main.sh"))

            if command._tmp_symlink_dir:
                shutil.rmtree(command._tmp_symlink_dir)
                command._tmp_symlink_dir = None

    def test_wrap_root_terminal_and_screen_are_predictable(self):
        self.assertEqual(command._wrap_root(["cmd"], {}), ["cmd"])
        self.assertEqual(command._wrap_root(["cmd"], {"enforce_root_launch": True}), ["sudo", "cmd"])
        self.assertEqual(
            command._wrap_root(["cmd"], {"enforce_root_launch": True, "keep_environment": True}),
            ["sudo", "-E", "cmd"],
        )

        with patch("apprun_cli.command.libapprun.can_use_dbus_and_gui", return_value=False), \
             patch("sys.stderr"):
            self.assertEqual(command._wrap_terminal(["cmd"], {"launch_in_terminal": True}), ["cmd"])

        with patch("apprun_cli.command.shutil.which", return_value=None), \
             patch("apprun_cli.command.libapprun.show_gui_alert") as alert:
            self.assertEqual(command._wrap_screen(["cmd"], {"launch_in_screen": "recommended"}, "me.hysong.AppRun"), ["cmd"])
            alert.assert_called_once()

    def test_setup_pythonpath_uses_dictionary_output(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PYTHONPATH": "existing"}):
            bundle = Path(tmp)
            meta = bundle / "AppRunMeta"
            meta.mkdir()
            (meta / "libs").write_text("$APPDIR/libs")
            completed = type("Completed", (), {"returncode": 0, "stdout": "/bundle/libs\n"})

            with patch("apprun_cli.command.subprocess.run", return_value=completed):
                command._setup_pythonpath(str(bundle))

            self.assertEqual(os.environ["PYTHONPATH"], "/bundle/libs:existing")


if __name__ == "__main__":
    unittest.main()
