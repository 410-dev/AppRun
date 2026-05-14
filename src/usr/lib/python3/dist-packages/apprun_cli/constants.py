"""Constants for the AppRun command implementation."""

import shutil
from pathlib import Path

UV_BIN = shutil.which("uv") or "/usr/bin/uv"
PYTHON3_BIN = "/usr/bin/python3"
SYSTEMD_UNIT_DIR = Path("/etc/systemd/system")
SYSTEMD_GLOBAL_USER_UNIT_DIR = Path("/etc/systemd/user")
SERVICE_STORE_ROOT = Path("/usr/share/services.apprd")
SYSTEM_SERVICE_STORE_DIR = SERVICE_STORE_ROOT / "system"
GLOBAL_USER_SERVICE_STORE_DIR = SERVICE_STORE_ROOT / "global"
GLOBAL_GUI_STARTUP_DIR = Path("/etc/xdg/autostart")
GLOBAL_GUI_STARTUP_STORE_DIR = SERVICE_STORE_ROOT / "gui-startup" / "global"
PORTABLE_TARGETS = {"mount", "box"}
INHERIT_TARGETS = {"venv", "data", "full"}

