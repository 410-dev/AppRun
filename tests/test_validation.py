import unittest

from apprun_validation import (
    ValidationError,
    sanitize_identifier,
    validate_app_id,
    validate_debian_package_name,
    validate_safe_relative_path,
    validate_service_file_path,
    validate_systemd_unit_name,
)


class ValidationTests(unittest.TestCase):
    def test_validate_app_id_accepts_path_safe_ids(self):
        self.assertEqual(validate_app_id("me.hysong.AppRun-3_2"), "me.hysong.AppRun-3_2")
        self.assertEqual(validate_app_id("SingleComponent"), "SingleComponent")

    def test_validate_app_id_rejects_path_escape_and_control_values(self):
        for value in ("../escape", ".hidden", "bad..component", "bad/name", "-flag", "bad\nid"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_app_id(value)

    def test_sanitize_identifier_turns_host_names_into_valid_fallbacks(self):
        self.assertEqual(sanitize_identifier(" My App!.apprunx "), "My-App-.apprunx")
        self.assertTrue(sanitize_identifier("..").startswith("unknown"))

    def test_package_unit_and_relative_path_validators_reject_unsafe_input(self):
        self.assertEqual(validate_debian_package_name("python3-venv"), "python3-venv")
        self.assertEqual(validate_systemd_unit_name("app@example.service"), "app@example.service")
        self.assertEqual(validate_service_file_path("services/my-app.service"), "services/my-app.service")
        self.assertEqual(validate_safe_relative_path("assets/icon.png"), "assets/icon.png")

        invalid_values = [
            (validate_debian_package_name, "Python3"),
            (validate_systemd_unit_name, "../evil.service"),
            (validate_service_file_path, "other/my-app.service"),
            (validate_safe_relative_path, "../escape"),
        ]
        for validator, value in invalid_values:
            with self.subTest(validator=validator.__name__, value=value):
                with self.assertRaises(ValidationError):
                    validator(value)


if __name__ == "__main__":
    unittest.main()
