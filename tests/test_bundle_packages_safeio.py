import json
import os
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apprun_safeio import ensure_directory_no_symlink, write_file_no_symlink
from apprun_validation import ValidationError
from libapprun.bundle import get_bundle_id, get_bundle_meta, get_meta_value, list_files
from libapprun.packages import (
    _parse_pkg_requirement,
    _version_satisfies,
    list_missing_base_packages,
)


class BundleMetadataTests(unittest.TestCase):
    def test_reads_id_and_meta_from_unpacked_bundle_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp)
            meta_dir = bundle / "AppRunMeta"
            meta_dir.mkdir()
            (meta_dir / "id").write_text("me.hysong.AppRun\n")
            (meta_dir / "meta.json").write_text(json.dumps({"name": "AppRun"}))

            self.assertEqual(get_bundle_id(str(bundle)), "me.hysong.AppRun")
            self.assertEqual(get_bundle_meta(str(bundle)), {"name": "AppRun"})
            self.assertEqual(get_meta_value(str(bundle), "name"), "AppRun")
            self.assertEqual(get_meta_value(str(bundle), "missing", "fallback"), "fallback")

    def test_invalid_or_non_object_meta_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp)
            meta_dir = bundle / "AppRunMeta"
            meta_dir.mkdir()
            (meta_dir / "meta.json").write_text("[1, 2, 3]")
            self.assertEqual(get_bundle_meta(str(bundle)), {})

            (meta_dir / "meta.json").write_text("{")
            self.assertEqual(get_bundle_meta(str(bundle)), {})

    def test_bundle_id_falls_back_to_sanitized_filename_when_no_id_exists(self):
        self.assertEqual(get_bundle_id("/tmp/My Cool App.apprunx"), "My-Cool-App_application")
        self.assertEqual(get_bundle_id("/tmp/unpacked bundle"), "unpacked-bundle_unknowntype")

    def test_invalid_directory_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            meta_dir = Path(tmp) / "AppRunMeta"
            meta_dir.mkdir()
            (meta_dir / "id").write_text("../escape")
            with self.assertRaises(ValidationError):
                get_bundle_id(tmp)

    def test_list_files_normalizes_unsquashfs_output(self):
        completed = type("Completed", (), {"stdout": "squashfs-root/main.py\nsquashfs-root/AppRunMeta/id\nother\n"})
        with patch("libapprun.bundle.subprocess.run", return_value=completed):
            self.assertEqual(list_files("demo.apprunx"), ["main.py", "AppRunMeta/id"])


class PackageRequirementTests(unittest.TestCase):
    def test_parse_package_requirement_supports_versions_and_plain_names(self):
        self.assertEqual(_parse_pkg_requirement("python3-venv>=3.11"), ("python3-venv", ">=", "3.11"))
        self.assertEqual(_parse_pkg_requirement("openjdk-25-jdk"), ("openjdk-25-jdk", None, None))
        with self.assertRaises(ValidationError):
            _parse_pkg_requirement("../evil")

    def test_version_comparison_uses_packaging_then_string_fallback(self):
        self.assertTrue(_version_satisfies("3.12.1", ">=", "3.11"))
        self.assertFalse(_version_satisfies("3.10", ">=", "3.11"))
        self.assertTrue(_version_satisfies("1:2.0", ">=", "1:1.9"))

    def test_list_missing_base_packages_preserves_requested_strings(self):
        with patch("libapprun.packages.get_meta_value", return_value=[
            "python3-venv>=3.11",
            "curl",
            "bad/name",
        ]), patch("libapprun.packages._get_installed_version", side_effect={
            "python3-venv": "3.10",
            "curl": "8.0",
        }.get), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(list_missing_base_packages("demo.apprunx"), ["python3-venv>=3.11"])


class SafeIoTests(unittest.TestCase):
    def test_write_file_no_symlink_creates_parent_and_file_with_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "nested" / "file.txt"
            write_file_no_symlink(dest, b"hello", mode=0o600)

            self.assertEqual(dest.read_bytes(), b"hello")
            self.assertEqual(dest.stat().st_mode & 0o777, 0o600)

    def test_write_file_no_symlink_rejects_final_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target.txt"
            link = root / "link.txt"
            target.write_text("original")
            os.symlink(target, link)

            with self.assertRaises(OSError):
                write_file_no_symlink(link, b"changed")
            self.assertEqual(target.read_text(), "original")

    def test_ensure_directory_no_symlink_rejects_symlink_component(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real"
            real.mkdir()
            link = root / "link"
            os.symlink(real, link)

            with self.assertRaises(OSError):
                ensure_directory_no_symlink(link / "child")


if __name__ == "__main__":
    unittest.main()
