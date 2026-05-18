"""Debian package requirement helpers used by AppRun metadata."""

from __future__ import annotations

import re
import subprocess
import sys

try:
    from packaging.version import InvalidVersion, Version
except ModuleNotFoundError:  # pragma: no cover - exercised only on minimal dev hosts
    InvalidVersion = ValueError
    Version = None

from apprun_i18n import tr
from apprun_validation import ValidationError, validate_debian_package_name

from .bundle import get_meta_value


def _parse_pkg_requirement(req: str) -> tuple[str, str | None, str | None]:
    """
    Parse a small Debian package requirement expression.

    Examples:
    - ``python3-venv>=3.11`` -> ``("python3-venv", ">=", "3.11")``
    - ``openjdk-25-jdk`` -> ``("openjdk-25-jdk", None, None)``
    """
    match = re.match(r"^([A-Za-z0-9+\-.]+?)\s*(>=|<=|==|>|<)\s*(.+)$", req)
    if match:
        return validate_debian_package_name(match.group(1)), match.group(2), match.group(3)
    return validate_debian_package_name(req.strip()), None, None


def _get_installed_version(pkg_name: str) -> str | None:
    """Return the installed Debian package version, or None when absent."""
    result = subprocess.run(
        ["dpkg-query", "-W", "-f=${Status} ${Version}", pkg_name],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    line = result.stdout.strip()
    if "install ok installed" not in line:
        return None
    parts = line.split()
    return parts[-1] if parts else None


def _version_satisfies(installed: str, operator: str, required: str) -> bool:
    """Compare versions, falling back to string comparison for Debian formats."""
    try:
        if Version is None:
            raise InvalidVersion("packaging is unavailable")
        installed_version = Version(installed)
        required_version = Version(required)
        ops = {
            ">=": installed_version >= required_version,
            "<=": installed_version <= required_version,
            "==": installed_version == required_version,
            ">": installed_version > required_version,
            "<": installed_version < required_version,
        }
        return ops.get(operator, False)
    except InvalidVersion:
        ops_str = {
            ">=": installed >= required,
            "<=": installed <= required,
            "==": installed == required,
            ">": installed > required,
            "<": installed < required,
        }
        return ops_str.get(operator, False)


def list_missing_base_packages(path: str) -> list[str]:
    """
    Return unmet ``apt-requirements`` metadata entries.

    Return values preserve the original metadata strings so callers can display
    exactly what the bundle requested.
    """
    requirements: list[str] = get_meta_value(path, "apt-requirements", [])
    if not requirements:
        return []

    missing = []
    for req in requirements:
        try:
            pkg_name, operator, req_ver = _parse_pkg_requirement(req)
        except ValidationError:
            print(tr("warning.meta_value_ignored", key="apt-requirements", item=req), file=sys.stderr)
            continue

        installed_ver = _get_installed_version(pkg_name)
        if installed_ver is None:
            missing.append(req)
            continue
        if operator is not None and req_ver is not None and not _version_satisfies(installed_ver, operator, req_ver):
            missing.append(req)

    return missing
