"""Small desktop notification and GUI alert helpers."""

from __future__ import annotations

import os
import shutil
import subprocess


def can_use_dbus_and_gui() -> bool:
    return bool(
        os.environ.get("DISPLAY")
        and all(os.environ.get(k) for k in [
            "DBUS_SESSION_BUS_ADDRESS",
            "DBUS_STARTER_ADDRESS",
            "DBUS_STARTER_BUS_TYPE",
        ])
    )


def notify(title: str, message: str) -> None:
    if shutil.which("notify-send") and can_use_dbus_and_gui():
        subprocess.run(["notify-send", title, message])


def show_gui_alert(title: str, message: str, level: str = "info") -> None:
    print(f"[AppRun] {title}: {message}")
    if not can_use_dbus_and_gui():
        return

    zenity_flag = {"info": "--info", "warning": "--warning", "error": "--error"}.get(level, "--info")
    kdialog_flag = {"info": "--msgbox", "warning": "--sorry", "error": "--error"}.get(level, "--msgbox")
    if shutil.which("zenity"):
        subprocess.run(["zenity", zenity_flag, f"--text={message}", f"--title={title}", "--width=400"])
    elif shutil.which("kdialog"):
        subprocess.run(["kdialog", kdialog_flag, message, "--title", title])

