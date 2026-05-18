import contextlib
import io
import unittest

from apprun_cli.parser import parse_args


class ParserTests(unittest.TestCase):
    def test_help_short_circuits_without_bundle_path(self):
        flags, bundle, extra = parse_args(["--help"])
        self.assertEqual(flags, {"help": True})
        self.assertIsNone(bundle)
        self.assertEqual(extra, [])

    def test_runtime_flags_and_extra_app_args_are_split(self):
        flags, bundle, extra = parse_args([
            "--portable=mount,box",
            "--inherit=full",
            "--info=name,version",
            "demo.apprunx",
            "--app-flag",
            "value",
        ])

        self.assertEqual(flags["portable"], ["mount", "box"])
        self.assertEqual(flags["inherit"], ["full"])
        self.assertEqual(flags["info"], ["name", "version"])
        self.assertEqual(bundle, "demo.apprunx")
        self.assertEqual(extra, ["--app-flag", "value"])

    def test_startup_argument_variants_support_lists_and_quoted_strings(self):
        flags, bundle, extra = parse_args([
            "--install-as-gui-startup",
            "--apprunargs=--portable,--inherit=venv",
            "--runargs-start=--name 'hello world'",
            "--runarg=--tail",
            "demo.apprunx",
        ])

        self.assertEqual(flags["install_as_gui_startup"], None)
        self.assertEqual(flags["gui_startup_apprun_args"], ["--portable", "--inherit=venv"])
        self.assertEqual(flags["gui_startup_run_args"], ["--name", "hello world", "--tail"])
        self.assertEqual(bundle, "demo.apprunx")
        self.assertEqual(extra, [])

    def test_extract_options_must_be_passed_together(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                parse_args(["--extract-file-from=AppRunMeta/id", "demo.apprunx"])
        self.assertEqual(ctx.exception.code, 2)

    def test_invalid_option_values_exit_with_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                parse_args(["--portable=mount,invalid", "demo.apprunx"])
        self.assertEqual(ctx.exception.code, 2)

    def test_unknown_options_exit_with_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                parse_args(["--unknown", "demo.apprunx"])
        self.assertEqual(ctx.exception.code, 2)

    def test_bundle_path_is_required_without_help(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                parse_args(["--id"])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
