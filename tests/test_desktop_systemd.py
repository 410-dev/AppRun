import unittest
from pathlib import Path

from apprun_desktop import (
    build_desktop_entry,
    build_desktop_from_meta,
    desktop_exec_quote_arg,
    format_desktop_exec,
    parse_bundled_desktop,
)
from apprun_systemd import build_generated_service_unit, format_exec_start, parse_unit_list
from apprun_validation import ValidationError


class DesktopEntryTests(unittest.TestCase):
    def test_exec_arguments_are_quoted_without_shell_concatenation(self):
        formatted = format_desktop_exec([
            "/usr/bin/apprun3",
            Path("/tmp/My App.apprunx"),
            "--literal=%f",
            'say "hi"',
        ])

        self.assertEqual(
            formatted,
            '/usr/bin/apprun3 "/tmp/My App.apprunx" "--literal=%%f" "say \\"hi\\""',
        )
        self.assertEqual(desktop_exec_quote_arg("simple"), "simple")

    def test_bundled_desktop_parser_allowlists_safe_first_values(self):
        parsed = parse_bundled_desktop(
            b"""
[Desktop Entry]
Name=Real App
Name=Ignored Duplicate
Exec=evil --command
Icon=evil
Keywords=alpha;beta;

[Other]
Comment=Ignored group
"""
        )

        self.assertEqual(parsed, {"Name": "Real App", "Keywords": "alpha;beta;"})

    def test_bundled_desktop_parser_rejects_line_injection(self):
        with self.assertRaises(ValidationError):
            parse_bundled_desktop(b"[Desktop Entry]\nName=bad\x01value\n")

    def test_build_desktop_entry_overrides_sensitive_fields(self):
        content = build_desktop_entry(
            app_id="me.hysong.AppRun",
            name="AppRun",
            comment="Launcher",
            exec_args=["/usr/bin/apprun3", "/tmp/App.apprunx"],
            icon="me.hysong.AppRun",
            terminal="yes",
            extra={"GenericName": "Runner", "Exec": "ignored", "Icon": "ignored"},
        )

        self.assertIn("Type=Application\n", content)
        self.assertIn("Name=AppRun\n", content)
        self.assertIn("GenericName=Runner\n", content)
        self.assertIn("Exec=/usr/bin/apprun3 /tmp/App.apprunx\n", content)
        self.assertIn("Icon=me.hysong.AppRun\n", content)
        self.assertIn("Terminal=true\n", content)
        self.assertIn("StartupWMClass=me.hysong.AppRun\n", content)
        self.assertNotIn("Exec=ignored", content)

    def test_build_desktop_from_meta_requires_name(self):
        self.assertIsNone(
            build_desktop_from_meta(
                app_id="me.hysong.AppRun",
                meta={},
                exec_args=["apprun3", "App.apprunx"],
                icon="me.hysong.AppRun",
            )
        )


class SystemdUnitTests(unittest.TestCase):
    def test_exec_start_arguments_are_quoted_safely(self):
        self.assertEqual(
            format_exec_start(["/usr/bin/apprun3", "/tmp/My App.apprunx", "100%"]),
            '/usr/bin/apprun3 "/tmp/My App.apprunx" "100%%"',
        )

    def test_parse_unit_list_validates_each_unit(self):
        self.assertEqual(
            parse_unit_list("network-online.target+dbus.service"),
            ["network-online.target", "dbus.service"],
        )
        with self.assertRaises(ValidationError):
            parse_unit_list("../escape.service")

    def test_build_generated_service_unit_serializes_expected_sections(self):
        content = build_generated_service_unit(
            description="AppRun service",
            service_type="oneshot",
            exec_args=["/usr/bin/apprun3", "/tmp/My App.apprunx"],
            after_units=["network-online.target"],
            before_units=["graphical.target"],
            user="appuser",
            wanted_by="multi-user.target",
        ).decode("utf-8")

        self.assertIn("[Unit]\n", content)
        self.assertIn("Description=AppRun service\n", content)
        self.assertIn("After=network-online.target\n", content)
        self.assertIn("[Service]\nType=oneshot\n", content)
        self.assertIn('ExecStart=/usr/bin/apprun3 "/tmp/My App.apprunx"\n', content)
        self.assertIn("User=appuser\n", content)
        self.assertIn("RemainAfterExit=yes\n", content)
        self.assertIn("[Install]\nWantedBy=multi-user.target\n", content)

    def test_build_generated_service_unit_rejects_unknown_type(self):
        with self.assertRaises(ValueError):
            build_generated_service_unit(
                description="bad",
                service_type="unknown",
                exec_args=["/bin/true"],
            )


if __name__ == "__main__":
    unittest.main()
