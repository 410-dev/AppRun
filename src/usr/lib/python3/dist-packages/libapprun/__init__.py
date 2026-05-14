"""AppRun Format 3 public Python API.

This package replaces the historical single-file ``libapprun.py`` while keeping
``import libapprun`` and ``from libapprun import ...`` working.  Keep this file
as the stable export surface; implementation details live in the sibling
modules.
"""

from .boxes import (
    ensure_box,
    ensure_box_path,
    get_box_path,
    get_box_root,
    get_portable_box_path,
    is_locked,
    is_locked_path,
    lock,
    unlock,
)
from .bundle import (
    get_bundle_id,
    get_bundle_meta,
    get_meta_value,
    list_files,
    peek_file,
    peek_file_bytes,
)
from .constants import (
    BOXES_ROOT,
    FUSERMOUNT,
    MKSQUASHFS,
    MOUNT_ROOT,
    SQUASHFUSE,
    UNSQUASHFS,
)
from .mounts import (
    get_mount_path,
    get_portable_data_root,
    get_portable_mount_path,
    is_mounted,
    mount,
    random_suffix,
    unmount,
)
from .packages import (
    _get_installed_version,
    _parse_pkg_requirement,
    _version_satisfies,
    list_missing_base_packages,
)
from .ui import can_use_dbus_and_gui, notify, show_gui_alert
from .util import get_checksum, run_cmd

__all__ = [
    "BOXES_ROOT",
    "FUSERMOUNT",
    "MKSQUASHFS",
    "MOUNT_ROOT",
    "SQUASHFUSE",
    "UNSQUASHFS",
    "_get_installed_version",
    "_parse_pkg_requirement",
    "_version_satisfies",
    "can_use_dbus_and_gui",
    "ensure_box",
    "ensure_box_path",
    "get_box_path",
    "get_box_root",
    "get_bundle_id",
    "get_bundle_meta",
    "get_checksum",
    "get_meta_value",
    "get_mount_path",
    "get_portable_box_path",
    "get_portable_data_root",
    "get_portable_mount_path",
    "is_locked",
    "is_locked_path",
    "is_mounted",
    "list_files",
    "list_missing_base_packages",
    "lock",
    "mount",
    "notify",
    "peek_file",
    "peek_file_bytes",
    "random_suffix",
    "run_cmd",
    "show_gui_alert",
    "unlock",
    "unmount",
]

