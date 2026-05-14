"""
Central validation helpers for AppRun host-facing values.

Bundles are untrusted input.  Any value that becomes a path fragment, command
operand, desktop entry value, Debian package name, or systemd unit name should
pass through this module before it reaches the host.
"""

from __future__ import annotations

import re
from pathlib import Path


class ValidationError(ValueError):
    """Raised when bundle-controlled data is unsafe for a host operation."""


_APP_ID_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,126}[A-Za-z0-9])?$")
_DEBIAN_PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]{0,213}$")
_SYSTEMD_UNIT_RE = re.compile(r"^[A-Za-z0-9:_.@-]+\.(?:service|socket|target|timer|path|mount|device|slice|scope)$")
_CONTROL_RE = re.compile("[\x00-\x1f\x7f]")


def _reject_control(value: str, label: str) -> None:
    if _CONTROL_RE.search(value):
        raise ValidationError(f"{label} contains control characters")


def validate_app_id(value: str) -> str:
    """
    Validate the canonical AppRun bundle ID.

    IDs are intentionally path-fragment safe: no slashes, no empty path
    components, no leading dash, and no ``..`` component.  The accepted shape is
    reverse-DNS friendly but also supports older single-component IDs.
    """
    text = str(value).strip()
    _reject_control(text, "bundle id")
    if not _APP_ID_RE.fullmatch(text):
        raise ValidationError(f"unsafe bundle id: {value!r}")
    if any(part in ("", "..") for part in text.split(".")):
        raise ValidationError(f"unsafe bundle id component: {value!r}")
    if "/" in text or "\\" in text or text.startswith(("-", ".")):
        raise ValidationError(f"unsafe bundle id path fragment: {value!r}")
    return text


def sanitize_identifier(value: str, default: str = "unknown") -> str:
    """
    Convert local fallback identifiers into a valid, non-authoritative app ID.

    This is only for host-derived fallback values such as filenames.  Bundle
    supplied IDs should be rejected with :func:`validate_app_id`.
    """
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip())
    text = re.sub(r"[.]{2,}", ".", text).strip(".-")
    if not text:
        text = default
    if not re.match(r"^[A-Za-z0-9]", text):
        text = f"{default}-{text}"
    if not re.search(r"[A-Za-z0-9]$", text):
        text = f"{text}-{default}"
    return validate_app_id(text[:128])


def validate_debian_package_name(value: str) -> str:
    """Validate the package name subset accepted by apt/dpkg."""
    text = str(value).strip()
    _reject_control(text, "package name")
    if not _DEBIAN_PACKAGE_RE.fullmatch(text):
        raise ValidationError(f"unsafe Debian package name: {value!r}")
    return text


def validate_systemd_unit_name(value: str, *, suffix: str | None = None) -> str:
    """Validate a systemd unit operand before it is passed to systemctl."""
    text = str(value).strip()
    _reject_control(text, "systemd unit name")
    if "/" in text or "\\" in text or ".." in text or text.startswith("-"):
        raise ValidationError(f"unsafe systemd unit name: {value!r}")
    if not _SYSTEMD_UNIT_RE.fullmatch(text):
        raise ValidationError(f"unsafe systemd unit name: {value!r}")
    if suffix and not text.endswith(suffix):
        raise ValidationError(f"systemd unit must end with {suffix}: {value!r}")
    return text


def validate_service_file_path(value: str) -> str:
    """Validate a bundle service file path of the form ``services/name.service``."""
    text = str(value)
    _reject_control(text, "service path")
    path = Path(text)
    if path.is_absolute() or len(path.parts) != 2 or path.parts[0] != "services":
        raise ValidationError(f"unsafe service path: {value!r}")
    validate_systemd_unit_name(path.name, suffix=".service")
    return text


def validate_desktop_value(value: object, label: str = "desktop value") -> str:
    """
    Validate a scalar Desktop Entry value.

    Desktop entries are line-oriented.  Newlines and other control characters
    are rejected instead of normalized so a bundle cannot inject extra keys.
    """
    text = "" if value is None else str(value)
    _reject_control(text, label)
    return text.strip()


def validate_safe_relative_path(value: str, label: str = "relative path") -> str:
    """Require a relative path that cannot escape its intended root."""
    text = str(value)
    _reject_control(text, label)
    path = Path(text)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValidationError(f"unsafe {label}: {value!r}")
    return text
