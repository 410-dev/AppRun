"""
Safe Desktop Entry serialization for AppRun generated launchers.

The serializer keeps bundle-provided desktop data on an allowlist and always
overrides host-sensitive keys such as Exec, Icon, Type, and StartupWMClass.
"""

from __future__ import annotations

import re
from pathlib import Path

from apprun_validation import ValidationError, validate_app_id, validate_desktop_value


PASSTHROUGH_KEYS = {
    "Name",
    "GenericName",
    "Comment",
    "Categories",
    "Keywords",
    "MimeType",
    "StartupNotify",
}


def desktop_exec_quote_arg(value: str | Path) -> str:
    """Quote one argv item for a Desktop Entry Exec line."""
    text = str(value)
    validate_desktop_value(text, "desktop Exec argument")
    if text and not re.search(r'[\s"\\%]', text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'


def format_desktop_exec(args: list[str | Path]) -> str:
    """Format argv-style arguments for a Desktop Entry Exec line."""
    return " ".join(desktop_exec_quote_arg(arg) for arg in args)


def bool_desktop_value(value: object, default: bool = False) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return "true"
        if lowered in {"0", "false", "no", "off"}:
            return "false"
    return "true" if default else "false"


def parse_bundled_desktop(desktop_data: bytes) -> dict[str, str]:
    """
    Parse a bundled desktop file into an allowlisted key map.

    Unknown groups, duplicate keys, malformed lines, and host-sensitive keys are
    ignored.  Values with control characters are rejected by the shared validator.
    """
    text = desktop_data.decode("utf-8", errors="replace")
    values: dict[str, str] = {}
    in_desktop_entry = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_desktop_entry = line == "[Desktop Entry]"
            continue
        if not in_desktop_entry or "=" not in line:
            continue

        key, value = line.split("=", 1)
        if key not in PASSTHROUGH_KEYS or key in values:
            continue
        values[key] = validate_desktop_value(value, f"desktop {key}")

    return values


def build_desktop_entry(
    *,
    app_id: str,
    name: str,
    exec_args: list[str | Path],
    icon: str,
    comment: str = "",
    terminal: object = False,
    categories: str = "Application;",
    extra: dict[str, str] | None = None,
) -> str:
    """
    Build a Desktop Entry from validated scalar fields and argv-style Exec args.

    The output is non-executable data; callers should write it with mode 0644.
    """
    app_id = validate_app_id(app_id)
    extra = dict(extra or {})

    safe_name = validate_desktop_value(name or app_id, "desktop Name") or app_id
    safe_comment = validate_desktop_value(comment, "desktop Comment")
    safe_icon = validate_desktop_value(icon, "desktop Icon")
    safe_categories = validate_desktop_value(categories or "Application;", "desktop Categories")

    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={safe_name}",
    ]
    if safe_comment:
        lines.append(f"Comment={safe_comment}")

    for key in ("GenericName", "Keywords", "MimeType", "StartupNotify"):
        if key in extra and extra[key]:
            lines.append(f"{key}={validate_desktop_value(extra[key], f'desktop {key}')}")

    lines.extend([
        f"Exec={format_desktop_exec(exec_args)}",
        f"Icon={safe_icon}",
        f"Terminal={bool_desktop_value(terminal)}",
        f"Categories={safe_categories}",
        f"StartupWMClass={app_id}",
    ])
    return "\n".join(lines) + "\n"


def build_desktop_from_meta(
    *,
    app_id: str,
    meta: dict,
    exec_args: list[str | Path],
    icon: str,
    extra: dict[str, str] | None = None,
) -> str | None:
    """Build a desktop entry from AppRun metadata, returning None without a name."""
    name = validate_desktop_value(meta.get("name", ""), "desktop Name")
    if not name:
        return None
    return build_desktop_entry(
        app_id=app_id,
        name=name,
        comment=meta.get("description", ""),
        terminal=meta.get("launch_in_terminal", False),
        categories="Application;",
        exec_args=exec_args,
        icon=icon,
        extra=extra,
    )

