"""Argument parsing for the public AppRun command."""

from __future__ import annotations

import shlex
import sys

from apprun_i18n import tr

from .constants import INHERIT_TARGETS, PORTABLE_TARGETS


def _parse_option_list(value: str, valid: set[str], option_name: str) -> list[str]:
    items = [item.strip().lower() for item in value.split(",") if item.strip()]
    invalid = [item for item in items if item not in valid]
    if invalid:
        print(
            tr("error.invalid_option_value", option=option_name, values=", ".join(invalid)),
            file=sys.stderr,
        )
        sys.exit(2)
    return items


def _parse_startup_args(raw: str, option_name: str) -> list[str]:
    """
    Parse compact startup argument strings.

    Whitespace uses shell-like quoting.  If no whitespace is present and commas
    are used, commas act as separators for convenience:
    ``--runargs-start=--a=x,--b=y,positional``.
    """
    value = raw.strip()
    if not value:
        return []

    if "," in value and not any(ch.isspace() for ch in value):
        return [part for part in value.split(",") if part]

    try:
        return shlex.split(value)
    except ValueError as exc:
        print(tr("error.option_parse_failed", option=option_name, error=exc), file=sys.stderr)
        sys.exit(2)


def parse_args(argv: list[str]):
    flags = {}
    remaining = argv[:]
    i = 0

    while i < len(remaining):
        arg = remaining[i]
        if not arg.startswith("--") and arg != "-h":
            break

        if arg in ("--help", "-h"):
            flags["help"] = True
        elif arg == "--id":
            flags["id"] = True
        elif arg == "--is-format3":
            flags["is_format3"] = True
        elif arg == "--info":
            flags["info"] = []
        elif arg.startswith("--info="):
            flags["info"] = arg[len("--info="):].split(",")
        elif arg == "--box-path":
            flags["box_path"] = True
        elif arg == "--portable":
            flags["portable"] = ["mount", "box"]
        elif arg.startswith("--portable="):
            flags["portable"] = _parse_option_list(arg[len("--portable="):], PORTABLE_TARGETS, "--portable")
        elif arg == "--inherit":
            flags["inherit"] = ["full"]
        elif arg.startswith("--inherit="):
            flags["inherit"] = _parse_option_list(arg[len("--inherit="):], INHERIT_TARGETS, "--inherit")
        elif arg == "--prepare":
            flags["prepare"] = True
        elif arg.startswith("--extract-file-from="):
            flags["extract_file_from"] = arg[len("--extract-file-from="):]
        elif arg.startswith("--extract-file-to="):
            flags["extract_file_to"] = arg[len("--extract-file-to="):]
        elif arg == "--register":
            flags["register"] = True
        elif arg == "--install-services":
            flags["install_services"] = True
        elif arg == "--start":
            flags["service_install_and_enable"] = True
            flags["service_install_and_start"] = True
        elif arg == "--enable":
            flags["service_install_and_enable"] = True
        elif arg.startswith("--install-as-service="):
            flags["install_as_service"] = arg[len("--install-as-service="):]
        elif arg == "--install-as-global-user-service":
            flags["install_as_global_user_service"] = None
        elif arg.startswith("--install-as-global-user-service="):
            flags["install_as_global_user_service"] = arg[len("--install-as-global-user-service="):]
        elif arg == "--uninstall-as-global-user-service":
            flags["uninstall_as_global_user_service"] = True
        elif arg == "--install-as-gui-startup":
            flags["install_as_gui_startup"] = None
        elif arg.startswith("--install-as-gui-startup="):
            flags["install_as_gui_startup"] = arg[len("--install-as-gui-startup="):]
        elif arg == "--uninstall-as-gui-startup":
            flags["uninstall_as_gui_startup"] = None
        elif arg.startswith("--uninstall-as-gui-startup="):
            flags["uninstall_as_gui_startup"] = arg[len("--uninstall-as-gui-startup="):]
        elif arg.startswith("--apprunargs="):
            flags.setdefault("gui_startup_apprun_args", []).extend(
                _parse_startup_args(arg[len("--apprunargs="):], "--apprunargs")
            )
        elif arg.startswith("--apprunarg="):
            flags.setdefault("gui_startup_apprun_args", []).append(arg[len("--apprunarg="):])
        elif arg.startswith("--runargs-start="):
            flags.setdefault("gui_startup_run_args", []).extend(
                _parse_startup_args(arg[len("--runargs-start="):], "--runargs-start")
            )
        elif arg.startswith("--runarg="):
            flags.setdefault("gui_startup_run_args", []).append(arg[len("--runarg="):])
        elif arg.startswith("--user=") and (
            "install_as_service" in flags
            or "uninstall_as_service" in flags
            or "install_as_gui_startup" in flags
            or "uninstall_as_gui_startup" in flags
        ):
            flags["service_install_user"] = arg[len("--user="):]
        elif arg == "--uninstall-services":
            flags["uninstall_services"] = True
        elif arg == "--uninstall-as-service":
            flags["uninstall_as_service"] = True
        else:
            print(tr("error.unknown_option", option=arg), file=sys.stderr)
            sys.exit(2)

        remaining.pop(i)

    if "help" in flags:
        return flags, None, []

    has_from = "extract_file_from" in flags
    has_to = "extract_file_to" in flags
    if has_from != has_to:
        print(tr("error.extract_options_together"), file=sys.stderr)
        sys.exit(2)

    has_gui_startup_args = (
        "gui_startup_apprun_args" in flags
        or "gui_startup_run_args" in flags
    )
    if has_gui_startup_args and "install_as_gui_startup" not in flags:
        print(tr("error.startup_args_require_install"), file=sys.stderr)
        sys.exit(2)

    if not remaining:
        print(tr("usage.apprun3_short"), file=sys.stderr)
        sys.exit(2)

    return flags, remaining[0], remaining[1:]

