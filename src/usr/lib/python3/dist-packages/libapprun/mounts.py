"""Mount path and FUSE lifecycle helpers."""

from __future__ import annotations

import secrets
import subprocess
from pathlib import Path

from apprun_validation import validate_app_id

from .constants import FUSERMOUNT, MOUNT_ROOT, SQUASHFUSE


def mount(apprunx: str, mountpoint: str) -> None:
    """Mount an AppRun squashfs bundle at ``mountpoint``."""
    mp = Path(mountpoint)
    mp.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [SQUASHFUSE, apprunx, str(mp)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"mount failed: {result.stderr}")


def unmount(mountpoint: str) -> None:
    """Unmount a previously mounted bundle and remove the mount directory."""
    subprocess.run([FUSERMOUNT, "-u", mountpoint], check=True)
    Path(mountpoint).rmdir()


def is_mounted(mountpoint: str) -> bool:
    """Return True only when ``mountpoint`` exactly appears in /proc/mounts."""
    mp = str(Path(mountpoint).resolve())
    with open("/proc/mounts") as mounts:
        for line in mounts:
            parts = line.split(" ", 2)
            if len(parts) >= 2 and parts[1] == mp:
                return True
    return False


def random_suffix() -> str:
    """Return a short cryptographically random path suffix."""
    return secrets.token_hex(4)


def get_mount_path(app_id: str) -> Path:
    app_id = validate_app_id(app_id)
    return MOUNT_ROOT / f"{app_id}.{random_suffix()}"


def get_portable_data_root(apprunx: str, app_id: str) -> Path:
    app_id = validate_app_id(app_id)
    return Path(apprunx).resolve().parent / f"{app_id}.apprunx.data.d"


def get_portable_mount_path(apprunx: str, app_id: str) -> Path:
    return get_portable_data_root(apprunx, app_id) / "mounts" / f"{app_id}.{random_suffix()}"

