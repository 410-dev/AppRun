"""
Systemd unit serialization helpers for AppRun generated services.

The functions in this module reject line-oriented injection and keep unit names
as validated systemctl operands.
"""

from __future__ import annotations

from pathlib import Path

from apprun_validation import validate_desktop_value, validate_systemd_unit_name


VALID_SERVICE_TYPES = ("simple", "oneshot", "forking", "notify", "idle")


def systemd_quote_arg(value: str | Path) -> str:
    """Quote one ExecStart argv item using systemd-compatible double quotes."""
    text = validate_desktop_value(str(value), "systemd ExecStart argument")
    if text and not any(ch.isspace() or ch in '\\"%' for ch in text):
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return f'"{escaped}"'


def format_exec_start(args: list[str | Path]) -> str:
    """Format argv-style ExecStart content without invoking a shell."""
    return " ".join(systemd_quote_arg(arg) for arg in args)


def parse_unit_list(value: str) -> list[str]:
    """Parse ``foo.target+bar.service`` dependency specs into validated units."""
    if not value.strip():
        return []
    return [validate_systemd_unit_name(item.strip()) for item in value.split("+") if item.strip()]


def build_generated_service_unit(
    *,
    description: object,
    service_type: str,
    exec_args: list[str | Path],
    after_units: list[str] | None = None,
    before_units: list[str] | None = None,
    user: str | None = None,
    wanted_by: str = "multi-user.target",
) -> bytes:
    """Serialize a generated AppRun service unit."""
    if service_type not in VALID_SERVICE_TYPES:
        raise ValueError(f"unsupported service type: {service_type!r}")

    safe_after = [validate_systemd_unit_name(unit) for unit in (after_units or [])]
    safe_before = [validate_systemd_unit_name(unit) for unit in (before_units or [])]
    safe_wanted_by = validate_systemd_unit_name(wanted_by)

    unit_lines = [
        "[Unit]",
        f"Description={validate_desktop_value(description, 'systemd Description')}",
    ]
    if safe_after:
        unit_lines.append(f"After={' '.join(safe_after)}")
    if safe_before:
        unit_lines.append(f"Before={' '.join(safe_before)}")

    service_lines = [
        "",
        "[Service]",
        f"Type={service_type}",
        "Environment=PYTHONUNBUFFERED=1",
        f"ExecStart={format_exec_start(exec_args)}",
    ]
    if user:
        service_lines.append(f"User={validate_desktop_value(user, 'systemd User')}")
    if service_type == "oneshot":
        service_lines.append("RemainAfterExit=yes")

    install_lines = ["", "[Install]", f"WantedBy={safe_wanted_by}"]
    return ("\n".join(unit_lines + service_lines + install_lines) + "\n").encode("utf-8")

